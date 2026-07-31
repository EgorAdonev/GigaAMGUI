"""Presentation-only segmentation for live transcript views."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from ..live.types import TranscriptEvent


_SENTENCE = re.compile(r".+?[.!?]+(?=\s|$)", re.DOTALL)


@dataclass
class LiveParagraph:
    sample_start: int
    source_label: str
    speaker: str | None
    sentences: list[str] = field(default_factory=list)


class LiveTranscriptPresenter:
    """Group finalized speech without influencing capture or ASR decisions."""

    def __init__(self, *, long_gap_samples: int = 48_000, max_sentences: int = 3) -> None:
        self._long_gap_samples = long_gap_samples
        self._max_sentences = max_sentences
        self.paragraphs: list[LiveParagraph] = []
        self.active_text = ""
        self._active_event: TranscriptEvent | None = None
        self._last_sample_end: int | None = None
        self._force_new_paragraph = False

    def clear(self) -> None:
        self.paragraphs.clear()
        self.active_text = ""
        self._active_event = None
        self._last_sample_end = None
        self._force_new_paragraph = False

    def add_final(self, event: TranscriptEvent) -> bool:
        """Add final ASR text and return whether it completed a sentence."""
        if event.status != "final":
            return False
        previous_sample_end = self._last_sample_end
        if self._active_event is not None and (
            self._active_event.source_label,
            self._active_event.speaker,
        ) != (event.source_label, event.speaker):
            self.paragraphs.append(LiveParagraph(
                self._active_event.sample_start,
                self._active_event.source_label,
                self._active_event.speaker,
                [self.active_text],
            ))
            self.active_text = ""
            self._active_event = None
        if self._active_event is None:
            self._active_event = event
        self.active_text = " ".join(filter(None, (self.active_text, event.text.strip())))
        completed = False
        while match := _SENTENCE.match(self.active_text):
            sentence = match.group().strip()
            self.active_text = self.active_text[match.end():].lstrip()
            self._append_sentence(
                sentence,
                self._active_event,
                previous_sample_end if not completed else event.sample_start,
            )
            completed = True
            self._active_event = event if self.active_text else None
        if event.paragraph_break_after:
            if self.active_text and self._active_event is not None:
                self.paragraphs.append(LiveParagraph(
                    self._active_event.sample_start,
                    self._active_event.source_label,
                    self._active_event.speaker,
                    [self.active_text],
                ))
                self.active_text = ""
                self._active_event = None
            self._force_new_paragraph = True
        self._last_sample_end = event.sample_end
        return completed

    def _append_sentence(
        self,
        sentence: str,
        event: TranscriptEvent,
        previous_sample_end: int | None,
    ) -> None:
        paragraph = self.paragraphs[-1] if self.paragraphs else None
        if (
            paragraph is None
            or self._force_new_paragraph
            or self._starts_new_paragraph(paragraph, event, previous_sample_end)
        ):
            paragraph = LiveParagraph(event.sample_start, event.source_label, event.speaker)
            self.paragraphs.append(paragraph)
        self._force_new_paragraph = False
        paragraph.sentences.append(sentence)

    def _starts_new_paragraph(
        self,
        paragraph: LiveParagraph,
        event: TranscriptEvent,
        previous_sample_end: int | None,
    ) -> bool:
        if (paragraph.source_label, paragraph.speaker) != (event.source_label, event.speaker):
            return True
        if len(paragraph.sentences) >= self._max_sentences:
            return True
        return (
            previous_sample_end is not None
            and event.sample_start - previous_sample_end > self._long_gap_samples
        )

    def rendered_paragraphs(self) -> str:
        rendered = [self._render_paragraph(paragraph) for paragraph in self.paragraphs]
        if self.active_text and self._active_event is not None:
            active = LiveParagraph(
                self._active_event.sample_start,
                self._active_event.source_label,
                self._active_event.speaker,
                [self.active_text],
            )
            if self.paragraphs and (
                self.paragraphs[-1].source_label,
                self.paragraphs[-1].speaker,
            ) == (active.source_label, active.speaker):
                rendered[-1] = f"{rendered[-1]} {self.active_text}"
            else:
                rendered.append(self._render_paragraph(active))
        return "\n\n".join(rendered)

    @staticmethod
    def _render_paragraph(paragraph: LiveParagraph) -> str:
        seconds = paragraph.sample_start / 16_000
        minutes, seconds = divmod(seconds, 60)
        timestamp = f"[{int(minutes):02d}:{seconds:06.3f}]"
        metadata = " · ".join(filter(None, (paragraph.source_label, paragraph.speaker)))
        return f"{timestamp} {metadata}: {' '.join(paragraph.sentences)}"
