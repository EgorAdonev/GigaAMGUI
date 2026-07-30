import os
import sys
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

sys.modules.setdefault("gigaam", types.SimpleNamespace(load_model=lambda *args, **kwargs: object()))
sys.modules.setdefault("yt_dlp", types.SimpleNamespace(YoutubeDL=object))

from src.gui.app_qt import GigaTranscriberQtApp  # noqa: E402
from src.live.types import CaptureSource, TranscriptEvent  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_gui_config(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGAAM_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    instance = GigaTranscriberQtApp()
    yield instance
    instance.close()


def test_live_source_disables_unselected_track_without_clearing_it(window):
    window.combo_live_source.setCurrentIndex(window.combo_live_source.findData("both"))
    window.combo_live_source.setCurrentIndex(window.combo_live_source.findData("mic"))

    assert window.cb_live_mic_audio.isEnabled() is True
    assert window.cb_live_system_audio.isEnabled() is False
    assert window.cb_live_system_audio.isChecked() is True


def test_live_start_passes_exact_selected_audio_tracks_to_session(window, tmp_path, monkeypatch):
    from src.live.capture.noop import NoOpCaptureAdapter

    monkeypatch.setattr(
        "src.gui.live_mixin.create_capture_adapter",
        lambda platform, source, device_id: NoOpCaptureAdapter(source, device_id),
    )
    window.combo_live_source.setCurrentIndex(window.combo_live_source.findData("both"))
    window.cb_live_mic_audio.setChecked(False)
    window.cb_live_system_audio.setChecked(True)
    window.live_output_dir.setText(str(tmp_path))

    window._start_live_session()

    assert window.live_session._settings.record_mic_audio is False
    assert window.live_session._settings.record_system_audio is True


def test_live_settings_persist_across_windows(qapp, tmp_path):
    first = GigaTranscriberQtApp()
    first.combo_live_source.setCurrentIndex(first.combo_live_source.findData("both"))
    first.combo_live_system_device.setCurrentIndex(first.combo_live_system_device.findData("system-default"))
    first.cb_live_export_txt.setChecked(False)
    first.live_output_dir.setText(str(tmp_path / "sessions"))
    first._save_live_settings()
    first.close()

    restored = GigaTranscriberQtApp()
    try:
        assert restored.combo_live_source.currentData() == "both"
        assert restored.combo_live_system_device.currentData() == "system-default"
        assert restored.cb_live_export_txt.isChecked() is False
        assert restored.live_output_dir.text() == str(tmp_path / "sessions")
    finally:
        restored.close()


def test_live_controls_drive_injected_capture_session_lifecycle(window, tmp_path, monkeypatch):
    from src.live.capture.noop import NoOpCaptureAdapter

    monkeypatch.setattr(
        "src.gui.live_mixin.create_capture_adapter",
        lambda platform, source, device_id: NoOpCaptureAdapter(source, device_id),
    )
    window.live_output_dir.setText(str(tmp_path))

    window._start_live_session()
    assert window.live_session.status().state.value == "recording"
    assert window.btn_live_start.isEnabled() is False
    assert window.btn_live_pause.isEnabled() is True
    assert window.btn_live_stop.isEnabled() is True

    window._pause_live_session()
    assert window.live_session.status().state.value == "paused"
    assert window.btn_live_pause.isEnabled() is False

    window._stop_live_session()
    assert window.live_session.status().state.value == "stopped"
    assert window.btn_live_start.isEnabled() is True
    assert window.btn_live_stop.isEnabled() is False


def test_live_overlay_receives_transcript_events_and_hides_without_destroying(window):
    window._show_live_overlay()
    event = TranscriptEvent(
        event_id="event-1",
        revision=0,
        source=CaptureSource.MIC,
        sample_start=0,
        sample_end=16000,
        timestamp_ns=0,
        text="Final line",
        status="final",
        speaker="Speaker 1",
    )

    window.signals.live_event.emit(event)

    assert window.live_overlay.isVisible() is True
    assert "Final line" in window.live_overlay.final_text.toPlainText()
    window.live_overlay.close()
    assert window.live_overlay.isVisible() is False
    assert window.live_overlay is not None


def test_live_overlay_reports_missing_llm_configuration_without_blocking(window, tmp_path, monkeypatch):
    from src.live.capture.noop import NoOpCaptureAdapter

    monkeypatch.setattr(
        "src.gui.live_mixin.create_capture_adapter",
        lambda platform, source, device_id: NoOpCaptureAdapter(source, device_id),
    )
    window.live_output_dir.setText(str(tmp_path))
    window._start_live_session()
    window.live_session._on_final(TranscriptEvent(
        event_id="event-1",
        revision=0,
        source=CaptureSource.MIC,
        sample_start=0,
        sample_end=16000,
        timestamp_ns=1_000_000_000,
        text="Final line",
        status="final",
    ))
    window._show_live_overlay()
    window.live_overlay.question_input.setText("What was said?")
    window.live_overlay.send_button.click()

    assert window.live_overlay.answer_text.toPlainText().startswith("LLM is not configured:")
    assert window.live_overlay.send_button.isEnabled() is True
