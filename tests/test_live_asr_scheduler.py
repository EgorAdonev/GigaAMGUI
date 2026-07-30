import time

import numpy as np

from src.live.asr import LiveAsrScheduler
from src.live.types import CaptureSource, PcmChunk


class FakeBackend:
    def __init__(self):
        self.requests = []

    def transcribe_window(self, audio, sample_rate, offset_samples):
        self.requests.append((audio.copy(), sample_rate, offset_samples))
        start = offset_samples / sample_rate
        return [{"transcription": "recognized speech", "boundaries": (start, start + 0.5)}]


def voiced_chunk(offset: int, seconds: float) -> PcmChunk:
    frames = np.ones((int(seconds * 16_000), 1), dtype=np.float32)
    return PcmChunk(CaptureSource.MIC, 16_000, 1, offset, frames, 1)


def silent_chunk(offset: int, seconds: float = 0.1) -> PcmChunk:
    frames = np.zeros((int(seconds * 16_000), 1), dtype=np.float32)
    return PcmChunk(CaptureSource.MIC, 16_000, 1, offset, frames, 1)


def wait_until(predicate):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("scheduler did not finish work")


def test_new_partial_replaces_stale_pending_partial_job():
    backend = FakeBackend()
    scheduler = LiveAsrScheduler(backend=backend, partial_delay_seconds=1.5)
    try:
        scheduler.submit(voiced_chunk(0, 2))
        scheduler.submit(voiced_chunk(2 * 16_000, 1))

        assert scheduler.pending_partial_offset == 3 * 16_000
    finally:
        scheduler.close()


def test_silence_commits_final_event_after_partial_speech():
    backend = FakeBackend()
    partials = []
    finals = []
    scheduler = LiveAsrScheduler(
        backend=backend,
        partial_delay_seconds=1.5,
        on_partial=partials.append,
        on_final=finals.append,
    )
    try:
        scheduler.submit(voiced_chunk(0, 2))
        scheduler.submit(silent_chunk(2 * 16_000))

        wait_until(lambda: finals)
        assert finals[0].status == "final"
        assert finals[0].sample_start == 0
        assert finals[0].sample_end == 2 * 16_000
        assert finals[0].text == "recognized speech"
    finally:
        scheduler.close()


def test_slow_decode_lengthens_refresh_within_configured_limit():
    scheduler = LiveAsrScheduler(backend=FakeBackend())
    try:
        scheduler.record_decode_duration(2.0)

        assert scheduler.refresh_seconds == 1.5
    finally:
        scheduler.close()
