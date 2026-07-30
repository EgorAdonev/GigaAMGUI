"""Protocol implemented by optional platform capture adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from ..types import CaptureDevice, CaptureEvent, PcmChunk


@runtime_checkable
class CaptureAdapter(Protocol):
    def start(
        self,
        on_chunk: Callable[[PcmChunk], None],
        on_event: Callable[[CaptureEvent], None],
    ) -> None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def devices(self) -> list[CaptureDevice]: ...
