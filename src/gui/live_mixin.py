"""Live-tab settings and Qt-facing capture session controller."""

from __future__ import annotations

import threading
import sys
from pathlib import Path

from ..live.capture.factory import create_capture_adapter
from ..live.exports import ExportSelection
from ..live.session import LiveSession, LiveStatus
from ..live.types import CaptureSource, CaptureState, DiarizationMode, LiveSettings, TranscriptEvent
from .live_overlay import LiveOverlay


class _NoOpScheduler:
    def submit(self, chunk) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class LiveMixin:
    def _init_live_state(self) -> None:
        self.live_session = None
        self.live_overlay = None
        self._live_settings = self.user_settings.get_value("live_settings", {}) or {}

    def _restore_live_settings(self) -> None:
        settings = self._live_settings
        self._set_live_combo_value(self.combo_live_source, settings.get("source", "mic"))
        self._set_live_combo_value(self.combo_live_mic_device, settings.get("mic_device_id"))
        self._set_live_combo_value(self.combo_live_system_device, settings.get("system_device_id"))
        self.cb_live_mic_audio.setChecked(bool(settings.get("record_mic_audio", True)))
        self.cb_live_system_audio.setChecked(bool(settings.get("record_system_audio", True)))
        self.cb_live_export_txt.setChecked(bool(settings.get("export_txt", True)))
        self.cb_live_export_srt.setChecked(bool(settings.get("export_srt", False)))
        self.cb_live_export_vtt.setChecked(bool(settings.get("export_vtt", False)))
        self._set_live_combo_value(self.combo_live_diarization, settings.get("diarization_mode", "off"))
        self.spin_live_gain.setValue(float(settings.get("gain", 1.0)))
        self.live_output_dir.setText(str(settings.get("output_dir", self.output_dir)))
        self._update_live_source_controls()

    @staticmethod
    def _set_live_combo_value(combo, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _save_live_settings(self) -> None:
        self._live_settings = {
            "source": self.combo_live_source.currentData(),
            "mic_device_id": self.combo_live_mic_device.currentData(),
            "system_device_id": self.combo_live_system_device.currentData(),
            "record_mic_audio": self.cb_live_mic_audio.isChecked(),
            "record_system_audio": self.cb_live_system_audio.isChecked(),
            "export_txt": self.cb_live_export_txt.isChecked(),
            "export_srt": self.cb_live_export_srt.isChecked(),
            "export_vtt": self.cb_live_export_vtt.isChecked(),
            "overlay_visible": False,
            "diarization_mode": self.combo_live_diarization.currentData(),
            "gain": self.spin_live_gain.value(),
            "output_dir": self.live_output_dir.text().strip(),
        }
        self.user_settings.set_value("live_settings", self._live_settings)

    def _selected_live_sources(self) -> set[CaptureSource]:
        source = self.combo_live_source.currentData()
        if source == "mic":
            return {CaptureSource.MIC}
        if source == "system":
            return {CaptureSource.SYSTEM}
        return {CaptureSource.MIC, CaptureSource.SYSTEM}

    def _update_live_source_controls(self) -> None:
        sources = self._selected_live_sources()
        self.cb_live_mic_audio.setEnabled(CaptureSource.MIC in sources)
        self.combo_live_mic_device.setEnabled(CaptureSource.MIC in sources)
        self.cb_live_system_audio.setEnabled(CaptureSource.SYSTEM in sources)
        self.combo_live_system_device.setEnabled(CaptureSource.SYSTEM in sources)

    def _start_live_session(self) -> None:
        output_dir = self.live_output_dir.text().strip()
        if not output_dir:
            self.lbl_live_status.setText(self._t("Выберите папку сессий", "Select a session folder"))
            return
        self._save_live_settings()
        sources = self._selected_live_sources()
        settings = LiveSettings(
            mic_device_id=self.combo_live_mic_device.currentData(),
            system_device_id=self.combo_live_system_device.currentData(),
            diarization_mode=DiarizationMode(self.combo_live_diarization.currentData()),
            record_mic_audio=CaptureSource.MIC in sources and self.cb_live_mic_audio.isChecked(),
            record_system_audio=CaptureSource.SYSTEM in sources and self.cb_live_system_audio.isChecked(),
            record_source_audio=any(
                checkbox.isChecked()
                for checkbox in (self.cb_live_mic_audio, self.cb_live_system_audio)
            ),
            record_mix_audio=sources == {CaptureSource.MIC, CaptureSource.SYSTEM},
        )
        adapters = {
            source: create_capture_adapter(
                sys.platform,
                source,
                settings.mic_device_id if source is CaptureSource.MIC else settings.system_device_id,
            )
            for source in sources
        }
        self.live_session = LiveSession(
            Path(output_dir),
            settings,
            adapters,
            scheduler_factory=lambda source, on_final, on_error: _NoOpScheduler(),
            export_selection=ExportSelection(
                txt=self.cb_live_export_txt.isChecked(),
                srt=self.cb_live_export_srt.isChecked(),
                vtt=self.cb_live_export_vtt.isChecked(),
                sample_rate=settings.asr_sample_rate,
            ),
        )
        self.live_session.subscribe(self._on_live_session_update)
        self.live_session.start()

    def _pause_live_session(self) -> None:
        if self.live_session is not None and self.live_session.status().state is CaptureState.RECORDING:
            self.live_session.pause()

    def _stop_live_session(self) -> None:
        if self.live_session is None:
            return
        if self.live_session.status().state in {CaptureState.RECORDING, CaptureState.PAUSED, CaptureState.FAILED}:
            self.signals.live_finished.emit(self.live_session.stop())

    def _on_live_session_update(self, value) -> None:
        if isinstance(value, LiveStatus):
            self.signals.live_status.emit(value)
        else:
            self.signals.live_event.emit(value)

    def _show_live_overlay(self) -> None:
        if self.live_overlay is None:
            self.live_overlay = LiveOverlay(self)
            self.live_overlay.question_submitted.connect(self._answer_live_question)
        self.live_overlay.show()
        self.live_overlay.raise_()

    def _update_live_overlay(self, event) -> None:
        if self.live_overlay is not None and isinstance(event, TranscriptEvent):
            self.live_overlay.update_transcript(event)

    def _answer_live_question(self, question: str) -> None:
        if self.live_session is None:
            self._update_live_answer("error", "Start a live session before asking the assistant.")
            return
        transcript = self.live_session.ask_context()
        if not transcript:
            self._update_live_answer("error", "No final transcript events are available yet.")
            return
        try:
            llm_settings = self._collect_llm_settings()
        except ValueError as exc:
            self._update_live_answer("error", f"LLM is not configured: {exc}")
            return
        threading.Thread(
            target=self._run_live_question,
            args=(llm_settings, transcript, question),
            daemon=True,
        ).start()

    def _run_live_question(self, llm_settings: dict, transcript: str, question: str) -> None:
        try:
            answer = self._run_llm_provider(llm_settings, transcript, question)
        except Exception as exc:
            self.signals.live_answer.emit("error", f"LLM error: {self._compact_llm_error(str(exc))}")
        else:
            self.signals.live_answer.emit("answer", answer)

    def _update_live_answer(self, _status: str, text: str) -> None:
        if self.live_overlay is not None:
            self.live_overlay.set_answer(text)

    def _update_live_status(self, status: LiveStatus) -> None:
        self.lbl_live_status.setText(status.state.value.replace("_", " ").title())
        self._update_live_control_state(status.state)

    def _on_live_finished(self, result) -> None:
        self._last_result_dir = str(result.session_dir)
        self.lbl_live_status.setText(self._t("Сессия сохранена", "Session saved"))
        self._update_live_control_state(CaptureState.STOPPED)

    def _update_live_control_state(self, state: CaptureState | None = None) -> None:
        state = state or (self.live_session.status().state if self.live_session else CaptureState.IDLE)
        self.btn_live_start.setEnabled(state in {CaptureState.IDLE, CaptureState.STOPPED, CaptureState.FAILED})
        self.btn_live_pause.setEnabled(state is CaptureState.RECORDING)
        self.btn_live_stop.setEnabled(state in {CaptureState.RECORDING, CaptureState.PAUSED, CaptureState.FAILED})
