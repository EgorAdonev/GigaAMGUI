"""No-op capture adapter used until a platform adapter is installed."""

from __future__ import annotations

from collections.abc import Callable

from ..types import CaptureDevice, CaptureEvent, CaptureSource, PcmChunk


class NoOpCaptureAdapter:
    """Expose a selectable source without requesting audio permissions."""

    def __init__(self, source: CaptureSource, device_id: str | None = None) -> None:
        self.source = source
        self.device_id = device_id or f"{source.value}-default"
        self.is_started = False
        self.is_paused = False

    def start(
        self,
        on_chunk: Callable[[PcmChunk], None],
        on_event: Callable[[CaptureEvent], None],
    ) -> None:
        self.is_started = True
        self.is_paused = False

    def pause(self) -> None:
        self.is_paused = True

    def stop(self) -> None:
        self.is_started = False
        self.is_paused = False

    def devices(self) -> list[CaptureDevice]:
        name = "Default microphone" if self.source is CaptureSource.MIC else "System audio"
        return [CaptureDevice(self.device_id, name, self.source, 48_000, 1, True)]
