"""Source-isolated live capture lifecycle coordinator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Protocol

from src.core.asr.types import normalize_window_audio

from .capture.base import CaptureAdapter
from .diarization import LIVE_ESTIMATE_STABILIZATION_HORIZON_SECONDS, label_event
from .exports import ExportSelection, export_session
from .journal import EventJournal, LiveSessionStore
from .recorder import SessionRecorder
from .timeline import AlignedMixer, SourceTimeline
from .types import CaptureEvent, CaptureEventKind, CaptureSource, CaptureState, DiarizationMode, LiveSettings, PcmChunk, TranscriptEvent


class AsrScheduler(Protocol):
    def submit(self, chunk: PcmChunk) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class LiveStatus:
    state: CaptureState
    active_sources: set[CaptureSource]
    failed_sources: set[CaptureSource]


@dataclass(frozen=True)
class SessionResult:
    session_dir: Path
    recordings: dict[CaptureSource, Path]
    exports: list[Path]


SchedulerFactory = Callable[
    [CaptureSource, Callable[[TranscriptEvent], None], Callable[[TranscriptEvent], None], Callable[[Exception], None]], AsrScheduler
]


class LiveSession:
    """Own capture lifecycle while leaving ASR work on scheduler-owned threads."""

    def __init__(
        self,
        root_dir: Path,
        settings: LiveSettings,
        adapters: Mapping[CaptureSource, CaptureAdapter],
        *,
        scheduler_factory: SchedulerFactory,
        export_selection: ExportSelection | None = None,
        recorder_factory: Callable[[Path, bool | set[CaptureSource], bool], SessionRecorder] = SessionRecorder,
        diarization_factory: Callable[[str], object] | None = None,
        translate: Callable[[str, str], str] | None = None,
    ) -> None:
        self._settings = settings
        self._adapters = dict(adapters)
        self._scheduler_factory = scheduler_factory
        self._export_selection = replace(
            export_selection or ExportSelection(),
            sample_rate=settings.asr_sample_rate,
        )
        self._recorder_factory = recorder_factory
        self._diarization_factory = diarization_factory
        self._translate = translate or (lambda _ru, en: en)
        self._session_dir = LiveSessionStore(root_dir).create(settings)
        self._journal = EventJournal(self._session_dir / "events.jsonl")
        self._recorder = recorder_factory(
            self._session_dir,
            {
                source
                for source, selected in (
                    (CaptureSource.MIC, settings.record_mic_audio),
                    (CaptureSource.SYSTEM, settings.record_system_audio),
                )
                if settings.record_source_audio and selected
            },
            settings.record_mix_audio,
        )
        self._state = CaptureState.IDLE
        self._active_sources: set[CaptureSource] = set()
        self._failed_sources: set[CaptureSource] = set()
        self._timelines: dict[CaptureSource, SourceTimeline] = {}
        self._mix_inputs: dict[int, dict[CaptureSource, PcmChunk]] = {}
        self._schedulers: dict[CaptureSource, AsrScheduler] = {}
        self._live_diarizers: dict[CaptureSource, object] = {}
        self._live_diarization_unavailable: set[CaptureSource] = set()
        self._speaker_labels: dict[tuple[CaptureSource, str], str] = {}
        self._finalized_revisions: dict[tuple[CaptureSource, str], int] = {}
        self._subscribers: list[Callable[[TranscriptEvent | CaptureEvent | LiveStatus], None]] = []
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._state is not CaptureState.IDLE:
                raise RuntimeError("session has already started")
            self._state = CaptureState.STARTING
            for source, adapter in self._adapters.items():
                self._schedulers[source] = self._scheduler_factory(
                    source,
                    self._on_final,
                    self._on_partial,
                    lambda error, source=source: self._on_asr_error(source, error),
                )
                # Native adapters can emit an asynchronous permission/device event
                # during start; mark source active before that callback can arrive.
                self._active_sources.add(source)
                try:
                    adapter.start(self._on_chunk, self._on_event)
                except Exception as exc:
                    self._mark_failed(source, str(exc))
            self._state = CaptureState.RECORDING if self._active_sources else CaptureState.FAILED
            self._notify_status()

    def pause(self) -> None:
        with self._lock:
            if self._state is not CaptureState.RECORDING:
                raise RuntimeError("only a recording session can be paused")
            for source in self._active_sources:
                self._adapters[source].pause()
            self._state = CaptureState.PAUSED
            self._notify_status()

    def resume(self) -> None:
        with self._lock:
            if self._state is not CaptureState.PAUSED:
                raise RuntimeError("only a paused session can be resumed")
            for source in self._active_sources:
                self._adapters[source].resume()
            self._state = CaptureState.RECORDING
            self._notify_status()

    def stop(self) -> SessionResult:
        with self._lock:
            if self._state in {CaptureState.STOPPED, CaptureState.IDLE}:
                raise RuntimeError("session is not running")
            self._state = CaptureState.STOPPING
            for source in self._active_sources:
                self._adapters[source].stop()
            for scheduler in self._schedulers.values():
                scheduler.flush()
                scheduler.close()
            recordings = self._recorder.close()
            if self._settings.diarization_mode is DiarizationMode.AFTER_STOP:
                self._diarize_recordings(recordings)
            exports = export_session(self._session_dir, self._journal.latest_events(), self._export_selection)
            self._active_sources.clear()
            self._state = CaptureState.STOPPED
            self._notify_status()
            return SessionResult(self._session_dir, recordings, exports)

    def status(self) -> LiveStatus:
        with self._lock:
            return LiveStatus(self._state, set(self._active_sources), set(self._failed_sources))

    def ask_context(self) -> str:
        return "\n".join(
            f"[{datetime.fromtimestamp(event.timestamp_ns / 1_000_000_000, timezone.utc).isoformat()}] "
            f"{event.source_label}{f' / {event.speaker}' if event.speaker else ''}: {event.text}"
            for event in self._journal.latest_events()
            if event.status == "final"
        )

    def subscribe(self, callback: Callable[[TranscriptEvent | CaptureEvent | LiveStatus], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def _on_chunk(self, chunk: PcmChunk) -> None:
        with self._lock:
            if self._state is not CaptureState.RECORDING or chunk.source not in self._active_sources:
                return
            timeline = self._timelines.setdefault(
                chunk.source,
                SourceTimeline(chunk.source, chunk.sample_rate, chunk.channels, self._on_event),
            )
            for aligned in timeline.ingest(chunk):
                self._recorder.write(aligned)
                mix_inputs = self._mix_inputs.setdefault(aligned.sample_offset, {})
                mix_inputs[aligned.source] = aligned
                if {CaptureSource.MIC, CaptureSource.SYSTEM} <= mix_inputs.keys():
                    self._recorder.write_mix(AlignedMixer().mix(mix_inputs))
                    del self._mix_inputs[aligned.sample_offset]
                audio = normalize_window_audio(aligned.frames[:, 0], aligned.sample_rate, self._settings.asr_sample_rate)
                offset = round(aligned.sample_offset * self._settings.asr_sample_rate / aligned.sample_rate)
                self._schedulers[aligned.source].submit(
                    PcmChunk(
                        aligned.source,
                        self._settings.asr_sample_rate,
                        1,
                        offset,
                        audio[:, None].copy(),
                        aligned.timestamp_ns,
                    )
                )
            LiveSessionStore(self._session_dir.parent).write_checkpoint(
                self._session_dir,
                {"active_sources": sorted(source.value for source in self._active_sources)},
            )

    def _on_event(self, event: CaptureEvent) -> None:
        with self._lock:
            if event.kind in {CaptureEventKind.PERMISSION_DENIED, CaptureEventKind.DEVICE_REMOVED, CaptureEventKind.DISK_FULL}:
                self._mark_failed(event.source, event.detail)
            self._notify(event)

    def _on_final(self, event: TranscriptEvent) -> None:
        with self._lock:
            finalized = label_event(event, self._settings.diarization_mode)
            self._record_finalized(finalized)
            self._journal.append(finalized)
            self._notify(finalized)
            if self._settings.diarization_mode is DiarizationMode.LIVE_ESTIMATE:
                for revised in self._estimate_live_speakers(finalized):
                    self._record_finalized(revised)
                    self._journal.append(revised)
                    self._notify(revised)

    def _on_partial(self, event: TranscriptEvent) -> None:
        with self._lock:
            if event.revision <= self._finalized_revisions.get((event.source, event.event_id), -1):
                return
            self._notify(event)

    def _record_finalized(self, event: TranscriptEvent) -> None:
        key = (event.source, event.event_id)
        self._finalized_revisions[key] = max(event.revision, self._finalized_revisions.get(key, -1))

    def _estimate_live_speakers(self, event: TranscriptEvent) -> list[TranscriptEvent]:
        diarizer = self._live_diarizers.get(event.source)
        if diarizer is None and event.source not in self._live_diarization_unavailable:
            try:
                diarizer = self._create_diarizer("sortformer")
                self._live_diarizers[event.source] = diarizer
            except Exception as exc:
                self._report_live_diarization_unavailable(event.source, str(exc))
                return []
        estimate = getattr(diarizer, "estimate_events", None)
        if not callable(estimate):
            self._report_live_diarization_unavailable(
                event.source,
                "Live Sortformer estimate unavailable; use After stop for offline speaker labels. "
                "Retaining source labels.",
            )
            return []
        horizon_samples = LIVE_ESTIMATE_STABILIZATION_HORIZON_SECONDS * self._settings.asr_sample_rate
        recent = [
            item
            for item in self._journal.latest_events()
            if item.source is event.source and event.sample_end - item.sample_end <= horizon_samples
        ]
        try:
            estimates = estimate(
                recent,
                stabilization_horizon_seconds=LIVE_ESTIMATE_STABILIZATION_HORIZON_SECONDS,
            )
        except Exception as exc:
            self._report_live_diarization_unavailable(event.source, str(exc))
            return []
        return self._revised_speakers(recent, estimates)

    def _diarize_recordings(self, recordings: dict[CaptureSource, Path]) -> None:
        for source, path in recordings.items():
            try:
                diarizer = self._create_diarizer("onnx")
                segments = diarizer.diarize(str(path))
                events = [event for event in self._journal.latest_events() if event.source is source]
                for revised in self._revised_speakers(events, self._segment_speakers(events, segments)):
                    self._record_finalized(revised)
                    self._journal.append(revised)
                    self._notify(revised)
            except Exception as exc:
                self._notify(CaptureEvent(
                    CaptureEventKind.STATUS,
                    source,
                    0,
                    0,
                    f"After-stop diarization unavailable: {exc}. Retaining source labels.",
                ))

    def _create_diarizer(self, backend: str):
        if self._diarization_factory is not None:
            return self._diarization_factory(backend)
        from src.core.diarization.factory import create_diarization_backend

        return create_diarization_backend(backend)

    def _segment_speakers(self, events, segments) -> dict[str, str]:
        speakers = {}
        for event in events:
            start = event.sample_start / self._settings.asr_sample_rate
            end = event.sample_end / self._settings.asr_sample_rate
            overlaps = [
                (max(0.0, min(end, segment.end) - max(start, segment.start)), segment.speaker)
                for segment in segments
            ]
            if overlaps:
                _, speaker = max(overlaps, key=lambda item: item[0])
                speakers[event.event_id] = speaker
        return speakers

    def _revised_speakers(self, events, estimates) -> list[TranscriptEvent]:
        revised = []
        for event in events:
            speaker = estimates.get(event.event_id)
            if speaker is None:
                continue
            anonymous = self._anonymous_speaker(event.source, str(speaker))
            if event.speaker != anonymous:
                revised.append(replace(event, revision=event.revision + 1, speaker=anonymous, supersedes=event.revision))
        return revised

    def _anonymous_speaker(self, source: CaptureSource, raw_speaker: str) -> str:
        key = (source, raw_speaker)
        number = len(self._speaker_labels) + 1
        return self._speaker_labels.setdefault(
            key,
            self._translate(f"Спикер {number}", f"Speaker {number}"),
        )

    def _report_live_diarization_unavailable(self, source: CaptureSource, detail: str) -> None:
        if source in self._live_diarization_unavailable:
            return
        self._live_diarization_unavailable.add(source)
        guidance = self._translate(
            "Используйте «После остановки» для офлайн-меток спикеров; "
            "метки источников сохраняются.",
            "Use After stop for offline speaker labels; retaining source labels.",
        )
        self._notify(CaptureEvent(
            CaptureEventKind.STATUS,
            source,
            0,
            0,
            f"{detail} {guidance}",
        ))

    def _on_asr_error(self, source: CaptureSource, error: Exception) -> None:
        self._notify(CaptureEvent(CaptureEventKind.STATUS, source, 0, 0, str(error)))

    def _mark_failed(self, source: CaptureSource, detail: str) -> None:
        self._active_sources.discard(source)
        self._failed_sources.add(source)
        if not self._active_sources and self._state is not CaptureState.STARTING:
            self._state = CaptureState.FAILED
        self._notify(CaptureEvent(CaptureEventKind.STATUS, source, 0, 0, detail))

    def _notify_status(self) -> None:
        self._notify(self.status())

    def _notify(self, value: TranscriptEvent | CaptureEvent | LiveStatus) -> None:
        for callback in tuple(self._subscribers):
            callback(value)
