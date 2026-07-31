import numpy as np

from src.live.session import LiveSession
from src.live.types import CaptureEvent, CaptureEventKind, CaptureSource, CaptureState, LiveSettings, PcmChunk


class FakeAdapter:
    def start(self, on_chunk, on_event):
        self.on_chunk = on_chunk
        self.on_event = on_event

    def pause(self):
        return None

    def stop(self):
        return None

    def emit(self, chunk):
        self.on_chunk(chunk)

    def fail(self, source):
        self.on_event(CaptureEvent(CaptureEventKind.DEVICE_REMOVED, source, 0, 1, "removed"))


class StartDeniedAdapter(FakeAdapter):
    def start(self, on_chunk, on_event):
        super().start(on_chunk, on_event)
        on_event(CaptureEvent(CaptureEventKind.PERMISSION_DENIED, CaptureSource.SYSTEM, 0, 1, "denied"))


class FakeScheduler:
    def __init__(self, on_error=None):
        self._on_error = on_error

    def submit(self, chunk):
        return None

    def flush(self):
        return None

    def close(self):
        return None

    def fail(self):
        self._on_error(RuntimeError("decode failed"))


def test_removed_system_source_does_not_stop_microphone(tmp_path):
    mic = FakeAdapter()
    system = FakeAdapter()
    session = LiveSession(
        tmp_path,
        LiveSettings(record_mix_audio=False),
        {CaptureSource.MIC: mic, CaptureSource.SYSTEM: system},
        scheduler_factory=lambda source, on_final, on_partial, on_error: FakeScheduler(),
    )

    session.start()
    system.fail(CaptureSource.SYSTEM)
    mic.emit(
        PcmChunk(CaptureSource.MIC, 48_000, 1, 0, np.ones((4_800, 1), dtype=np.float32), 1)
    )

    status = session.status()
    assert status.state is CaptureState.RECORDING
    assert status.active_sources == {CaptureSource.MIC}
    assert status.failed_sources == {CaptureSource.SYSTEM}


def test_asr_error_is_reported_without_stopping_its_source(tmp_path):
    adapter = FakeAdapter()
    events = []
    scheduler = None

    def scheduler_factory(source, on_final, on_partial, on_error):
        nonlocal scheduler
        scheduler = FakeScheduler(on_error)
        return scheduler

    session = LiveSession(
        tmp_path,
        LiveSettings(record_mix_audio=False),
        {CaptureSource.SYSTEM: adapter},
        scheduler_factory=scheduler_factory,
    )
    session.subscribe(events.append)
    session.start()
    scheduler.fail()

    assert session.status().active_sources == {CaptureSource.SYSTEM}
    assert events[-1].source is CaptureSource.SYSTEM
    assert events[-1].detail == "decode failed"


def test_startup_permission_event_does_not_leave_source_active(tmp_path):
    session = LiveSession(
        tmp_path,
        LiveSettings(record_mix_audio=False),
        {CaptureSource.SYSTEM: StartDeniedAdapter()},
        scheduler_factory=lambda source, on_final, on_partial, on_error: FakeScheduler(),
    )

    session.start()

    assert session.status().state is CaptureState.FAILED
    assert session.status().active_sources == set()
