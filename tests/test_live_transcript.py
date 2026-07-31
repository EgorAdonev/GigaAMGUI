from src.gui.live_transcript import LiveTranscriptPresenter
from src.live.types import CaptureSource, TranscriptEvent


def _event(
    text: str,
    *,
    event_id: str = "event",
    source: CaptureSource = CaptureSource.MIC,
    speaker: str | None = None,
    sample_start: int = 0,
    sample_end: int = 16_000,
    paragraph_break_after: bool = False,
) -> TranscriptEvent:
    return TranscriptEvent(
        event_id=event_id,
        revision=0,
        source=source,
        sample_start=sample_start,
        sample_end=sample_end,
        timestamp_ns=0,
        text=text,
        status="final",
        speaker=speaker,
        paragraph_break_after=paragraph_break_after,
    )


def test_presenter_completes_a_sentence_from_multiple_finalized_phrases():
    presenter = LiveTranscriptPresenter()

    assert presenter.add_final(_event("First part", event_id="one")) is False
    assert presenter.paragraphs == []
    assert presenter.add_final(_event(" of the sentence.", event_id="two")) is True

    paragraph = presenter.paragraphs[0]
    assert paragraph.sentences == ["First part of the sentence."]
    assert paragraph.source_label == "MIC"
    assert paragraph.speaker is None


def test_presenter_keeps_incomplete_sentence_active_until_later_completion():
    presenter = LiveTranscriptPresenter()

    presenter.add_final(_event("Unfinished words", event_id="one"))
    presenter.add_final(_event(" continue", event_id="two"))

    assert presenter.paragraphs == []
    assert presenter.active_text == "Unfinished words continue"


def test_presenter_starts_paragraphs_for_metadata_gap_and_sentence_limit():
    presenter = LiveTranscriptPresenter(long_gap_samples=16_000)

    for number in range(3):
        start = number * 16_000
        presenter.add_final(_event(f"Sentence {number}.", event_id=str(number), sample_start=start, sample_end=start + 1))
    presenter.add_final(_event("Fourth sentence.", event_id="four", sample_start=48_000, sample_end=48_001))
    presenter.add_final(_event("Other speaker.", event_id="speaker", speaker="Speaker 2", sample_start=48_001, sample_end=48_002))
    presenter.add_final(_event("After gap.", event_id="gap", speaker="Speaker 2", sample_start=64_003, sample_end=64_004))

    assert [paragraph.sentences for paragraph in presenter.paragraphs] == [
        ["Sentence 0.", "Sentence 1.", "Sentence 2."],
        ["Fourth sentence."],
        ["Other speaker."],
        ["After gap."],
    ]
    assert presenter.paragraphs[2].speaker == "Speaker 2"


def test_presenter_starts_a_new_paragraph_after_a_silence_finalized_phrase():
    presenter = LiveTranscriptPresenter()

    presenter.add_final(_event("First phrase.", event_id="one", paragraph_break_after=True))
    presenter.add_final(_event("Second phrase.", event_id="two", sample_start=16_000))

    assert [paragraph.sentences for paragraph in presenter.paragraphs] == [
        ["First phrase."],
        ["Second phrase."],
    ]
