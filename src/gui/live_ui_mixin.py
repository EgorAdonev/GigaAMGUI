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
    QVBoxLayout,
    QWidget,
)


class LiveUiMixin:
    def _create_live_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(self._px(8), self._px(14), self._px(8), self._px(8))
        layout.setSpacing(self._px(10))

        self.grp_live_source = QGroupBox("Live capture")
        source_form = QFormLayout(self.grp_live_source)
        self.combo_live_source = QComboBox()
        self.combo_live_source.addItem("Microphone", "mic")
        self.combo_live_source.addItem("System audio", "system")
        self.combo_live_source.addItem("Microphone + system audio", "both")
        source_form.addRow("Source:", self.combo_live_source)

        self.combo_live_mic_device = QComboBox()
        self.combo_live_mic_device.addItem("Default microphone", "mic-default")
        source_form.addRow("Microphone device:", self.combo_live_mic_device)
        self.combo_live_system_device = QComboBox()
        self.combo_live_system_device.addItem("System audio", "system-default")
        source_form.addRow("System audio device:", self.combo_live_system_device)

        self.cb_live_mic_audio = QCheckBox("Record microphone track")
        self.cb_live_mic_audio.setChecked(True)
        self.cb_live_system_audio = QCheckBox("Record system audio track")
        self.cb_live_system_audio.setChecked(True)
        tracks = QWidget()
        tracks_layout = QHBoxLayout(tracks)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.addWidget(self.cb_live_mic_audio)
        tracks_layout.addWidget(self.cb_live_system_audio)
        tracks_layout.addStretch()
        source_form.addRow("Tracks:", tracks)

        self.combo_live_diarization = QComboBox()
        self.combo_live_diarization.addItem("Off", "off")
        self.combo_live_diarization.addItem("Live estimate", "live_estimate")
        self.combo_live_diarization.addItem("After stop", "after_stop")
        self.combo_live_diarization.setToolTip(
            "Live estimates are anonymous and may change during the most recent 10 seconds."
        )
        source_form.addRow("Diarization:", self.combo_live_diarization)
        self.spin_live_gain = QDoubleSpinBox()
        self.spin_live_gain.setRange(0.0, 2.0)
        self.spin_live_gain.setSingleStep(0.1)
        self.spin_live_gain.setValue(1.0)
        source_form.addRow("Gain:", self.spin_live_gain)
        layout.addWidget(self.grp_live_source)

        self.grp_live_output = QGroupBox("Session output")
        output_form = QFormLayout(self.grp_live_output)
        self.live_output_dir = QLineEdit()
        self.live_output_dir.setPlaceholderText("Select an output folder before starting")
        output_form.addRow("Folder:", self.live_output_dir)
        exports = QWidget()
        exports_layout = QHBoxLayout(exports)
        exports_layout.setContentsMargins(0, 0, 0, 0)
        self.cb_live_export_txt = QCheckBox("TXT")
        self.cb_live_export_txt.setChecked(True)
        self.cb_live_export_srt = QCheckBox("SRT")
        self.cb_live_export_vtt = QCheckBox("VTT")
        for checkbox in (self.cb_live_export_txt, self.cb_live_export_srt, self.cb_live_export_vtt):
            exports_layout.addWidget(checkbox)
        exports_layout.addStretch()
        output_form.addRow("Exports:", exports)
        layout.addWidget(self.grp_live_output)

        controls = QHBoxLayout()
        self.btn_live_start = QPushButton("Start")
        self.btn_live_start.setObjectName("start_button")
        self.btn_live_start.clicked.connect(self._start_live_session)
        self.btn_live_pause = QPushButton("Pause")
        self.btn_live_pause.clicked.connect(self._pause_live_session)
        self.btn_live_stop = QPushButton("Stop")
        self.btn_live_stop.clicked.connect(self._stop_live_session)
        self.btn_live_overlay = QPushButton("Overlay")
        self.btn_live_overlay.clicked.connect(self._show_live_overlay)
        controls.addWidget(self.btn_live_start)
        controls.addWidget(self.btn_live_pause)
        controls.addWidget(self.btn_live_stop)
        controls.addWidget(self.btn_live_overlay)
        controls.addStretch()
        layout.addLayout(controls)
        self.lbl_live_status = QLabel("Ready")
        layout.addWidget(self.lbl_live_status)
        layout.addStretch()

        self.combo_live_source.currentIndexChanged.connect(self._update_live_source_controls)
        self._update_live_source_controls()
        self._update_live_control_state()
        return tab
