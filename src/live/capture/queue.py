"""Non-blocking bounded queue for copied capture frames."""

from __future__ import annotations

from collections.abc import Callable
from queue import Empty, SimpleQueue
from threading import Lock

from ..types import CaptureEvent, CaptureEventKind, PcmChunk


class BoundedChunkQueue:
    def __init__(
        self,
        max_frames: int,
        on_event: Callable[[CaptureEvent], None] | None = None,
    ) -> None:
        if max_frames <= 0:
            raise ValueError("max_frames must be positive")
        self._max_frames = max_frames
        self._on_event = on_event
        self._chunks: SimpleQueue[PcmChunk] = SimpleQueue()
        self._lock = Lock()
        self._queued_frames = 0
        self.dropped_frames = 0

    def put(self, chunk: PcmChunk) -> bool:
        frame_count = len(chunk.frames)
        with self._lock:
            if self._queued_frames + frame_count > self._max_frames:
                self.dropped_frames += frame_count
                accepted = False
            else:
                self._queued_frames += frame_count
                accepted = True

        if not accepted:
            if self._on_event is not None:
                self._on_event(
                    CaptureEvent(
                        CaptureEventKind.OVERFLOW,
                        chunk.source,
                        chunk.sample_offset,
                        chunk.timestamp_ns,
                        f"queue full; dropped_frames={frame_count}",
                    )
                )
            return False

        self._chunks.put(chunk)
        return True

    def get(self, timeout: float) -> PcmChunk | None:
        try:
            chunk = self._chunks.get(timeout=timeout)
        except Empty:
            return None

        with self._lock:
            self._queued_frames -= len(chunk.frames)
        return chunk
