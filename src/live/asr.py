"""Pseudo-streaming ASR work scheduling independent of capture and Qt."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from src.core.asr.types import TranscriptionSegment

from .types import CaptureSource, PcmChunk, TranscriptEvent


class WindowBackend(Protocol):
    def transcribe_window(
        self,
        audio: np.ndarray,
        sample_rate: int,
        offset_samples: int,
    ) -> list[TranscriptionSegment]: ...


@dataclass
class _SpeechRun:
    start: int
    end: int
    audio: list[np.ndarray]


@dataclass(frozen=True)
class _Job:
    source: CaptureSource
    start: int
    end: int
    audio: np.ndarray
    is_final: bool


class LiveAsrScheduler:
    """Prioritize committed speech and retain only the newest partial decode."""

    def __init__(
        self,
        backend: WindowBackend,
        *,
        partial_delay_seconds: float = 1.5,
        on_partial: Callable[[TranscriptEvent], None] | None = None,
        on_final: Callable[[TranscriptEvent], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if partial_delay_seconds <= 0:
            raise ValueError("partial_delay_seconds must be positive")
        self._backend = backend
        self._partial_delay_seconds = partial_delay_seconds
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._runs: dict[CaptureSource, _SpeechRun] = {}
        self._final_jobs: deque[_Job] = deque()
        self._partial_job: _Job | None = None
        self._partial_revisions: dict[str, int] = {}
        self._refresh_seconds = 0.25
        self._closed = False
        self._condition = threading.Condition()
        self._worker = threading.Thread(target=self._run, name="live-asr", daemon=True)
        self._worker.start()

    @property
    def pending_partial_offset(self) -> int | None:
        with self._condition:
            return None if self._partial_job is None else self._partial_job.end

    @property
    def refresh_seconds(self) -> float:
        with self._condition:
            return self._refresh_seconds

    def submit(self, chunk: PcmChunk) -> None:
        if chunk.sample_rate != 16_000 or chunk.channels != 1:
            raise ValueError("live ASR requires derived 16 kHz mono chunks")
        audio = chunk.frames[:, 0]
        voiced = bool(np.any(np.abs(audio) > 0.01))
        with self._condition:
            if self._closed:
                raise RuntimeError("scheduler is closed")
            run = self._runs.get(chunk.source)
            if voiced:
                if run is None:
                    run = _SpeechRun(chunk.sample_offset, chunk.sample_offset, [])
                    self._runs[chunk.source] = run
                run.audio.append(audio.copy())
                run.end = chunk.sample_offset + len(audio)
                if run.end - run.start >= self._partial_delay_seconds * chunk.sample_rate:
                    self._partial_job = self._job(chunk.source, run, is_final=False)
                    self._condition.notify()
            elif run is not None:
                self._final_jobs.append(self._job(chunk.source, run, is_final=True))
                del self._runs[chunk.source]
                self._condition.notify()

    def flush(self) -> None:
        with self._condition:
            for source, run in list(self._runs.items()):
                self._final_jobs.append(self._job(source, run, is_final=True))
                del self._runs[source]
            self._condition.notify_all()

    def record_decode_duration(self, seconds: float) -> None:
        with self._condition:
            self._refresh_seconds = min(1.5, max(0.25, seconds))

    def close(self) -> None:
        self.flush()
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._worker.join(timeout=1)

    @staticmethod
    def _job(source: CaptureSource, run: _SpeechRun, *, is_final: bool) -> _Job:
        return _Job(source, run.start, run.end, np.concatenate(run.audio), is_final)

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._final_jobs and self._partial_job is None and not self._closed:
                    self._condition.wait()
                if self._final_jobs:
                    job = self._final_jobs.popleft()
                elif self._partial_job is not None:
                    job = self._partial_job
                    self._partial_job = None
                elif self._closed:
                    return
                else:
                    continue
            started = time.monotonic()
            try:
                segments = self._backend.transcribe_window(job.audio, 16_000, job.start)
                self._publish(job, segments)
            except Exception as exc:
                if self._on_error is not None:
                    self._on_error(exc)
            finally:
                self.record_decode_duration(time.monotonic() - started)

    def _publish(self, job: _Job, segments: list[TranscriptionSegment]) -> None:
        if not segments:
            return
        text = " ".join(segment["transcription"].strip() for segment in segments).strip()
        if not text:
            return
        event_id = f"{job.source.value}-{job.start}"
        revision = self._partial_revisions.get(event_id, -1) + 1
        self._partial_revisions[event_id] = revision
        event = TranscriptEvent(
            event_id=event_id,
            revision=revision,
            source=job.source,
            sample_start=job.start,
            sample_end=job.end,
            timestamp_ns=time.time_ns(),
            text=text,
            status="final" if job.is_final else "partial",
            supersedes=revision - 1 if revision else None,
        )
        callback = self._on_final if job.is_final else self._on_partial
        if callback is not None:
            callback(event)
