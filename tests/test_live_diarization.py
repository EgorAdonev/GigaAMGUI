from src.live.diarization import label_event
from src.live.types import CaptureSource, DiarizationMode, TranscriptEvent


def test_off_mode_keeps_stable_source_label():
    event = TranscriptEvent("mic-0", 0, CaptureSource.MIC, 0, 16_000, 1, "hello", "final")

    labeled = label_event(event, DiarizationMode.OFF)

    assert labeled.source_label == "MIC"
    assert labeled.speaker is None
