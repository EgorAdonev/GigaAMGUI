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
    ) -> None:
        self._source = source
        self._sample_rate = sample_rate
        self._channels = channels
        self._on_event = on_event
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
    def __init__(self, mic_gain: float = 1.0, system_gain: float = 1.0) -> None:
        self._mic_gain = mic_gain
        self._system_gain = system_gain

    def mix(self, chunks: Mapping[CaptureSource, PcmChunk]) -> PcmChunk:
        if not chunks:
            raise ValueError("at least one chunk is required")
        reference = next(iter(chunks.values()))
        for chunk in chunks.values():
            if (
                chunk.sample_rate != reference.sample_rate
                or chunk.channels != reference.channels
                or chunk.sample_offset != reference.sample_offset
                or chunk.frames.shape != reference.frames.shape
            ):
                raise ValueError("chunks must share format, offset, and frame count")

        mixed = np.zeros_like(reference.frames)
        mic = chunks.get(CaptureSource.MIC)
        system = chunks.get(CaptureSource.SYSTEM)
        if mic is not None:
            mixed += self._mic_gain * mic.frames
        if system is not None:
            mixed += self._system_gain * system.frames
        np.clip(mixed, -1.0, 1.0, out=mixed)
        return PcmChunk(
            CaptureSource.MIC,
            reference.sample_rate,
            reference.channels,
            reference.sample_offset,
            mixed,
            reference.timestamp_ns,
        )
