"""Continuous source-native session recording."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import soundfile as sf

from .types import CaptureSource, PcmChunk


class SessionRecorder:
    def __init__(
        self,
        session_dir: Path,
        record_sources: bool | set[CaptureSource] = True,
        record_mix: bool = True,
        writer_factory: Callable[..., Any] = sf.SoundFile,
        rf64_limit_bytes: int = 0xFFFFFFFF,
    ) -> None:
        self._session_dir = Path(session_dir)
        self._record_sources = record_sources
        self._record_mix = record_mix
        self._writer_factory = writer_factory
        self._rf64_limit_bytes = rf64_limit_bytes
        self._writers: dict[CaptureSource | str, Any] = {}
        self._paths: dict[CaptureSource | str, Path] = {}
        self._bytes_written: dict[CaptureSource | str, int] = {}

    def write(self, chunk: PcmChunk) -> None:
        if self._record_sources is True or (
            isinstance(self._record_sources, set) and chunk.source in self._record_sources
        ):
            self._write(chunk.source, chunk, f"{chunk.source.value}.wav")

    def write_mix(self, chunk: PcmChunk) -> None:
        if self._record_mix:
            self._write("mix", chunk, "mix.wav")

    def close(self) -> dict[CaptureSource, Path]:
        for writer in self._writers.values():
            writer.close()
        return {
            source: path
            for source, path in self._paths.items()
            if isinstance(source, CaptureSource)
        }

    def _write(self, track: CaptureSource | str, chunk: PcmChunk, filename: str) -> None:
        writer = self._writers.get(track)
        if writer is None:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            path = self._session_dir / filename
            byte_count = chunk.frames.nbytes
            format_name = "RF64" if byte_count > self._rf64_limit_bytes else "WAV"
            writer = self._writer_factory(
                path,
                mode="w",
                samplerate=chunk.sample_rate,
                channels=chunk.channels,
                format=format_name,
                subtype="FLOAT",
            )
            self._writers[track] = writer
            self._paths[track] = path
            self._bytes_written[track] = 0
        writer.write(chunk.frames)
        self._bytes_written[track] += chunk.frames.nbytes
