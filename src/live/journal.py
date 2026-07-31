"""Recoverable session metadata and append-only transcript revisions."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from src.utils.atomic_json import save_json_atomic

from .types import CaptureSource, LiveSettings, TranscriptEvent


class LiveSessionStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)

    def create(self, settings: LiveSettings) -> Path:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        session_dir = self._root_dir / f"session-{uuid4().hex}"
        session_dir.mkdir()
        metadata = asdict(settings)
        metadata["diarization_mode"] = settings.diarization_mode.value
        save_json_atomic(str(session_dir / "metadata.json"), metadata)
        return session_dir

    def write_checkpoint(self, session_dir: Path, checkpoint: dict) -> None:
        save_json_atomic(str(Path(session_dir) / "checkpoint.json"), checkpoint)

    def update_metadata(self, session_dir: Path, **values: object) -> None:
        path = Path(session_dir) / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata.update(values)
        save_json_atomic(str(path), metadata)


class EventJournal:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def append(self, event: TranscriptEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(event)
        payload.pop("source_label", None)
        payload["source"] = event.source.value
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")
            file.flush()

    def latest_events(self) -> list[TranscriptEvent]:
        latest: dict[str, TranscriptEvent] = {}
        if not self._path.exists():
            return []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            data["source"] = CaptureSource(data["source"])
            event = TranscriptEvent(**data)
            prior = latest.get(event.event_id)
            if prior is None or event.revision >= prior.revision:
                latest[event.event_id] = event
        return list(latest.values())


class ConversationJournal:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def append(self, turn) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": turn.id,
            "question": turn.question,
            "answer": turn.answer,
            "status": turn.status,
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")
            file.flush()

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)
