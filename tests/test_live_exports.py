from src.live.exports import ExportSelection, export_session
from src.live.types import CaptureSource, TranscriptEvent


def event(
    event_id: str,
    revision: int,
    text: str,
    status: str = "final",
    sample_start: int = 0,
) -> TranscriptEvent:
    return TranscriptEvent(
        event_id=event_id,
        revision=revision,
        source=CaptureSource.MIC,
        sample_start=sample_start,
        sample_end=sample_start + 48_000,
        timestamp_ns=1,
        text=text,
        status=status,
        speaker="Speaker 1",
        supersedes=revision - 1 if revision else None,
    )


def test_export_is_atomic_and_uses_only_latest_final_events(tmp_path):
    paths = export_session(
        tmp_path,
        [event("one", 0, "draft"), event("one", 1, "one"), event("two", 0, "two", "partial")],
        ExportSelection(txt=True),
    )

    assert paths == [tmp_path / "transcript.txt"]
    assert paths[0].read_text(encoding="utf-8") == "[00:00.000] MIC Speaker 1: one\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_subtitle_exports_sort_revisions_and_renumber_cues(tmp_path):
    paths = export_session(
        tmp_path,
        [event("second", 0, "second", sample_start=96_000), event("first", 0, "old"), event("first", 1, "first")],
        ExportSelection(srt=True, vtt=True),
    )

    srt, vtt = (path.read_text(encoding="utf-8") for path in paths)
    assert "1\n00:00:00,000 --> 00:00:01,000\n<Speaker 1> MIC: first" in srt
    assert "2\n00:00:02,000 --> 00:00:03,000\n<Speaker 1> MIC: second" in srt
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.000\n<v Speaker 1>MIC: first" in vtt
