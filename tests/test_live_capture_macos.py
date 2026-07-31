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


def test_macos_shareable_content_completion_returns_none():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    class ShareableContent:
        @staticmethod
        def getShareableContentWithCompletionHandler_(handler):
            assert handler("content", None) is None

    class ScreenCaptureKit:
        SCShareableContent = ShareableContent

    capture = _ScreenCaptureKitCapture(None, None, None, ScreenCaptureKit)

    assert capture._shareable_content() == "content"


def test_macos_system_audio_copies_cmblockbuffer_bytes_before_numpy_conversion():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    pcm = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    delivered = []

    class AVFoundation:
        @staticmethod
        def CMSampleBufferGetDataBuffer(_sample_buffer):
            return "block"

    class CoreMedia:
        @staticmethod
        def CMBlockBufferGetDataLength(block):
            assert block == "block"
            return pcm.nbytes

        @staticmethod
        def CMBlockBufferCopyDataBytes(block, offset, length, destination):
            assert (block, offset, length) == ("block", 0, pcm.nbytes)
            assert destination is None
            return 0, pcm.tobytes()

    capture = _ScreenCaptureKitCapture(AVFoundation, CoreMedia, None, None)
    capture._deliver_audio(object(), lambda frames, timestamp, rate: delivered.append((frames, timestamp, rate)))

    np.testing.assert_array_equal(delivered[0][0], pcm)
    assert delivered[0][1:] == (None, 48_000)


def test_macos_system_audio_ignores_empty_cmblockbuffer_callback():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    class AVFoundation:
        @staticmethod
        def CMSampleBufferGetDataBuffer(_sample_buffer):
            return "block"

    class CoreMedia:
        @staticmethod
        def CMBlockBufferGetDataLength(_block):
            return 0

    capture = _ScreenCaptureKitCapture(AVFoundation, CoreMedia, None, None)
    errors = []
    capture.set_error_handler(errors.append)

    capture._deliver_audio(object(), lambda *_args: pytest.fail("empty callback delivered audio"))

    assert errors == []


def test_macos_system_audio_ignores_callback_without_a_data_buffer():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    class AVFoundation:
        @staticmethod
        def CMSampleBufferGetDataBuffer(_sample_buffer):
            return None

    capture = _ScreenCaptureKitCapture(AVFoundation, None, None, None)
    errors = []
    capture.set_error_handler(errors.append)

    capture._deliver_audio(object(), lambda *_args: pytest.fail("empty callback delivered audio"))

    assert errors == []


def test_macos_system_audio_reports_one_persistent_copy_failure():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    class AVFoundation:
        @staticmethod
        def CMSampleBufferGetDataBuffer(_sample_buffer):
            return "block"

    class CoreMedia:
        @staticmethod
        def CMBlockBufferGetDataLength(_block):
            return 8

        @staticmethod
        def CMBlockBufferCopyDataBytes(_block, _offset, _length, destination):
            assert destination is None
            return -12704, b""

    capture = _ScreenCaptureKitCapture(AVFoundation, CoreMedia, None, None)
    errors = []
    capture.set_error_handler(errors.append)

    for _ in range(3):
        capture._deliver_audio(object(), lambda *_args: pytest.fail("invalid buffer delivered audio"))

    assert len(errors) == 1
    assert "copy failed (OSStatus -12704)" in str(errors[0])


def test_macos_system_audio_reports_one_persistent_malformed_buffer():
    from src.live.capture.macos import _ScreenCaptureKitCapture

    class AVFoundation:
        @staticmethod
        def CMSampleBufferGetDataBuffer(_sample_buffer):
            return "block"

    class CoreMedia:
        @staticmethod
        def CMBlockBufferGetDataLength(_block):
            return 8

        @staticmethod
        def CMBlockBufferCopyDataBytes(_block, _offset, _length, _destination):
            return 0, b"\x00"

    capture = _ScreenCaptureKitCapture(AVFoundation, CoreMedia, None, None)
    errors = []
    capture.set_error_handler(errors.append)

    for _ in range(3):
        capture._deliver_audio(object(), lambda *_args: pytest.fail("malformed buffer delivered audio"))

    assert len(errors) == 1
    assert "returned 1 bytes; expected 8 bytes" in str(errors[0])


def test_macos_screen_capture_delegate_uses_objective_c_superclass_initializer():
    Foundation = pytest.importorskip("Foundation")

    from src.live.capture.macos import _ScreenCaptureKitCapture

    class Content:
        @staticmethod
        def displays():
            return [object()]

    class ShareableContent:
        @staticmethod
        def getShareableContentWithCompletionHandler_(handler):
            handler(Content(), None)

    class Configuration:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def setCapturesAudio_(self, _value):
            pass

        def setSampleRate_(self, _value):
            pass

        def setChannelCount_(self, _value):
            pass

    class ContentFilter:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithDisplay_excludingWindows_(self, _display, _windows):
            return self

    class Stream:
        @classmethod
        def alloc(cls):
            return cls()

        def initWithFilter_configuration_delegate_(self, _filter, _configuration, _delegate):
            return self

        def addStreamOutput_type_sampleHandlerQueue_error_(self, _output, _output_type, _queue, _error):
            return True

        def startCaptureWithCompletionHandler_(self, handler):
            handler(None)

    class ScreenCaptureKit:
        SCShareableContent = ShareableContent
        SCStreamConfiguration = Configuration
        SCContentFilter = ContentFilter
        SCStream = Stream
        SCStreamOutputTypeAudio = 1

    capture = _ScreenCaptureKitCapture(None, None, Foundation, ScreenCaptureKit)

    capture.start(CaptureSource.SYSTEM, None, lambda *_args: None)
