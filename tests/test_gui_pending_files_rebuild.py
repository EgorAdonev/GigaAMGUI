import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PyQt6 = pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from src.gui.app_qt import GigaTranscriberQtApp  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_gui_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    win = GigaTranscriberQtApp()
    yield win
    win.close()
    app.processEvents()


def test_rebuild_pending_audio_files_skips_already_transcribed(tmp_path, window):
    input_dir = tmp_path / "audio"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (input_dir / "done.wav").write_bytes(b"")
    (input_dir / "new.wav").write_bytes(b"")
    (output_dir / "done.txt").write_text("transcript")

    window.input_dir = str(input_dir)
    window.output_dir = str(output_dir)
    window.output_formats["txt"] = True

    window._rebuild_pending_audio_files()

    assert window.files_to_process == [str(input_dir / "new.wav")]


def test_rebuild_pending_audio_files_no_output_dir_keeps_all(tmp_path, window):
    input_dir = tmp_path / "audio"
    input_dir.mkdir()
    (input_dir / "a.wav").write_bytes(b"")
    (input_dir / "b.mp3").write_bytes(b"")

    window.input_dir = str(input_dir)
    window.output_dir = ""

    window._rebuild_pending_audio_files()

    assert sorted(window.files_to_process) == sorted(
        [str(input_dir / "a.wav"), str(input_dir / "b.mp3")]
    )


def test_rebuild_pending_audio_files_missing_folder_is_empty(tmp_path, window):
    window.input_dir = str(tmp_path / "does-not-exist")
    window._rebuild_pending_audio_files()
    assert window.files_to_process == []


def test_rebuild_pending_llm_transcripts_skips_already_processed(tmp_path, window):
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "meeting.txt").write_text("text")
    (transcript_dir / "other.txt").write_text("text")
    (transcript_dir / "meeting_llm_summary.txt").write_text("summary")

    window.llm_transcript_dir = str(transcript_dir)
    window.llm_output_dir = str(transcript_dir)
    for key, cb in window.llm_action_checkboxes.items():
        cb.setChecked(key == "summary")
    for key, cb in window.llm_export_checkboxes.items():
        cb.setChecked(key == "txt")

    window._rebuild_pending_llm_transcripts()

    assert window.transcript_files_for_llm == [str(transcript_dir / "other.txt")]


def test_rebuild_pending_llm_transcripts_ignores_llm_output_files(tmp_path, window):
    transcript_dir = tmp_path / "transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "note.txt").write_text("text")
    (transcript_dir / "note_llm_tasks.txt").write_text("tasks")

    window.llm_transcript_dir = str(transcript_dir)
    window.llm_output_dir = str(transcript_dir)
    for cb in window.llm_action_checkboxes.values():
        cb.setChecked(False)
    for cb in window.llm_export_checkboxes.values():
        cb.setChecked(False)

    window._rebuild_pending_llm_transcripts()

    assert window.transcript_files_for_llm == [str(transcript_dir / "note.txt")]
