"""Windows WASAPI capture adapters backed by optional PyAudioWPatch."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from ..types import CaptureSource
from .common import NativeCaptureApi, QueuedCaptureAdapter
from .factory import CaptureUnavailable


def _load_windows_api() -> NativeCaptureApi:
    try:
        import pyaudiowpatch as pyaudio
    except ImportError as exc:
        raise CaptureUnavailable("Windows live capture requires PyAudioWPatch. Install requirements-live-windows.txt.") from exc
    return _PyAudioWASAPI(pyaudio)


class _PyAudioWASAPI:
    def __init__(self, pyaudio: Any) -> None:
        self._pyaudio = pyaudio
        self._audio = pyaudio.PyAudio()
        self._stream: Any = None

    def devices(self, source: CaptureSource) -> list[dict[str, Any]]:
        devices = []
        for index in range(self._audio.get_device_count()):
            info = self._audio.get_device_info_by_index(index)
            loopback = bool(info.get("isLoopbackDevice", False))
            if (source is CaptureSource.SYSTEM) != loopback or info.get("maxInputChannels", 0) <= 0:
                continue
            devices.append(
                {
                    "id": str(index),
                    "name": info["name"],
                    "sample_rate": int(info["defaultSampleRate"]),
                    "channels": int(info["maxInputChannels"]),
                    "is_default": index == self._audio.get_default_input_device_info()["index"],
                }
            )
        return devices

    def start(self, source: CaptureSource, device_id: str | None, callback: Callable[..., None]) -> None:
        devices = self.devices(source)
        selected = next((item for item in devices if item["id"] == device_id), None) if device_id else next(
            (item for item in devices if item["is_default"]), devices[0] if devices else None
        )
        if selected is None:
            raise OSError("No WASAPI microphone or loopback device is available")

        def on_audio(data: bytes, frame_count: int, _time_info: Any, _status: Any) -> tuple[None, int]:
            frames = np.frombuffer(data, dtype=np.float32).reshape(frame_count, selected["channels"])
            callback(frames, None, selected["sample_rate"])
            return None, self._pyaudio.paContinue

        self._stream = self._audio.open(
            format=self._pyaudio.paFloat32,
            channels=selected["channels"],
            rate=selected["sample_rate"],
            input=True,
            input_device_index=int(selected["id"]),
            stream_callback=on_audio,
        )
        self._stream.start_stream()

    def pause(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()

    def resume(self) -> None:
        if self._stream is not None:
            self._stream.start_stream()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        self._audio.terminate()


class _WindowsAdapter(QueuedCaptureAdapter):
    def __init__(
        self,
        source: CaptureSource,
        device_id: str | None = None,
        *,
        api: NativeCaptureApi | None = None,
        api_loader: Callable[[], NativeCaptureApi] = _load_windows_api,
    ) -> None:
        super().__init__(source, api, device_id, api_loader=api_loader)

    def _native_api(self) -> NativeCaptureApi:
        try:
            return super()._native_api()
        except ImportError as exc:
            raise CaptureUnavailable(
                "Windows live capture requires PyAudioWPatch. Install requirements-live-windows.txt."
            ) from exc


class WindowsMicrophoneAdapter(_WindowsAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(CaptureSource.MIC, device_id, **kwargs)


class WindowsSystemAudioAdapter(_WindowsAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(CaptureSource.SYSTEM, device_id, **kwargs)
