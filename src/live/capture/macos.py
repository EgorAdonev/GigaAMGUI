"""macOS Core Audio and ScreenCaptureKit adapter entry points."""

from __future__ import annotations

from collections.abc import Callable
import platform
from threading import Event
from typing import Any

import numpy as np

from ..types import CaptureSource
from .common import NativeCaptureApi, QueuedCaptureAdapter, SoundDeviceCapture
from .factory import CaptureUnavailable


def _load_macos_microphone_api() -> NativeCaptureApi:
    try:
        import sounddevice
    except ImportError as exc:
        raise CaptureUnavailable(
            "macOS microphone capture requires sounddevice. Install requirements-live-macos.txt "
            "and grant Microphone permission."
        ) from exc
    return SoundDeviceCapture(sounddevice)


def _load_macos_system_api() -> NativeCaptureApi:
    version = platform.mac_ver()[0]
    if version and int(version.split(".", maxsplit=1)[0]) < 13:
        raise CaptureUnavailable(
            "macOS system capture requires macOS 13+ with ScreenCaptureKit. "
            "Upgrade macOS or select a virtual audio device."
        )
    try:
        import AVFoundation
        import CoreMedia
        import Foundation
        import ScreenCaptureKit
    except ImportError as exc:
        raise CaptureUnavailable(
            "macOS system capture requires macOS 13+, PyObjC ScreenCaptureKit, and Screen Recording permission; "
            "install requirements-live-macos.txt or select a virtual audio device."
        ) from exc
    if not hasattr(ScreenCaptureKit, "SCStream"):
        raise CaptureUnavailable(
            "ScreenCaptureKit is unavailable on this macOS version. Upgrade to macOS 13+ "
            "or select a virtual audio device."
        )
    return _ScreenCaptureKitCapture(AVFoundation, CoreMedia, Foundation, ScreenCaptureKit)


class _ScreenCaptureKitCapture:
    """Capture desktop audio with ScreenCaptureKit without importing PyObjC on startup."""

    def __init__(self, avfoundation: Any, coremedia: Any, foundation: Any, screen_capture_kit: Any) -> None:
        self._avfoundation = avfoundation
        self._coremedia = coremedia
        self._foundation = foundation
        self._sck = screen_capture_kit
        self._stream: Any = None
        self._output: Any = None
        self._error_handler: Callable[[Exception], None] | None = None

    def devices(self, source: CaptureSource) -> list[dict[str, Any]]:
        if source is not CaptureSource.SYSTEM:
            return []
        self._shareable_content()
        return [{"id": "default", "name": "Desktop system audio", "sample_rate": 48_000, "channels": 2, "is_default": True}]

    def start(self, source: CaptureSource, _device_id: str | None, callback: Callable[..., None]) -> None:
        if source is not CaptureSource.SYSTEM:
            raise OSError("ScreenCaptureKit only captures system audio")
        content = self._shareable_content()
        displays = list(content.displays())
        if not displays:
            raise OSError("ScreenCaptureKit found no capturable display")
        configuration = self._sck.SCStreamConfiguration.alloc().init()
        configuration.setCapturesAudio_(True)
        configuration.setSampleRate_(48_000)
        configuration.setChannelCount_(2)
        stream_filter = self._sck.SCContentFilter.alloc().initWithDisplay_excludingWindows_(displays[0], [])
        owner = self

        class Output(self._foundation.NSObject):
            def initWithCallback_(self, output_callback: Callable[..., None]) -> Any:
                self = super().init()
                if self is not None:
                    self._callback = output_callback
                return self

            def stream_didOutputSampleBuffer_ofType_(self, _stream: Any, sample_buffer: Any, output_type: Any) -> None:
                if output_type != owner._sck.SCStreamOutputTypeAudio:
                    return
                owner._deliver_audio(sample_buffer, self._callback)

        self._output = Output.alloc().initWithCallback_(callback)
        self._stream = self._sck.SCStream.alloc().initWithFilter_configuration_delegate_(stream_filter, configuration, None)
        add_result = self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._output, self._sck.SCStreamOutputTypeAudio, None, None
        )
        if isinstance(add_result, tuple):
            added, error = add_result
        else:
            added, error = add_result, None
        if not added:
            self._raise_capture_error(error)
        completed = Event()
        result: list[Any] = []
        self._stream.startCaptureWithCompletionHandler_(lambda start_error: (result.append(start_error), completed.set()))
        if not completed.wait(5):
            raise OSError("ScreenCaptureKit did not confirm capture startup")
        if result and result[0]:
            self._raise_capture_error(result[0])

    def pause(self) -> None:
        self.stop()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stopCaptureWithCompletionHandler_(lambda _error: None)
            self._stream = None
        self._output = None

    def set_error_handler(self, handler: Callable[[Exception], None]) -> None:
        self._error_handler = handler

    def _shareable_content(self) -> Any:
        completed = Event()
        result: list[Any] = []
        self._sck.SCShareableContent.getShareableContentWithCompletionHandler_(
            lambda content, error: (result.extend((content, error)), completed.set())
        )
        if not completed.wait(5):
            raise OSError("ScreenCaptureKit did not return shareable content")
        if len(result) != 2 or result[1]:
            self._raise_capture_error(result[1] if len(result) == 2 else "unknown error")
        return result[0]

    def _deliver_audio(self, sample_buffer: Any, callback: Callable[..., None]) -> None:
        try:
            block = self._avfoundation.CMSampleBufferGetDataBuffer(sample_buffer)
            status, _at_offset, length, data = self._coremedia.CMBlockBufferGetDataPointer(block, 0, None, None, None)
            if status != 0 or data is None or length % 8:
                raise OSError("ScreenCaptureKit returned an unreadable audio buffer")
            frames = np.frombuffer(data, dtype=np.float32, count=length // 4).reshape(-1, 2)
            callback(frames, None, 48_000)
        except Exception as exc:
            if self._error_handler is not None:
                self._error_handler(exc)

    @staticmethod
    def _raise_capture_error(error: Any) -> None:
        detail = str(error)
        if any(word in detail.casefold() for word in ("permission", "screen recording", "tcc", "not authorized")):
            raise PermissionError(f"Screen Recording permission denied: {detail}")
        raise OSError(f"ScreenCaptureKit capture failed: {detail}")


class _MacAdapter(QueuedCaptureAdapter):
    def __init__(
        self,
        source: CaptureSource,
        device_id: str | None = None,
        *,
        api: NativeCaptureApi | None = None,
        api_loader: Callable[[], NativeCaptureApi] = _load_macos_system_api,
    ) -> None:
        super().__init__(source, api, device_id, api_loader=api_loader)


class MacMicrophoneAdapter(_MacAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("api_loader", _load_macos_microphone_api)
        super().__init__(CaptureSource.MIC, device_id, **kwargs)


class MacSystemAudioAdapter(_MacAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("api_loader", _load_macos_system_api)
        super().__init__(CaptureSource.SYSTEM, device_id, **kwargs)
