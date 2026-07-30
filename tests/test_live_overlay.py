import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.gui.live_overlay import LiveOverlay
from src.live.types import CaptureSource, TranscriptEvent


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def overlay(qapp):
    instance = LiveOverlay()
    instance.show()
    yield instance
    instance.close()


def _event(text, status="final", source=CaptureSource.MIC, speaker=None):
    return TranscriptEvent(
        event_id="event-1",
        revision=0,
        source=source,
        sample_start=0,
        sample_end=16000,
        timestamp_ns=0,
        text=text,
        status=status,
        speaker=speaker,
    )


def test_overlay_displays_recent_final_lines_partial_and_metadata(overlay):
    overlay.update_transcript(_event("Final one", speaker="Speaker 1"))
    overlay.update_transcript(_event("Final two", source=CaptureSource.SYSTEM))
    overlay.update_transcript(_event("Still listening", status="partial"))

    assert "Speaker 1" in overlay.final_text.toPlainText()
    assert "MIC" in overlay.final_text.toPlainText()
    assert "SYSTEM" in overlay.final_text.toPlainText()
    assert "[00:00.000]" in overlay.final_text.toPlainText()
    assert overlay.partial_label.text() == "Still listening"


def test_overlay_collapses_hides_and_can_be_dragged(overlay):
    assert overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert overlay.windowFlags() & Qt.WindowType.FramelessWindowHint

    overlay.toggle_collapsed()
    assert overlay.content.isVisible() is False
    overlay.toggle_collapsed()
    assert overlay.content.isVisible() is True

    original = overlay.pos()
    QTest.mousePress(overlay.header, Qt.MouseButton.LeftButton, pos=overlay.header.rect().center())
    QTest.mouseMove(overlay.header, overlay.header.rect().center() + QPoint(40, 40))
    QTest.mouseRelease(overlay.header, Qt.MouseButton.LeftButton, pos=overlay.header.rect().center() + QPoint(40, 40))
    assert overlay.pos() != original

    overlay.close()
    assert overlay.isVisible() is False


def test_overlay_submits_questions_and_hides_answer_card(overlay):
    questions = []
    overlay.question_submitted.connect(questions.append)
    overlay.question_input.setText("What was agreed?")
    overlay.send_button.click()

    overlay.set_answer("The deadline is Friday.")
    assert questions == ["What was agreed?"]
    assert overlay.answer_text.toPlainText() == "The deadline is Friday."
    assert overlay.answer_card.isVisible() is True

    overlay.toggle_answer_visibility()
    assert overlay.answer_card.isVisible() is False
    assert overlay.answer_toggle_button.text() == "Show answer"
