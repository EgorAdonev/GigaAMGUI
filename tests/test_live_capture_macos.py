import time

import numpy as np
import pytest

from src.live.types import CaptureEventKind, CaptureSource


class DeniedMacApi:
    def devices(self, source):
        return []

    def start(self, source, device_id, callback):
        raise PermissionError("Screen Recording denied")

    def pause(self):
        pass

    def stop(self):
        pass


class TccFailureMacApi(DeniedMacApi):
    def start(self, source, device_id, callback):
        raise RuntimeError("Screen Recording permission was denied by TCC")


class CallbackMacApi(DeniedMacApi):
    def start(self, source, device_id, callback):
        callback(np.ones((2, 2), dtype=np.float32), 123, 48_000)


def wait_until(predicate):
    end = time.monotonic() + 1
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_macos_permission_denial_emits_event_without_chunk():
    from src.live.capture.macos import MacSystemAudioAdapter

    events = []
    adapter = MacSystemAudioAdapter(api=DeniedMacApi())
    adapter.start(lambda chunk: pytest.fail("denied capture emitted a chunk"), events.append)
    wait_until(lambda: events)
    adapter.stop()

    assert events[-1].kind is CaptureEventKind.PERMISSION_DENIED
    assert events[-1].source is CaptureSource.SYSTEM
    assert "Screen Recording" in events[-1].detail


def test_macos_unavailable_screencapturekit_explains_virtual_device_fallback():
    from src.live.capture.factory import CaptureUnavailable
    from src.live.capture.macos import MacSystemAudioAdapter

    with pytest.raises(CaptureUnavailable, match="macOS 13|virtual audio device"):
        MacSystemAudioAdapter(api_loader=lambda: (_ for _ in ()).throw(ImportError("missing"))).devices()


def test_macos_tcc_error_is_mapped_to_permission_event():
    from src.live.capture.macos import MacSystemAudioAdapter

    events = []
    adapter = MacSystemAudioAdapter(api=TccFailureMacApi())
    adapter.start(lambda chunk: pytest.fail("denied capture emitted a chunk"), events.append)
    wait_until(lambda: events)
    adapter.stop()

    assert events[-1].kind is CaptureEventKind.PERMISSION_DENIED
    assert "Screen Recording" in events[-1].detail


def test_macos_callback_is_delivered_from_worker_with_native_timestamp():
    from src.live.capture.macos import MacSystemAudioAdapter

    chunks = []
    adapter = MacSystemAudioAdapter(api=CallbackMacApi())
    adapter.start(chunks.append, lambda event: pytest.fail(event.detail))
    wait_until(lambda: chunks)
    adapter.stop()

    assert chunks[0].timestamp_ns == 123
    assert chunks[0].sample_rate == 48_000
    assert chunks[0].frames.flags["WRITEABLE"] is False
