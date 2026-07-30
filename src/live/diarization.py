"""Live diarization policy helpers without cross-session identity state."""

from __future__ import annotations

from .types import DiarizationMode, TranscriptEvent

LIVE_ESTIMATE_STABILIZATION_HORIZON_SECONDS = 10


def label_event(event: TranscriptEvent, mode: DiarizationMode) -> TranscriptEvent:
    """Keep source labels stable when diarization is disabled."""
    if mode is DiarizationMode.OFF:
        return event
    return event
