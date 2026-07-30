"""Live-transcription domain contracts independent of Qt and capture backends."""

from .asr import LiveAsrScheduler
from .exports import ExportSelection, export_session
from .journal import EventJournal, LiveSessionStore
from .recorder import SessionRecorder
from .session import LiveSession, LiveStatus, SessionResult
from .types import (
    CaptureDevice,
    CaptureEvent,
    CaptureEventKind,
    CaptureSource,
    CaptureState,
    DiarizationMode,
    LiveSettings,
    PcmChunk,
    TranscriptEvent,
)

__all__ = [
    "CaptureDevice",
    "CaptureEvent",
    "CaptureEventKind",
    "CaptureSource",
    "CaptureState",
    "DiarizationMode",
    "EventJournal",
    "ExportSelection",
    "LiveSettings",
    "LiveAsrScheduler",
    "LiveSession",
    "LiveSessionStore",
    "LiveStatus",
    "PcmChunk",
    "SessionRecorder",
    "SessionResult",
    "TranscriptEvent",
    "export_session",
]
