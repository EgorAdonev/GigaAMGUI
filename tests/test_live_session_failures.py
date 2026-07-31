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


def source_chunk(source, *, offset=0, timestamp_ns=1, frame_count=4_800):
    return PcmChunk(
        source, 48_000, 1, offset,
        np.ones((frame_count, 1), dtype=np.float32), timestamp_ns,
    )


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


def test_mix_failure_is_throttled_without_stopping_source_recording_or_asr(tmp_path):
    class RecordingScheduler(FakeScheduler):
        def __init__(self):
            super().__init__()
            self.submitted = []

        def submit(self, chunk):
            self.submitted.append(chunk)

    class FailingMixRecorder:
        def __init__(self, *args):
            self.written = []

        def write(self, chunk):
            self.written.append(chunk)

        def write_mix(self, chunk):
            raise RuntimeError("mix writer failed")

        def close(self):
            return {}

    mic = FakeAdapter()
    system = FakeAdapter()
    schedulers = {}
    updates = []

    def scheduler_factory(source, on_final, on_partial, on_error):
        scheduler = RecordingScheduler()
        schedulers[source] = scheduler
        return scheduler

    session = LiveSession(
        tmp_path,
        LiveSettings(record_mix_audio=True),
        {CaptureSource.MIC: mic, CaptureSource.SYSTEM: system},
        scheduler_factory=scheduler_factory,
        recorder_factory=FailingMixRecorder,
    )
    session.subscribe(updates.append)
    session.start()
    mic.emit(source_chunk(CaptureSource.MIC, timestamp_ns=1))
    system.emit(source_chunk(CaptureSource.SYSTEM, timestamp_ns=1))
    mic.emit(source_chunk(CaptureSource.MIC, offset=4_800, timestamp_ns=1))
    system.emit(source_chunk(CaptureSource.SYSTEM, offset=4_800, timestamp_ns=1))

    assert len(schedulers[CaptureSource.MIC].submitted) == 2
    assert len(schedulers[CaptureSource.SYSTEM].submitted) == 2
    assert session.status().active_sources == {CaptureSource.MIC, CaptureSource.SYSTEM}
    assert [event.detail for event in updates if isinstance(event, CaptureEvent)] == [
        "Mix recording unavailable: mix writer failed"
    ]


def test_staggered_source_callbacks_produce_timestamp_aligned_mix(tmp_path):
    class CollectingRecorder:
        def __init__(self, *args):
            self.mixes = []

        def write(self, chunk):
            return None

        def write_mix(self, chunk):
            self.mixes.append(chunk)

        def close(self):
            return {}

    mic = FakeAdapter()
    system = FakeAdapter()
    recorders = []

    def recorder_factory(*args):
        recorder = CollectingRecorder(*args)
        recorders.append(recorder)
        return recorder

    session = LiveSession(
        tmp_path,
        LiveSettings(record_mix_audio=True),
        {CaptureSource.MIC: mic, CaptureSource.SYSTEM: system},
        scheduler_factory=lambda source, on_final, on_partial, on_error: FakeScheduler(),
        recorder_factory=recorder_factory,
    )
    session.start()
    mic.emit(source_chunk(CaptureSource.MIC, offset=100, timestamp_ns=1_000_000_000, frame_count=4))
    system.emit(source_chunk(CaptureSource.SYSTEM, offset=200, timestamp_ns=1_000_041_667, frame_count=2))

    assert len(recorders[0].mixes) == 1
    assert recorders[0].mixes[0].frames.shape == (4, 1)
