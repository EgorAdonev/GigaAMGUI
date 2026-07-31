"""Always-on-top transcript overlay for live transcription."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ..live.types import TranscriptEvent
from .live_transcript import LiveTranscriptPresenter


class _DragHandle(QFrame):
    def __init__(self, overlay: LiveOverlay) -> None:
        super().__init__(overlay)
        self._overlay = overlay
        self._drag_origin: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() is Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self._overlay.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._overlay.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)


class LiveOverlay(QWidget):
    """Small movable window that keeps final and partial text visible."""

    question_submitted = pyqtSignal(str)
    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Live transcription")
        self.setMinimumWidth(360)
        self.resize(480, 240)
        self._transcript_presenter = LiveTranscriptPresenter()
        self._conversation: list[tuple[str, str]] = []
        self._active_question: str | None = None

        glass = QFrame()
        glass.setObjectName("liveGlass")
        glass.setStyleSheet(
            "QFrame#liveGlass { background: rgba(28, 32, 40, 218); "
            "border: 1px solid rgba(255, 255, 255, 75); border-radius: 16px; } "
            "QTextEdit { background: transparent; border: none; color: #f4f6fa; } "
            "QLabel { color: #d9e2f2; background: transparent; } "
            "QPushButton { background: rgba(255, 255, 255, 26); color: #f4f6fa; "
            "border: none; border-radius: 10px; min-width: 24px; min-height: 24px; } "
            "QPushButton:hover { background: rgba(255, 255, 255, 52); }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(glass)
        layout = QVBoxLayout(glass)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        self.header = _DragHandle(self)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("LIVE")
        title.setStyleSheet("font-weight: 700; letter-spacing: 1px; color: #9fc5ff;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.collapse_button = QPushButton("−")
        self.collapse_button.setToolTip("Collapse")
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        header_layout.addWidget(self.collapse_button)
        self.close_button = QPushButton("×")
        self.close_button.setToolTip("Hide overlay")
        self.close_button.clicked.connect(self.hide)
        header_layout.addWidget(self.close_button)
        layout.addWidget(self.header)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(7)
        self.final_text = QTextEdit()
        self.final_text.setReadOnly(True)
        self.final_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.final_text.setMinimumHeight(112)
        content_layout.addWidget(self.final_text)
        self.partial_label = QLabel()
        self.partial_label.setWordWrap(True)
        self.partial_label.setStyleSheet("color: #a9c9ff; font-style: italic;")
        content_layout.addWidget(self.partial_label)

        answer_header = QHBoxLayout()
        answer_header.setContentsMargins(0, 0, 0, 0)
        answer_header.addWidget(QLabel("ASSISTANT"))
        answer_header.addStretch()
        self.answer_toggle_button = QPushButton("Hide answer")
        self.answer_toggle_button.clicked.connect(self.toggle_answer_visibility)
        answer_header.addWidget(self.answer_toggle_button)
        content_layout.addLayout(answer_header)
        self.answer_card = QFrame()
        answer_layout = QVBoxLayout(self.answer_card)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setMinimumHeight(104)
        answer_layout.addWidget(self.answer_text)
        self.answer_card.hide()
        content_layout.addWidget(self.answer_card)

        question_layout = QHBoxLayout()
        question_layout.setContentsMargins(0, 0, 0, 0)
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Ask about this session")
        self.question_input.returnPressed.connect(self._submit_question)
        question_layout.addWidget(self.question_input)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._submit_question)
        question_layout.addWidget(self.send_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_generation)
        self.cancel_button.hide()
        question_layout.addWidget(self.cancel_button)
        content_layout.addLayout(question_layout)
        layout.addWidget(self.content)

    def update_transcript(self, event: TranscriptEvent) -> None:
        if event.status == "final":
            self._transcript_presenter.add_final(event)
            self._render_final_text()
            self.partial_label.clear()
        elif event.status == "partial":
            self.partial_label.setText(event.text)

    def clear_transcript(self) -> None:
        self._transcript_presenter.clear()
        self.final_text.clear()
        self.partial_label.clear()

    def _render_final_text(self) -> None:
        scrollbar = self.final_text.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        position = scrollbar.value()
        self.final_text.setPlainText(self._transcript_presenter.rendered_paragraphs())
        scrollbar.setValue(scrollbar.maximum() if at_bottom else position)

    def toggle_collapsed(self) -> None:
        collapsed = self.content.isVisible()
        self.content.setVisible(not collapsed)
        self.collapse_button.setText("+" if collapsed else "−")
        self.adjustSize()

    def set_answer(self, text: str) -> None:
        if self._active_question is None:
            self.answer_text.setPlainText(text)
        else:
            self._conversation[-1] = (self._active_question, text)
            self._render_conversation()
        self.answer_card.show()
        self.answer_toggle_button.setText("Hide answer")
        self.adjustSize()

    def append_answer(self, text: str) -> None:
        if self._active_question is None:
            self.set_answer(text)
            return
        question, answer = self._conversation[-1]
        self._conversation[-1] = (question, text if answer == "Generating..." else answer + text)
        self._render_conversation()

    def finish_generation(self) -> None:
        self._active_question = None
        self.cancel_button.hide()
        self.send_button.setEnabled(True)

    def _begin_question(self, question: str) -> None:
        self._active_question = question
        self._conversation.append((question, "Generating..."))
        self._render_conversation()
        self.answer_card.show()
        self.answer_toggle_button.setText("Hide answer")
        self.send_button.setEnabled(False)
        self.cancel_button.show()
        self.adjustSize()

    def _cancel_generation(self) -> None:
        if self._active_question is None:
            return
        question, _answer = self._conversation[-1]
        self._conversation[-1] = (question, "")
        self._active_question = None
        self._render_conversation()
        self.cancel_button.hide()
        self.send_button.setEnabled(True)
        self.cancel_requested.emit()

    def _render_conversation(self) -> None:
        self.answer_text.setPlainText(
            "\n\n".join(
                f"You: {question}" + (f"\nAssistant: {answer}" if answer else "")
                for question, answer in self._conversation
            )
        )

    def toggle_answer_visibility(self) -> None:
        visible = self.answer_card.isVisible()
        self.answer_card.setVisible(not visible)
        self.answer_toggle_button.setText("Show answer" if visible else "Hide answer")
        self.adjustSize()

    def _submit_question(self) -> None:
        question = self.question_input.text().strip()
        if not question:
            return
        self.question_input.clear()
        self._begin_question(question)
        self.question_submitted.emit(question)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
