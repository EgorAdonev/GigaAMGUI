"""Materialize latest finalized transcript revisions as atomic exports."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.core.formatters import generate_srt, generate_vtt

from .types import TranscriptEvent


@dataclass(frozen=True)
class ExportSelection:
    txt: bool = False
    srt: bool = False
    vtt: bool = False
    sample_rate: int = 48_000


def export_session(
    session_dir: Path,
    events: Iterable[TranscriptEvent],
    selection: ExportSelection,
) -> list[Path]:
    session_dir = Path(session_dir)
    finalized = _latest_final_events(events)
    exports: list[tuple[Path, str]] = []
    if selection.txt:
        exports.append((session_dir / "transcript.txt", _format_txt(finalized, selection.sample_rate)))
    utterances = _utterances(finalized, selection.sample_rate)
    if selection.srt:
        exports.append((session_dir / "transcript.srt", generate_srt(utterances)))
    if selection.vtt:
        exports.append((session_dir / "transcript.vtt", generate_vtt(utterances)))
    for path, content in exports:
        _write_atomic(path, content)
    return [path for path, _ in exports]


def _latest_final_events(events: Iterable[TranscriptEvent]) -> list[TranscriptEvent]:
    latest: dict[str, TranscriptEvent] = {}
    for event in events:
        prior = latest.get(event.event_id)
        if prior is None or event.revision >= prior.revision:
            latest[event.event_id] = event
    return sorted(
        (event for event in latest.values() if event.status == "final"),
        key=lambda event: (event.sample_start, event.event_id),
    )


def _format_txt(events: Iterable[TranscriptEvent], sample_rate: int) -> str:
    return "".join(
        f"[{_short_timestamp(event.sample_start / sample_rate)}] {event.source_label}"
        f"{' ' + event.speaker if event.speaker else ''}: {event.text}\n"
        for event in events
    )


def _short_timestamp(seconds: float) -> str:
    minutes, seconds = divmod(seconds, 60)
    return f"{int(minutes):02d}:{seconds:06.3f}"


def _utterances(events: Iterable[TranscriptEvent], sample_rate: int) -> list[dict]:
    return [
        {
            "transcription": f"{event.source_label}: {event.text}",
            "boundaries": (event.sample_start / sample_rate, event.sample_end / sample_rate),
            "speaker": event.speaker,
        }
        for event in events
    ]


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
