"""Linux PipeWire/PulseAudio monitor-source adapter entry points."""

from __future__ import annotations

from collections.abc import Callable

from ..types import CaptureSource
from .common import NativeCaptureApi, QueuedCaptureAdapter, SoundDeviceCapture
from .factory import CaptureUnavailable


def _load_linux_api() -> NativeCaptureApi:
    try:
        import sounddevice
    except ImportError as exc:
        raise CaptureUnavailable(
            "Linux live capture requires sounddevice. Install requirements-live-linux.txt; "
            "for system audio configure a PipeWire/PulseAudio monitor source."
        ) from exc
    return SoundDeviceCapture(sounddevice)


class _LinuxAdapter(QueuedCaptureAdapter):
    def __init__(
        self,
        source: CaptureSource,
        device_id: str | None = None,
        *,
        api: NativeCaptureApi | None = None,
        api_loader: Callable[[], NativeCaptureApi] = _load_linux_api,
    ) -> None:
        super().__init__(source, api, device_id, api_loader=api_loader)


class LinuxMicrophoneAdapter(_LinuxAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: object) -> None:
        super().__init__(CaptureSource.MIC, device_id, **kwargs)


class LinuxSystemAudioAdapter(_LinuxAdapter):
    def __init__(self, device_id: str | None = None, **kwargs: object) -> None:
        super().__init__(CaptureSource.SYSTEM, device_id, **kwargs)
