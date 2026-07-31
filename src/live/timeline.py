"""Source-offset alignment and bounded gain mixing for live audio."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from .types import CaptureEvent, CaptureEventKind, CaptureSource, PcmChunk


class SourceTimeline:
    def __init__(
        self,
        source: CaptureSource,
        sample_rate: int,
        channels: int,
        on_event: Callable[[CaptureEvent], None] | None = None,
        max_gap_seconds: float = 1.0,
    ) -> None:
        if max_gap_seconds < 0:
            raise ValueError("max_gap_seconds must be non-negative")
        self._source = source
        self._sample_rate = sample_rate
        self._channels = channels
        self._on_event = on_event
        self._max_gap_frames = round(max_gap_seconds * sample_rate)
        self._next_offset: int | None = None

    def ingest(self, chunk: PcmChunk) -> list[PcmChunk]:
        if chunk.source is not self._source:
            raise ValueError("chunk source does not match timeline")
        if chunk.sample_rate != self._sample_rate or chunk.channels != self._channels:
            raise ValueError("chunk format does not match timeline")
        if self._next_offset is None:
            self._next_offset = chunk.sample_offset

        emitted: list[PcmChunk] = []
        if chunk.sample_offset > self._next_offset:
            gap = chunk.sample_offset - self._next_offset
            if gap <= self._max_gap_frames:
                emitted.append(
                    PcmChunk(
                        self._source,
                        self._sample_rate,
                        self._channels,
                        self._next_offset,
                        np.zeros((gap, self._channels), dtype=np.float32),
                        chunk.timestamp_ns,
                    )
                )
                self._emit_discontinuity(chunk, f"gap={gap}")
            else:
                self._emit_discontinuity(chunk, f"gap={gap} discarded")
            self._next_offset = chunk.sample_offset
        elif chunk.sample_offset < self._next_offset:
            overlap = self._next_offset - chunk.sample_offset
            self._emit_discontinuity(chunk, f"overlap={overlap}")
            if overlap >= len(chunk.frames):
                return emitted
            chunk = PcmChunk(
                chunk.source,
                chunk.sample_rate,
                chunk.channels,
                self._next_offset,
                chunk.frames[overlap:].copy(),
                chunk.timestamp_ns,
            )

        emitted.append(chunk)
        self._next_offset += len(chunk.frames)
        return emitted

    def _emit_discontinuity(self, chunk: PcmChunk, detail: str) -> None:
        if self._on_event is not None:
            self._on_event(
                CaptureEvent(
                    CaptureEventKind.DISCONTINUITY,
                    self._source,
                    chunk.sample_offset,
                    chunk.timestamp_ns,
                    detail,
                )
            )


class AlignedMixer:
    def __init__(
        self,
        mic_gain: float = 1.0,
        system_gain: float = 1.0,
        *,
        max_skew_seconds: float = 1.0,
        max_output_frames: int = 48_000,
    ) -> None:
        if max_skew_seconds < 0:
            raise ValueError("max_skew_seconds must be non-negative")
        if max_output_frames <= 0:
            raise ValueError("max_output_frames must be positive")
        self._mic_gain = mic_gain
        self._system_gain = system_gain
        self._max_skew_seconds = max_skew_seconds
        self._max_output_frames = max_output_frames

    def mix(self, chunks: Mapping[CaptureSource, PcmChunk]) -> PcmChunk:
        if not chunks:
            raise ValueError("at least one chunk is required")
        reference = chunks.get(CaptureSource.MIC) or chunks.get(CaptureSource.SYSTEM) or next(iter(chunks.values()))
        start_ns = min(chunk.timestamp_ns for chunk in chunks.values())
        skew_seconds = (max(chunk.timestamp_ns for chunk in chunks.values()) - start_ns) / 1_000_000_000
        if skew_seconds > self._max_skew_seconds:
            raise ValueError(f"timestamp skew {skew_seconds:.3f}s exceeds mix limit")
        expected_frames = {
            source: round(len(chunk.frames) * reference.sample_rate / chunk.sample_rate)
            for source, chunk in chunks.items()
        }
        if any(frame_count > self._max_output_frames for frame_count in expected_frames.values()):
            raise ValueError("mix input exceeds output frame limit")
        normalized = {
            source: self._normalize(chunk, reference.sample_rate, reference.channels)
            for source, chunk in chunks.items()
        }
        starts = {
            source: round((chunk.timestamp_ns - start_ns) * reference.sample_rate / 1_000_000_000)
            for source, chunk in chunks.items()
        }
        frame_count = max(starts[source] + len(frames) for source, frames in normalized.items())
        if frame_count > self._max_output_frames:
            raise ValueError("mix output exceeds frame limit")
        mixed = np.zeros((frame_count, reference.channels), dtype=np.float32)
        mic = chunks.get(CaptureSource.MIC)
        system = chunks.get(CaptureSource.SYSTEM)
        if mic is not None:
            start = starts[CaptureSource.MIC]
            frames = normalized[CaptureSource.MIC]
            mixed[start:start + len(frames)] += self._mic_gain * frames
        if system is not None:
            start = starts[CaptureSource.SYSTEM]
            frames = normalized[CaptureSource.SYSTEM]
            mixed[start:start + len(frames)] += self._system_gain * frames
        np.clip(mixed, -1.0, 1.0, out=mixed)
        return PcmChunk(
            CaptureSource.MIC,
            reference.sample_rate,
            reference.channels,
            max(0, reference.sample_offset - starts[reference.source]),
            mixed,
            start_ns,
        )

    @staticmethod
    def _normalize(chunk: PcmChunk, sample_rate: int, channels: int) -> np.ndarray:
        frames = chunk.frames
        if chunk.channels != channels:
            if channels == 1:
                frames = frames.mean(axis=1, dtype=np.float32)[:, None]
            elif chunk.channels == 1:
                frames = np.repeat(frames, channels, axis=1)
            elif chunk.channels > channels:
                frames = frames[:, :channels]
            else:
                frames = np.concatenate(
                    (frames, np.repeat(frames[:, -1:], channels - chunk.channels, axis=1)), axis=1
                )
        if chunk.sample_rate == sample_rate or not len(frames):
            return frames.copy()
        frame_count = round(len(frames) * sample_rate / chunk.sample_rate)
        positions = np.linspace(0, len(frames) - 1, frame_count, dtype=np.float32)
        return np.stack(
            [np.interp(positions, np.arange(len(frames)), frames[:, channel]) for channel in range(channels)],
            axis=1,
        ).astype(np.float32)
