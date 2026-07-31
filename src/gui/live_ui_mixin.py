"""Live-tab widget construction for the desktop application."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LiveUiMixin:
    def _create_live_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(self._px(8), self._px(14), self._px(8), self._px(8))
        layout.setSpacing(self._px(10))

        self.grp_live_source = QGroupBox(self._t("1. Захват в реальном времени", "1. Live capture"))
        source_form = QFormLayout(self.grp_live_source)
        self.combo_live_source = QComboBox()
        self.combo_live_source.addItem(self._t("Микрофон", "Microphone"), "mic")
        self.combo_live_source.addItem(self._t("Системный звук", "System audio"), "system")
        self.combo_live_source.addItem(self._t("Микрофон + системный звук", "Microphone + system audio"), "both")
        self.lbl_live_source = QLabel(self._t("Источник:", "Source:"))
        source_form.addRow(self.lbl_live_source, self.combo_live_source)

        self.combo_live_mic_device = QComboBox()
        self.lbl_live_mic_device = QLabel(self._t("Микрофон:", "Microphone:"))
        source_form.addRow(self.lbl_live_mic_device, self.combo_live_mic_device)
        self.combo_live_system_device = QComboBox()
        self.lbl_live_system_device = QLabel(self._t("Системный звук:", "System audio:"))
        source_form.addRow(self.lbl_live_system_device, self.combo_live_system_device)

        self.cb_live_mic_audio = QCheckBox(self._t("Записывать дорожку микрофона", "Record microphone track"))
        self.cb_live_mic_audio.setChecked(True)
        self.cb_live_system_audio = QCheckBox(self._t("Записывать дорожку системного звука", "Record system audio track"))
        self.cb_live_system_audio.setChecked(True)
        tracks = QWidget()
        tracks_layout = QHBoxLayout(tracks)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.addWidget(self.cb_live_mic_audio)
        tracks_layout.addWidget(self.cb_live_system_audio)
        tracks_layout.addStretch()
        self.lbl_live_tracks = QLabel(self._t("Дорожки:", "Tracks:"))
        source_form.addRow(self.lbl_live_tracks, tracks)

        self.combo_live_diarization = QComboBox()
        self.combo_live_diarization.addItem(self._t("Выключено", "Off"), "off")
        self.combo_live_diarization.addItem(self._t("Оценка в реальном времени", "Live estimate"), "live_estimate")
        self.combo_live_diarization.addItem(self._t("После остановки", "After stop"), "after_stop")
        self.combo_live_diarization.setToolTip(
            self._t(
                "Оценки анонимны и могут меняться в последние 10 секунд.",
                "Live estimates are anonymous and may change during the most recent 10 seconds.",
            )
        )
        self.lbl_live_diarization = QLabel(self._t("Диаризация:", "Diarization:"))
        source_form.addRow(self.lbl_live_diarization, self.combo_live_diarization)
        self.spin_live_gain = QDoubleSpinBox()
        self.spin_live_gain.setRange(0.0, 2.0)
        self.spin_live_gain.setSingleStep(0.1)
        self.spin_live_gain.setValue(1.0)
        self.lbl_live_gain = QLabel(self._t("Усиление:", "Gain:"))
        source_form.addRow(self.lbl_live_gain, self.spin_live_gain)
        layout.addWidget(self.grp_live_source)

        self.grp_live_output = QGroupBox(self._t("2. Папка сессий", "2. Session folder"))
        output_layout = QHBoxLayout(self.grp_live_output)
        output_layout.setContentsMargins(self._px(12), self._px(8), self._px(12), self._px(10))
        output_layout.setSpacing(self._px(12))
        self.btn_live_output_select = QPushButton(self._t("Выбрать папку", "Choose folder"))
        self.btn_live_output_select.setMinimumWidth(self._px(220))
        self.btn_live_output_select.setFixedHeight(self._px(36))
        self.btn_live_output_select.clicked.connect(self._select_live_output_folder)
        output_layout.addWidget(self.btn_live_output_select)
        self.lbl_live_output_folder = QLabel()
        self.lbl_live_output_folder.setStyleSheet(
            self._transparent_label_style(self._colors()["text_mute"])
        )
        output_layout.addWidget(self.lbl_live_output_folder, 1)
        self.live_output_dir = QLineEdit()
        self.live_output_dir.setVisible(False)
        self.live_output_dir.textChanged.connect(self._update_live_output_folder_label)
        layout.addWidget(self.grp_live_output)

        self.grp_live_exports = QGroupBox(self._t("3. Форматы вывода", "3. Output formats"))
        exports_group_layout = QVBoxLayout(self.grp_live_exports)
        exports_group_layout.setContentsMargins(self._px(12), self._px(8), self._px(12), self._px(10))
        exports_group_layout.setSpacing(self._px(6))
        exports_layout = QHBoxLayout()
        exports_layout.setSpacing(self._px(20))
        self.cb_live_export_txt = QCheckBox(self._t("Текст (.txt)", "Text (.txt)"))
        self.cb_live_export_txt.setChecked(True)
        self.cb_live_export_txt_timecodes = QCheckBox(
            self._t("Таймкоды (_timecodes.txt)", "Timecodes (_timecodes.txt)")
        )
        self.cb_live_export_txt_timecodes.setChecked(True)
        self.cb_live_export_txt_diarize = QCheckBox(
            self._t("Диаризация (_diarize.txt)", "Diarization (_diarize.txt)")
        )
        self.cb_live_export_txt_diarize_timecodes = QCheckBox(
            self._t("Диар.+тайм. (_diarize_timecodes.txt)", "Diarization+timecodes (_diarize_timecodes.txt)")
        )
        self.cb_live_export_md = QCheckBox("Markdown (.md)")
        self.cb_live_export_srt = QCheckBox("SRT (.srt)")
        self.cb_live_export_vtt = QCheckBox("VTT (.vtt)")
        self.live_export_checkboxes = {
            "txt": self.cb_live_export_txt,
            "txt_timecodes": self.cb_live_export_txt_timecodes,
            "txt_diarize": self.cb_live_export_txt_diarize,
            "txt_diarize_timecodes": self.cb_live_export_txt_diarize_timecodes,
            "md": self.cb_live_export_md,
            "srt": self.cb_live_export_srt,
            "vtt": self.cb_live_export_vtt,
        }
        for checkbox in self.live_export_checkboxes.values():
            exports_layout.addWidget(checkbox)
        exports_layout.addStretch()
        exports_group_layout.addLayout(exports_layout)
        subtitle_layout = QHBoxLayout()
        subtitle_layout.setSpacing(self._px(20))
        self.cb_live_subtitle_sentence_split = QCheckBox(
            self._t("Разбивать по предложениям", "Split by sentences")
        )
        self.cb_live_subtitle_sentence_split.setChecked(True)
        subtitle_layout.addWidget(self.cb_live_subtitle_sentence_split)
        self.lbl_live_subtitle_max_lines = QLabel(self._t("Строк:", "Lines:"))
        subtitle_layout.addWidget(self.lbl_live_subtitle_max_lines)
        self.spin_live_subtitle_max_lines = QSpinBox()
        self.spin_live_subtitle_max_lines.setRange(1, 4)
        self.spin_live_subtitle_max_lines.setValue(2)
        self.spin_live_subtitle_max_lines.setFixedWidth(self._px(64))
        subtitle_layout.addWidget(self.spin_live_subtitle_max_lines)
        self.lbl_live_subtitle_max_width = QLabel(self._t("Символов:", "Characters:"))
        subtitle_layout.addWidget(self.lbl_live_subtitle_max_width)
        self.spin_live_subtitle_max_width = QSpinBox()
        self.spin_live_subtitle_max_width.setRange(20, 100)
        self.spin_live_subtitle_max_width.setValue(64)
        self.spin_live_subtitle_max_width.setFixedWidth(self._px(76))
        subtitle_layout.addWidget(self.spin_live_subtitle_max_width)
        subtitle_layout.addStretch()
        exports_group_layout.addLayout(subtitle_layout)
        layout.addWidget(self.grp_live_exports)

        self.live_controls_layout = QHBoxLayout()
        self.live_controls_layout.addStretch()
        self.btn_live_start = QPushButton(self._t("НАЧАТЬ ЗАПИСЬ", "START LIVE"))
        self.btn_live_start.setObjectName("start_button")
        self.btn_live_start.setFixedHeight(self._px(32))
        self.btn_live_start.clicked.connect(self._start_live_session)
        self.btn_live_pause = QPushButton(self._t("Пауза", "Pause"))
        self.btn_live_pause.setFixedHeight(self._px(32))
        self.btn_live_pause.clicked.connect(self._pause_live_session)
        self.btn_live_stop = QPushButton(self._t("Остановить", "Stop"))
        self.btn_live_stop.setFixedHeight(self._px(32))
        self.btn_live_stop.clicked.connect(self._stop_live_session)
        self.btn_live_clear = QPushButton(self._t("Очистить", "Clear"))
        self.btn_live_clear.setFixedHeight(self._px(32))
        self.btn_live_clear.clicked.connect(self._clear_live_display)
        self.btn_live_overlay = QPushButton(self._t("Оверлей", "Overlay"))
        self.btn_live_overlay.setFixedHeight(self._px(32))
        self.btn_live_overlay.clicked.connect(self._show_live_overlay)
        self.live_controls_layout.addWidget(self.btn_live_start)
        self.live_controls_layout.addWidget(self.btn_live_pause)
        self.live_controls_layout.addWidget(self.btn_live_stop)
        self.live_controls_layout.addWidget(self.btn_live_clear)
        self.live_controls_layout.addWidget(self.btn_live_overlay)
        self.live_controls_layout.addStretch()
        layout.addLayout(self.live_controls_layout)
        self.lbl_live_status = QLabel(self._t("Готово к записи", "Ready for live capture"))
        layout.addWidget(self.lbl_live_status)
        self.live_transcript = QTextEdit()
        self.live_transcript.setReadOnly(True)
        self.live_transcript.setFont(self._font(10, fixed=True))
        self.live_transcript.setMinimumHeight(self._px(140))
        self.live_transcript.setPlaceholderText(
            self._t("Здесь появятся расшифровка и сообщения о состоянии.", "Transcript and capture status will appear here.")
        )
        layout.addWidget(self.live_transcript)
        layout.addStretch()

        self.combo_live_source.currentIndexChanged.connect(self._update_live_source_controls)
        self.combo_live_diarization.currentIndexChanged.connect(self._update_live_export_controls)
        for checkbox in self.live_export_checkboxes.values():
            checkbox.stateChanged.connect(self._update_live_export_controls)
        self._refresh_live_devices()
        self._update_live_output_folder_label(self.live_output_dir.text())
        self._update_live_source_controls()
        self._update_live_export_controls()
        self._update_live_control_state()
        return tab
