import time

import numpy as np
import pytest

from src.live.types import CaptureEventKind, CaptureSource


class RemovedLinuxApi:
    def devices(self, source):
        return [{"id": "monitor-1", "name": "Built-in Monitor", "sample_rate": 48_000, "channels": 2, "is_default": True}]

    def start(self, source, device_id, callback):
        raise OSError("device removed")

    def pause(self):
        pass

    def stop(self):
        pass


def wait_until(predicate):
    end = time.monotonic() + 1
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_linux_monitor_device_is_enumerated_without_starting_capture():
    from src.live.capture.linux import LinuxSystemAudioAdapter

    adapter = LinuxSystemAudioAdapter(api=RemovedLinuxApi())

    assert adapter.devices()[0].id == "monitor-1"


def test_linux_removed_device_emits_source_local_event():
    from src.live.capture.linux import LinuxSystemAudioAdapter

    events = []
    adapter = LinuxSystemAudioAdapter(api=RemovedLinuxApi())
    adapter.start(lambda chunk: None, events.append)
    wait_until(lambda: events)
    adapter.stop()

    assert events[-1].kind is CaptureEventKind.DEVICE_REMOVED
    assert events[-1].source is CaptureSource.SYSTEM


def test_linux_missing_gstreamer_has_monitor_setup_instructions():
    from src.live.capture.factory import CaptureUnavailable
    from src.live.capture.linux import LinuxSystemAudioAdapter

    with pytest.raises(CaptureUnavailable, match="PipeWire|PulseAudio"):
        LinuxSystemAudioAdapter(api_loader=lambda: (_ for _ in ()).throw(ImportError("missing"))).devices()


class FakeSoundDevice:
    def __init__(self):
        self.started = []

    def query_devices(self):
        return [
            {"name": "USB microphone", "max_input_channels": 1, "default_samplerate": 44_100},
            {"name": "Monitor of Built-in Audio", "max_input_channels": 2, "default_samplerate": 48_000},
            {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48_000},
        ]

    def InputStream(self, **kwargs):
        self.started.append(kwargs)

        class Stream:
            def start(self):
                kwargs["callback"](np.ones((3, kwargs["channels"]), dtype=np.float32), 3, None, None)

            def stop(self):
                pass

            def close(self):
                pass

        return Stream()


def test_linux_sounddevice_selects_monitor_and_delivers_float32_frames():
    from src.live.capture.linux import SoundDeviceCapture

    native = SoundDeviceCapture(FakeSoundDevice())
    devices = native.devices(CaptureSource.SYSTEM)
    frames = []

    native.start(CaptureSource.SYSTEM, devices[0]["id"], lambda data, timestamp_ns, rate: frames.append((data, timestamp_ns, rate)))

    assert [device["name"] for device in devices] == ["Monitor of Built-in Audio"]
    assert frames[0][0].dtype == np.float32
    assert frames[0][0].shape == (3, 2)
    assert frames[0][1] is None
    assert frames[0][2] == 48_000


def test_linux_system_capture_rejects_missing_monitor_source():
    from src.live.capture.factory import CaptureUnavailable
    from src.live.capture.linux import SoundDeviceCapture

    native = SoundDeviceCapture(FakeSoundDevice())
    native._sounddevice.query_devices = lambda: [{"name": "USB microphone", "max_input_channels": 1, "default_samplerate": 48_000}]

    with pytest.raises(CaptureUnavailable, match="monitor source"):
        native.start(CaptureSource.SYSTEM, None, lambda *_: None)
