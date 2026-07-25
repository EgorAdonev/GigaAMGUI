# Subtitle Speaker Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In diarized subtitles, name the speaker in SRT only when the speaker changes, while keeping a WebVTT voice span with the full speaker name on every VTT cue.

**Architecture:** The cue planner in `src/core/subtitles.py` becomes the single place that decides when a speaker label is visible. `SubtitleCue` grows a second speaker field: `speaker` keeps the full name (semantic attribution, consumed by VTT), `speaker_label` holds the fitted visible label and is set only on the cue that starts a speaker's turn (consumed by SRT). Line-width budget is charged only to a cue that draws a visible label, so all other cues recover the full `max_line_width`. Formatters stay pure renderers.

**Tech Stack:** Python 3.11+, pytest, Ruff, `.venv` at repo root.

**Spec:** `docs/superpowers/specs/2026-07-25-subtitle-speaker-labels-design.md`

## Global Constraints

- Work on the current `main` branch; do not create a worktree or feature branch.
- Only `src/core/subtitles.py`, `src/core/formatters.py`, their two test files, and docs change. Do NOT touch `cli.py`, `src/gui/*`, `web/*`, `tui/*`, `src/core/processor.py`, or `src/core/diarization/*`.
- No new user-facing setting. `SubtitleOptions` keeps exactly its three current fields.
- Visible SRT label format is `{name}: ` — plain text, no angle brackets.
- VTT keeps `<v {full name}>` on every diarized cue, with no closing `</v>`.
- A long pause by the same speaker must NOT reintroduce the label; only a real speaker change does.
- Non-diarized SRT/VTT output must stay byte-for-byte identical.
- TXT, timecoded TXT, and Markdown output must not change.
- Run commands with the repo venv: `.venv/bin/python -m pytest`, `.venv/bin/python -m ruff check`.
- Three DPI-sensitive GUI layout tests can fail independently of this change; compare against a clean tree before blaming this work.
- Commit each task; do NOT push, tag, or build release artifacts.
- `.gitignore:78` ignores `docs/`, so `docs/CHANGELOG.md` commits normally (it is already tracked) but this plan and its spec need `git add -f` if the maintainer wants them versioned, the way earlier specs and plans were.

---

### Task 1: Planner emits `speaker_label` on speaker change only

**Files:**
- Modify: `src/core/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `SRT_SPEAKER_SEPARATOR: str` — public module constant, value `": "`.
  - `SubtitleCue(start: float, end: float, lines: tuple[str, ...], speaker: str | None = None, speaker_label: str | None = None)` — frozen dataclass.
  - `build_subtitle_cues(utterances: list[dict], options: SubtitleOptions | None = None) -> list[SubtitleCue]` — unchanged signature.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_subtitles.py`:

```python
def test_speaker_label_only_on_first_cue_of_turn():
    utterances = [
        {
            "transcription": "Первая фраза. Вторая фраза.",
            "boundaries": (0.0, 2.0),
            "speaker": "Спикер №1",
            "words": [
                {"text": "Первая", "start": 0.0, "end": 0.5},
                {"text": "фраза.", "start": 0.6, "end": 1.0},
                {"text": "Вторая", "start": 1.1, "end": 1.6},
                {"text": "фраза.", "start": 1.7, "end": 2.0},
            ],
        }
    ]

    cues = build_subtitle_cues(utterances, SubtitleOptions())

    assert [cue.speaker_label for cue in cues] == ["Спикер №1", None]
    assert [cue.speaker for cue in cues] == ["Спикер №1", "Спикер №1"]


def test_long_pause_does_not_repeat_speaker_label():
    utterances = [
        {
            "transcription": "Первая фраза.",
            "boundaries": (0.0, 1.0),
            "speaker": "Спикер №1",
            "words": [
                {"text": "Первая", "start": 0.0, "end": 0.5},
                {"text": "фраза.", "start": 0.6, "end": 1.0},
            ],
        },
        {
            "transcription": "Через паузу.",
            "boundaries": (30.0, 31.0),
            "speaker": "Спикер №1",
            "words": [
                {"text": "Через", "start": 30.0, "end": 30.5},
                {"text": "паузу.", "start": 30.6, "end": 31.0},
            ],
        },
    ]

    cues = build_subtitle_cues(utterances, SubtitleOptions())

    assert [cue.speaker_label for cue in cues] == ["Спикер №1", None]
    assert [cue.speaker for cue in cues] == ["Спикер №1", "Спикер №1"]


def test_speaker_change_reintroduces_label():
    utterances = [
        {
            "transcription": "Раз.",
            "boundaries": (0.0, 0.5),
            "speaker": "Спикер №1",
            "words": [{"text": "Раз.", "start": 0.0, "end": 0.5}],
        },
        {
            "transcription": "Два.",
            "boundaries": (0.6, 1.0),
            "speaker": "Спикер №2",
            "words": [{"text": "Два.", "start": 0.6, "end": 1.0}],
        },
        {
            "transcription": "Три.",
            "boundaries": (1.1, 1.5),
            "speaker": "Спикер №1",
            "words": [{"text": "Три.", "start": 1.1, "end": 1.5}],
        },
    ]

    cues = build_subtitle_cues(utterances, SubtitleOptions())

    assert [cue.speaker_label for cue in cues] == [
        "Спикер №1",
        "Спикер №2",
        "Спикер №1",
    ]


def test_unlabeled_cues_use_full_line_width():
    tokens = ["абвгдежзи"] * 7 + ["абвгдежзи."]
    utterances = [
        {
            "transcription": " ".join(tokens),
            "boundaries": (0.0, 8.0),
            "speaker": "Спикер №1",
            "words": [
                {"text": token, "start": float(index), "end": index + 0.9}
                for index, token in enumerate(tokens)
            ],
        }
    ]
    options = SubtitleOptions(max_line_count=1, max_line_width=40)

    cues = build_subtitle_cues(utterances, options)

    # Labeled cue wraps at 40 - len("Спикер №1") - len(": ") == 29 columns.
    assert cues[0].speaker_label == "Спикер №1"
    assert cues[0].lines == ("абвгдежзи абвгдежзи абвгдежзи",)
    # Unlabeled cues recover the full 40 columns: four tokens instead of three.
    assert cues[1].speaker_label is None
    assert cues[1].lines == ("абвгдежзи абвгдежзи абвгдежзи абвгдежзи",)
    assert cues[2].lines == ("абвгдежзи.",)


def test_long_speaker_name_is_truncated_only_in_visible_label():
    utterances = [
        {
            "transcription": "Коротко.",
            "boundaries": (0.0, 1.0),
            "speaker": "Очень длинное имя спикера",
            "words": [{"text": "Коротко.", "start": 0.0, "end": 1.0}],
        }
    ]
    options = SubtitleOptions(max_line_width=40)

    cues = build_subtitle_cues(utterances, options)

    assert cues[0].speaker == "Очень длинное имя спикера"
    assert cues[0].speaker_label == "Очень длин…имя спикера"


def test_cues_without_speaker_have_no_label():
    utterances = [
        {
            "transcription": "Без спикера.",
            "boundaries": (0.0, 1.0),
            "words": [
                {"text": "Без", "start": 0.0, "end": 0.4},
                {"text": "спикера.", "start": 0.5, "end": 1.0},
            ],
        }
    ]

    cues = build_subtitle_cues(utterances, SubtitleOptions())

    assert [(cue.speaker, cue.speaker_label) for cue in cues] == [(None, None)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_subtitles.py -q`

Expected: FAIL. `AttributeError: 'SubtitleCue' object has no attribute 'speaker_label'` in the new tests.

- [ ] **Step 3: Replace the speaker-width constants**

In `src/core/subtitles.py`, replace lines 8-10:

```python
_MAX_JOIN_GAP_SECONDS = 1.0
_VTT_SPEAKER_MARKUP_OVERHEAD = len("<v >")
_PREFERRED_MIN_TEXT_WIDTH_WITH_SPEAKER = 16
```

with:

```python
_MAX_JOIN_GAP_SECONDS = 1.0
_PREFERRED_MIN_TEXT_WIDTH_WITH_SPEAKER = 16

# Видимый разделитель метки спикера в SRT. VTT использует невидимую разметку
# <v ...>, поэтому она не участвует в бюджете ширины строки.
SRT_SPEAKER_SEPARATOR = ": "
```

- [ ] **Step 4: Add `speaker_label` to the cue dataclass**

Replace the `SubtitleCue` dataclass (`src/core/subtitles.py:34-41`) with:

```python
@dataclass(frozen=True)
class SubtitleCue:
    """Один временной блок субтитров до сериализации в SRT/VTT.

    speaker — полное имя спикера, семантическая атрибуция для VTT <v ...>.
    speaker_label — видимая метка для SRT, заполнена только на первом cue
    новой реплики спикера.
    """

    start: float
    end: float
    lines: tuple[str, ...]
    speaker: str | None = None
    speaker_label: str | None = None
```

- [ ] **Step 5: Rewrite the width helpers**

Replace `_fit_speaker` and `_content_line_width` (`src/core/subtitles.py:144-167`) with:

```python
def _fit_speaker(speaker: object, width: int) -> str | None:
    """Обрезать имя спикера под видимую SRT-метку, сохранив место для текста."""

    if speaker is None:
        return None
    value = str(speaker).strip()
    if not value:
        return None
    separator_width = len(SRT_SPEAKER_SEPARATOR)
    reserved_text_width = min(
        _PREFERRED_MIN_TEXT_WIDTH_WITH_SPEAKER,
        width - separator_width - 1,
    )
    max_length = max(1, width - separator_width - reserved_text_width)
    if len(value) <= max_length:
        return value
    if max_length <= 2:
        return value[-max_length:]
    prefix_length = (max_length - 1) // 2
    suffix_length = max_length - prefix_length - 1
    return f"{value[:prefix_length]}…{value[-suffix_length:]}"


def _content_line_width(width: int, label: str | None) -> int:
    """Ширина текста строки: метка занимает место только там, где её печатают."""

    if label is None:
        return width
    return max(1, width - len(label) - len(SRT_SPEAKER_SEPARATOR))
```

- [ ] **Step 6: Rewrite `build_subtitle_cues` label bookkeeping**

Replace `build_subtitle_cues` (`src/core/subtitles.py:170-230`) with:

```python
def build_subtitle_cues(
    utterances: list[dict],
    options: SubtitleOptions | None = None,
) -> list[SubtitleCue]:
    """Преобразовать ASR utterances в семантические subtitle cues."""

    options = options or SubtitleOptions()
    cues: list[SubtitleCue] = []
    grouped_words: list[dict] = []
    grouped_speaker: str | None = None
    grouped_label: str | None = None
    labeled_speaker: str | None = None

    def flush_group() -> None:
        nonlocal grouped_words, grouped_label
        sentence: list[dict] = []
        for grouped_word in grouped_words:
            sentence.append(grouped_word)
            if options.sentence_split and _ends_sentence(grouped_word["text"]):
                cues.extend(_cues_from_words(
                    sentence,
                    grouped_speaker,
                    grouped_label,
                    options,
                ))
                grouped_label = None
                sentence = []
        if sentence:
            cues.extend(_cues_from_words(
                sentence,
                grouped_speaker,
                grouped_label,
                options,
            ))
            grouped_label = None
        grouped_words = []

    for utterance in utterances:
        if not isinstance(utterance, dict):
            continue
        transcription = utterance.get("transcription", "")
        if not isinstance(transcription, str) or not transcription.strip():
            continue
        words = _normalized_words(utterance) or _fallback_words(utterance)
        if not words:
            continue
        raw_speaker = utterance.get("speaker")
        speaker = str(raw_speaker).strip() if raw_speaker is not None else ""
        speaker = speaker or None
        can_join = bool(grouped_words) and speaker == grouped_speaker
        if can_join:
            gap = float(words[0]["start"]) - float(grouped_words[-1]["end"])
            can_join = 0.0 <= gap <= _MAX_JOIN_GAP_SECONDS
        if not can_join:
            flush_group()
            grouped_speaker = speaker
            grouped_label = None
            if speaker is not None and speaker != labeled_speaker:
                grouped_label = _fit_speaker(speaker, options.max_line_width)
                labeled_speaker = speaker
        # Пока метка не напечатана, любое слово группы может попасть в cue
        # с меткой, поэтому делим по суженной ширине всю группу целиком.
        split_width = _content_line_width(options.max_line_width, grouped_label)
        grouped_words.extend(_split_long_words(words, split_width))

    flush_group()

    return cues
```

Note for the implementer: `speaker` is now the full stripped name and doubles as the grouping key, so the old `grouped_speaker_key` variable disappears. An intervening group with no speaker does not reset `labeled_speaker`, which matches `generate_markdown` and the diarized TXT path.

- [ ] **Step 7: Thread the label through cue construction**

Replace `_cues_from_words` and `_cue_from_words` (`src/core/subtitles.py:251-282`, i.e. through the end of the file) with:

```python
def _cues_from_words(
    words: list[dict],
    speaker: str | None,
    label: str | None,
    options: SubtitleOptions,
) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    current: list[dict] = []
    pending_label = label
    line_width = _content_line_width(options.max_line_width, pending_label)
    for word in words:
        candidate = [*current, word]
        lines = _wrap_words(candidate, line_width)
        if current and len(lines) > options.max_line_count:
            cues.append(_cue_from_words(current, speaker, pending_label, line_width))
            pending_label = None
            line_width = _content_line_width(options.max_line_width, pending_label)
            current = [word]
        else:
            current = candidate
    if current:
        cues.append(_cue_from_words(current, speaker, pending_label, line_width))
    return cues


def _cue_from_words(
    words: list[dict],
    speaker: str | None,
    label: str | None,
    line_width: int,
) -> SubtitleCue:
    return SubtitleCue(
        start=float(words[0]["start"]),
        end=float(words[-1]["end"]),
        lines=_wrap_words(words, line_width),
        speaker=speaker,
        speaker_label=label,
    )
```

- [ ] **Step 8: Run the planner tests**

Run: `.venv/bin/python -m pytest tests/test_subtitles.py -q`

Expected: PASS, all tests in the file.

- [ ] **Step 9: Lint**

Run: `.venv/bin/python -m ruff check src/core/subtitles.py tests/test_subtitles.py`

Expected: `All checks passed!`

- [ ] **Step 10: Commit**

```bash
git add src/core/subtitles.py tests/test_subtitles.py
git commit -m "feat(subtitles): label speakers on change in cue planner"
```

---

### Task 2: SRT prints the visible label, VTT keeps the voice span

**Files:**
- Modify: `src/core/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: `SubtitleCue.speaker`, `SubtitleCue.speaker_label`, and `SRT_SPEAKER_SEPARATOR` from `src/core/subtitles.py` (Task 1).
- Produces: `generate_srt(utterances: list, options: SubtitleOptions | None = None) -> str` and `generate_vtt(...) -> str` — unchanged signatures.

- [ ] **Step 1: Update the existing formatter tests and add the regression test**

In `tests/test_formatters.py`, replace the import block on lines 1-3:

```python
"""Характеризующие тесты форматтеров SRT/VTT/Markdown."""
from src.core import formatters
from src.core.subtitles import SubtitleOptions
```

with:

```python
"""Характеризующие тесты форматтеров SRT/VTT/Markdown."""
import re

from src.core import formatters
from src.core.subtitles import SRT_SPEAKER_SEPARATOR, SubtitleOptions
```

Replace the expected SRT payload line in `test_generate_srt` (line 38):

```python
        "SPEAKER_00: второй третий\n"
```

Replace the two markup assertions in `test_srt_and_vtt_share_phrase_cues_and_line_wrapping` (lines 74-75). At `max_line_width=20` the visible SRT label is truncated to `№1`, while VTT keeps the full name:

```python
    assert "№1: Первая короткая\nфраза." in srt
    assert "<v Спикер №1>Первая короткая\nфраза." in vtt
```

Replace the assertion body of `test_diarized_subtitle_prefix_respects_max_line_width` (lines 102-110) with:

```python
    srt_payload = [
        line for line in srt.splitlines()
        if line and not line.isdigit() and "-->" not in line
    ]
    # Разметка <v ...> невидима в плеере, поэтому меряем текст без неё.
    vtt_payload = [
        re.sub(r"^<v [^>]+>", "", line)
        for line in vtt.splitlines()
        if line and line != "WEBVTT" and "-->" not in line
    ]
    assert all(len(line) <= 20 for line in [*srt_payload, *vtt_payload])
    assert srt_payload[0].startswith(f"№1{SRT_SPEAKER_SEPARATOR}")
```

Append this new test to the end of `tests/test_formatters.py`:

```python
def test_srt_labels_speaker_once_while_vtt_attributes_every_cue():
    utterances = [{
        "transcription": "Первая фраза. Вторая фраза.",
        "boundaries": (1.0, 3.0),
        "speaker": "Спикер №1",
        "words": [
            {"text": "Первая", "start": 1.0, "end": 1.4},
            {"text": "фраза.", "start": 1.5, "end": 1.9},
            {"text": "Вторая", "start": 2.0, "end": 2.4},
            {"text": "фраза.", "start": 2.5, "end": 2.9},
        ],
    }]

    srt = formatters.generate_srt(utterances)
    vtt = formatters.generate_vtt(utterances)

    srt_blocks = [block for block in srt.split("\n\n") if block.strip()]
    assert len(srt_blocks) == 2
    assert srt_blocks[0].endswith("Спикер №1: Первая фраза.")
    assert "Спикер" not in srt_blocks[1]
    assert "<" not in srt
    assert vtt.count("<v Спикер №1>") == 2
    assert "</v>" not in vtt
    # Оба формата описывают одни и те же cues с одинаковыми границами.
    srt_times = [
        line.replace(",", ".") for line in srt.splitlines() if "-->" in line
    ]
    vtt_times = [line for line in vtt.splitlines() if "-->" in line]
    assert srt_times == vtt_times
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_formatters.py -q`

Expected: FAIL. `test_generate_srt` still renders `<SPEAKER_00> второй третий`, and `test_srt_labels_speaker_once_while_vtt_attributes_every_cue` fails on `assert "<" not in srt`.

- [ ] **Step 3: Render the plain SRT label**

In `src/core/formatters.py`, change the import on line 9 to:

```python
from .subtitles import SRT_SPEAKER_SEPARATOR, SubtitleOptions, build_subtitle_cues
```

Replace lines 31-33 in `generate_srt`:

```python
        cue_lines = list(cue.lines)
        if cue.speaker and cue_lines:
            cue_lines[0] = f"<{cue.speaker}> {cue_lines[0]}"
```

with:

```python
        cue_lines = list(cue.lines)
        if cue.speaker_label and cue_lines:
            cue_lines[0] = (
                f"{cue.speaker_label}{SRT_SPEAKER_SEPARATOR}{cue_lines[0]}"
            )
```

- [ ] **Step 4: Document the VTT voice span**

`generate_vtt` keeps its current behavior (a voice span on every diarized cue), but it now receives the full untruncated name. Replace its one-line docstring (`src/core/formatters.py:41`) with:

```python
    """Генерирует контент в формате VTT субтитров.

    Voice span <v ...> ставится на каждый cue: WebVTT не переносит состояние
    между cues, поэтому cue без него теряет атрибуцию спикера. Имя не обрезаем —
    оно невидимо в плеере и нужно для ::cue(v[voice="..."]) и внешних
    инструментов. Закрывающий </v> опускается по спецификации, потому что span
    занимает весь текст cue; при добавлении любой другой разметки в cue его
    придётся вернуть.
    """
```

- [ ] **Step 5: Run the formatter tests**

Run: `.venv/bin/python -m pytest tests/test_formatters.py -q`

Expected: PASS, all tests in the file.

- [ ] **Step 6: Lint**

Run: `.venv/bin/python -m ruff check src/core/formatters.py tests/test_formatters.py`

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/core/formatters.py tests/test_formatters.py
git commit -m "feat(subtitles): print SRT speaker labels only on change"
```

---

### Task 3: Full regression run and knowledge graph refresh

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-2.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: PASS. If exactly the three known DPI-sensitive GUI layout tests fail, verify they also fail on a clean tree with `git stash && .venv/bin/python -m pytest tests/ -q; git stash pop` before accepting them. Any failure in `tests/test_cli_backend.py`, `tests/test_processor_progress.py`, `tests/test_web_app_persistence.py`, `tests/test_tui_worker.py`, or `tests/test_diarization_mapping.py` is a real regression from this change and must be fixed.

- [ ] **Step 2: Lint the repository**

Run: `.venv/bin/python -m ruff check .`

Expected: `All checks passed!`

- [ ] **Step 3: Inspect a diarized sample by eye**

Run:

```bash
.venv/bin/python -c "
from src.core.formatters import generate_srt, generate_vtt
from src.core.subtitles import SubtitleOptions

utterances = [
    {'transcription': 'Добрый день, начнём с повестки. Первый пункт — бюджет.',
     'boundaries': (1.0, 6.0), 'speaker': 'Спикер №1'},
    {'transcription': 'У меня есть вопрос по срокам.',
     'boundaries': (6.2, 9.0), 'speaker': 'Спикер №2'},
    {'transcription': 'Отвечу после перерыва.',
     'boundaries': (9.2, 11.0), 'speaker': 'Спикер №1'},
]
print(generate_srt(utterances, SubtitleOptions()))
print(generate_vtt(utterances, SubtitleOptions()))
"
```

Expected: SRT names `Спикер №1:` once, then `Спикер №2:` once, then `Спикер №1:` once, with no angle brackets anywhere; VTT carries `<v Спикер №N>` on every cue and no `</v>`.

Report this output in the task summary. The maintainer additionally verifies a real long diarized recording (the issue #37 example) before the release is cut; that check needs audio and models and is not part of this task.

- [ ] **Step 4: Refresh the knowledge graph**

Run: `graphify update .`

Expected: the command completes and reports an updated graph. If `graphify` is not on `PATH`, skip this step and say so in the task report.

- [ ] **Step 5: Confirm the graph produced no tracked changes**

```bash
git status --short
```

`graphify-out/` is gitignored, so expect a clean tree and make no commit. If anything tracked did change, commit it as `chore: refresh knowledge graph`.

---

### Task 4: Documentation

**Files:**
- Modify: `docs/CHANGELOG.md` (the `## [Unreleased]` section, lines 8-26)
- Modify: `README.md:32-33`, `README.md:116-121`
- Modify: `README_EN.md:32-33`, `README_EN.md:117-122`

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-2.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add a changelog entry**

In `docs/CHANGELOG.md`, inside the existing `## [Unreleased]` section, append to the end of the `### Исправлено` list (after the bullet starting `- TXT и Markdown не зависят от новых настроек`):

```markdown
- Issue #37: в SRT имя спикера печатается только при смене говорящего, обычным
  текстом `Спикер №1:` вместо `<Спикер №1>` — угловые скобки не являются тегом
  SRT и вырезаются частью плееров. Долгая пауза того же спикера метку не
  повторяет.
- VTT сохраняет стандартный voice span `<v Спикер №1>` на каждом cue: WebVTT не
  переносит состояние между cues, поэтому это нужно для атрибуции и стилизации
  `::cue(v[voice="..."])`. Имя в VTT не обрезается.
- Ширина строки резервируется под метку только там, где её печатают, поэтому
  остальные cues используют всю настроенную длину строки.
```

- [ ] **Step 2: Update the Russian README feature list**

In `README.md`, replace the subtitle bullet on lines 32-33:

```markdown
- SRT/VTT делятся на короткие фразы по пунктуации и word timestamps; число строк
  и максимальная длина строки настраиваются отдельно, не затрагивая TXT/MD.
```

with:

```markdown
- SRT/VTT делятся на короткие фразы по пунктуации и word timestamps; число строк
  и максимальная длина строки настраиваются отдельно, не затрагивая TXT/MD.
- При диаризации SRT называет спикера только при смене говорящего (`Спикер №1:`),
  а VTT сохраняет стандартный voice span `<v Спикер №1>` на каждом cue.
```

- [ ] **Step 3: Correct the Russian subtitle-settings paragraph**

The last sentence of the `### Настройки субтитров` section currently claims the width limit always accounts for the speaker label, which stops being true. In `README.md`, replace lines 119-121:

```markdown
распределение внутри исходного ASR-сегмента. Лимит ширины учитывает также метку
спикера; при экстремально узкой строке длинная метка сокращается с сохранением
идентифицирующего суффикса.
```

with:

```markdown
распределение внутри исходного ASR-сегмента. При диаризации SRT называет спикера
только при смене говорящего, и лимит ширины учитывает метку лишь в этих cue —
остальные используют всю заданную длину строки. VTT сохраняет стандартный voice
span `<v Спикер №1>` на каждом cue: он невидим в плеере, но нужен для атрибуции
и стилизации. При экстремально узкой строке длинная видимая метка сокращается
с сохранением идентифицирующего суффикса; в VTT имя не обрезается.
```

- [ ] **Step 4: Update the English README feature list**

In `README_EN.md`, replace the subtitle bullet on lines 32-33:

```markdown
- SRT/VTT are split into short phrases using punctuation and word timestamps;
  line count and line width are configurable without changing TXT/MD output.
```

with:

```markdown
- SRT/VTT are split into short phrases using punctuation and word timestamps;
  line count and line width are configurable without changing TXT/MD output.
- With diarization, SRT names a speaker only when the speaker changes
  (`Спикер №1:`), while VTT keeps a standard `<v Спикер №1>` voice span on every
  cue.
```

- [ ] **Step 5: Correct the English subtitle-settings paragraph**

In `README_EN.md`, replace lines 120-122:

```markdown
ASR segment as the fallback. The width limit also includes speaker markup; at
extremely narrow widths, long speaker labels are compacted while preserving
their identifying suffix.
```

with:

```markdown
ASR segment as the fallback. With diarization, SRT names a speaker only when the
speaker changes, and the width limit charges the label only to those cues — the
rest use the full configured width. VTT keeps a standard `<v Спикер №1>` voice
span on every cue: it is invisible in players but carries attribution and
styling. At extremely narrow widths the visible label is compacted while
preserving its identifying suffix; the VTT name is never truncated.
```

- [ ] **Step 6: Verify the docs and nothing else drifted**

Run: `git diff --stat && git diff --check`

Expected: only `docs/CHANGELOG.md`, `README.md`, and `README_EN.md` listed; no whitespace errors reported.

- [ ] **Step 7: Commit**

```bash
git add docs/CHANGELOG.md README.md README_EN.md
git commit -m "docs: describe speaker labels in SRT and VTT"
```

---

## Deferred to release cut (do NOT run as part of this plan)

These steps happen only when the maintainer explicitly asks to cut `v1.3.8`:

- bump `CFBundleShortVersionString` and `CFBundleVersion` in `packaging/gigaam_app_mac.spec:225-226` and the matching assertions in `tests/test_macos_packaging_config.py:22-23`;
- add `docs/RELEASE_NOTES_1.3.8.md`;
- build and verify the macOS bundle;
- push `main`, tag `v1.3.8`, and reply on issue #37.
