import numpy as np

from src.live.capture.queue import BoundedChunkQueue
from src.live.types import CaptureEventKind, CaptureSource, PcmChunk


def chunk(offset: int, count: int, source: CaptureSource = CaptureSource.MIC) -> PcmChunk:
    return PcmChunk(source, 48_000, 1, offset, np.zeros((count, 1), dtype=np.float32), 1)


def test_full_queue_drops_new_chunk_without_blocking():
    events = []
    queue = BoundedChunkQueue(max_frames=4, on_event=events.append)

    assert queue.put(chunk(offset=0, count=4)) is True
    assert queue.put(chunk(offset=4, count=1)) is False

    assert queue.dropped_frames == 1
    assert [(event.kind, event.sample_offset) for event in events] == [
        (CaptureEventKind.OVERFLOW, 4)
    ]


def test_get_releases_frame_capacity_for_the_next_chunk():
    queue = BoundedChunkQueue(max_frames=4)
    first = chunk(offset=0, count=4)

    assert queue.put(first) is True
    assert queue.get(timeout=0) is first
    assert queue.put(chunk(offset=4, count=4)) is True


def test_empty_queue_returns_none_after_timeout():
    assert BoundedChunkQueue(max_frames=1).get(timeout=0) is None
