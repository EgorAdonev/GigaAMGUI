import numpy as np

from src.live.recorder import SessionRecorder
from src.live.types import CaptureSource, PcmChunk


def chunk(source: CaptureSource, sample_rate: int = 48_000, channels: int = 2) -> PcmChunk:
    return PcmChunk(source, sample_rate, channels, 0, np.ones((3, channels), np.float32), 1)


class Writer:
    def __init__(self, path, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.blocks = []
        self.closed = False

    def write(self, frames):
        self.blocks.append(frames)

    def close(self):
        self.closed = True


def test_recorder_preserves_source_rate_channels_and_selected_artifacts(tmp_path):
    writers = []

    def factory(path, **kwargs):
        writer = Writer(path, **kwargs)
        writers.append(writer)
        return writer

    recorder = SessionRecorder(tmp_path, record_sources=True, record_mix=False, writer_factory=factory)
    recorder.write(chunk(CaptureSource.MIC))
    recorder.write(chunk(CaptureSource.SYSTEM, sample_rate=44_100, channels=1))
    paths = recorder.close()

    assert paths == {
        CaptureSource.MIC: tmp_path / "mic.wav",
        CaptureSource.SYSTEM: tmp_path / "system.wav",
    }
    assert [(writer.kwargs["samplerate"], writer.kwargs["channels"]) for writer in writers] == [
        (48_000, 2),
        (44_100, 1),
    ]
    assert all(writer.closed for writer in writers)


def test_recorder_selects_rf64_before_wav_size_limit(tmp_path):
    formats = []

    def factory(path, **kwargs):
        formats.append(kwargs["format"])
        return Writer(path, **kwargs)

    recorder = SessionRecorder(tmp_path, writer_factory=factory, rf64_limit_bytes=16)
    recorder.write(chunk(CaptureSource.MIC, channels=2))

    assert formats == ["RF64"]
