# Issue #37 follow-up: speaker labels in SRT and VTT cues

Date: 2026-07-25

Release: `v1.3.8`

## Context

`v1.3.7` (commit `7843deb`) replaced the ~20-second Markdown-like SRT/VTT blocks
with phrase-level cues planned in `src/core/subtitles.py`. The reporter
confirmed the fix and asked for one follow-up: with diarization enabled, every
single cue starts with a speaker label, which is noisy and wastes line width.
The request is to name the speaker only when the speaker changes, the way plain
TXT and Markdown already do it in this project.

Current behavior:

- `generate_srt` prepends `<Спикер №1> ` to the first line of **every** cue that
  carries a speaker (`src/core/formatters.py:31-33`);
- `generate_vtt` prepends `<v Спикер №1>` to the first line of every cue
  (`src/core/formatters.py:49-51`);
- `build_subtitle_cues` reserves line width for that markup on **all** cues of a
  group (`_content_line_width`, `src/core/subtitles.py:164-167`), so a 64-column
  subtitle effectively wraps at ~49 columns even where no label is drawn;
- `_fit_speaker` truncates long speaker names against that same budget
  (`src/core/subtitles.py:144-161`), and the truncated name is what reaches the
  WebVTT voice span.

Two format facts drive the design; both were verified rather than assumed.

1. `<Спикер №1>` is not a defined SubRip tag. It is undefined territory:
   ffmpeg's `subrip` decoder passes it through as literal text (verified:
   converting a probe `.srt` to ASS keeps `<Спикер №1> Добрый день`), which is
   exactly what the reporter sees, while parsers that strip `<[^>]+>` — VLC's
   own subtitle decoder, most JavaScript SRT parsers — delete the label
   entirely. Plain `Спикер №1: ` is unambiguous in both families.
2. WebVTT's `<v annotation>` voice span is markup, not text. The W3C
   specification states the annotation is not rendered as visible text; it maps
   to `::cue(v[voice="…"])` for styling. Verified: ffmpeg's `webvtt` decoder
   drops the tag and emits only the dialogue. The spec's own multi-cue dialogue
   example repeats `<v …>` in each cue, because WebVTT keeps no parser state
   between cues.

Point 2 is the reason the two formats must diverge. In TXT and Markdown a reader
infers "still the same speaker" from document flow. WebVTT has no flow: each cue
is parsed independently, so a cue without `<v …>` is not a continuation of the
previous speaker, it is a cue with no speaker at all. Dropping the tag on
continuation cues would break per-speaker CSS styling in browsers, strip
attribution for VTT-consuming tools (Subtitle Edit, translation pipelines,
VTT → diarized transcript converters), and make attribution unrecoverable once
any tool re-splits or merges cues.

## Requirements

- SRT renders a visible speaker label only on the first cue of a speaker's
  speech; consecutive cues by the same speaker carry no label.
- The visible SRT label uses plain text in the existing project style
  (`Спикер №1: `), with no angle brackets.
- A long pause by the same speaker does not reintroduce the label; only a real
  speaker change does. This matches `generate_markdown` and the diarized TXT
  path (`src/core/processor.py:462-467`).
- VTT keeps a `<v …>` voice span on every diarized cue and passes the full,
  untruncated speaker name.
- Line-width budget is reserved only on cues that actually draw a visible
  label; all other cues get the full `max_line_width`.
- Speaker-name truncation applies only to the visible SRT label.
- SRT and VTT keep identical cue boundaries and timings for the same input.
- Non-diarized output is byte-for-byte unchanged.
- TXT, timecoded TXT, and Markdown are unchanged.
- No new user-facing setting; Desktop GUI, Web UI, CLI, and Rust TUI are
  untouched.

## Considered approaches

### Label on change in both formats, keeping current syntax

Track the previous speaker and skip the prefix when unchanged, leaving
`<Спикер №1>` and `<v Спикер №1>` as they are. Smallest diff. Rejected: it keeps
the undefined SRT tag that some parsers delete, and it strips WebVTT attribution
from continuation cues for no rendering benefit, since the voice span is
invisible in conforming players anyway.

### A `speaker_labels` option with `always` / `on_change` / `never`

Make the policy configurable and default it to `on_change`. Rejected for now:
nobody asked for `always` or `never`, subtitles already expose three settings,
and a fourth one costs `SubtitleOptions`, CLI flags, GUI widgets plus i18n
strings, Web UI form plus persistence, Rust TUI command plus its saved config,
and tests on all five surfaces. The policy stays in one place in the planner, so
adding the option later remains a small, local change.

### Format-aware split: visible label on change (SRT), voice span always (VTT)

Treat the visible label and the semantic attribution as two different outputs of
one planner decision. The planner marks which cue starts a new speaker and
budgets width for the visible label only there; SRT draws the label, VTT always
emits the voice span with the full name. Selected: it satisfies the request in
the format where the noise is real, keeps WebVTT correct, and incidentally
recovers ~15 columns of line width on every unlabeled cue.

## Selected architecture

### Cue contract

`SubtitleCue` carries two distinct fields:

- `speaker: str | None` — the full, untruncated speaker name, or `None` when
  diarization is off. Semantic attribution; consumed by VTT.
- `speaker_label: str | None` — the visible label to draw, already fitted to the
  line width. Non-`None` only on the cue that starts a new speaker's speech.
  Consumed by SRT.

Formatters stay pure renderers: they never compute when a speaker changes,
because only the planner can also charge the label to the width budget.

### Planner

`build_subtitle_cues` gains one piece of cross-group state: the speaker key of
the last cue for which a visible label was emitted. Groups already break both on
a speaker change and on a gap larger than `_MAX_JOIN_GAP_SECONDS`, so
"first cue of the group" is not a usable test — the same speaker resuming after
a 1.5-second pause opens a new group and must not be relabeled.

For each group:

- if the group's speaker key differs from the last labeled speaker key, the
  group's **first** cue receives `speaker_label` (fitted) and is wrapped at the
  reduced width; the last-labeled key is then updated;
- every other cue in the group, and every cue of a group whose speaker is
  unchanged, receives `speaker_label = None` and is wrapped at the full
  `max_line_width`;
- `speaker` is set to the full name on every cue with a speaker, regardless of
  labeling.

The label-pending state is threaded through the sentence loop inside
`flush_group`, because a group's first cue is the first cue of its first
sentence. `_split_long_words` is called with the width that applies to the
utterance being processed: the reduced width while a label is pending, the full
width otherwise.

### Width budget

`_content_line_width(width, label)` reserves `len(label) + len(": ")` and is
called only for a cue that draws a label. WebVTT markup no longer participates
in the budget at all, since it is invisible in conforming players; the
`_VTT_SPEAKER_MARKUP_OVERHEAD` constant is replaced by an SRT separator
constant. `_PREFERRED_MIN_TEXT_WIDTH_WITH_SPEAKER` keeps its role of guaranteeing
usable text room at small widths, and therefore still governs how aggressively a
long name is truncated.

Two consequences are deliberate. First, the whole labeled cue is wrapped at the
reduced width, not only its first line; a per-line width would buy a few columns
on one cue per turn and is not worth a second wrapping path. Second, diarized
cue boundaries will differ from `v1.3.7` output for the same input, because
unlabeled cues now fit more words per line. That is the intended improvement,
not a regression; only non-diarized output is required to stay identical.

### Rendering

```python
# generate_srt
if cue.speaker_label and cue_lines:
    cue_lines[0] = f"{cue.speaker_label}: {cue_lines[0]}"

# generate_vtt
if cue.speaker and cue_lines:
    cue_lines[0] = f"<v {cue.speaker}>{cue_lines[0]}"
```

The VTT voice span stays unclosed. The specification permits omitting `</v>`
when the voice span is the only component of the cue text, which is always true
here. This is a documented constraint, not an accident: **if a future change
adds any other markup to a cue (for example `<i>`), the closing `</v>` becomes
mandatory.**

### Unchanged paths

Non-diarized input has `speaker = None` on every utterance, so both formatters
take the same code path as today and produce identical bytes. `generate_markdown`,
the plain and diarized TXT builders in `TranscriptionProcessor`, and all
`SubtitleOptions` plumbing through CLI, GUI, Web, and TUI are untouched.

## Testing strategy

Tests are written before implementation.

New coverage in `tests/test_subtitles.py`:

- a single speaker across several cues yields `speaker_label` on the first cue
  only, and `speaker` on all of them;
- the same speaker resuming after a gap above `_MAX_JOIN_GAP_SECONDS` gets no
  second label;
- an A → B → A sequence yields three labels;
- unlabeled cues wrap at the full `max_line_width` while the labeled cue wraps
  at the reduced width;
- a speaker name too long for the budget is truncated in `speaker_label` and
  kept in full in `speaker`;
- non-diarized input yields `speaker is None` and `speaker_label is None`.

Updated coverage in `tests/test_formatters.py`:

- `test_generate_srt` expects `SPEAKER_00: второй третий` instead of
  `<SPEAKER_00> второй третий`;
- `test_srt_and_vtt_share_phrase_cues_and_line_wrapping` expects the plain SRT
  prefix and a full-name VTT voice span, and asserts SRT and VTT still produce
  the same number of cues with the same timings;
- `test_diarized_subtitle_prefix_respects_max_line_width` splits its assertion:
  every visible SRT line stays within `max_line_width` including the label,
  while VTT lines are measured after stripping the `<v …>` markup;
- a new test asserts a second cue by the same speaker carries no SRT label and
  still carries the VTT voice span.

Regression gates:

- `.venv/bin/python -m pytest tests/ -q` (three DPI-sensitive GUI layout tests
  may fail independently of this change; compare against a clean tree);
- `.venv/bin/python -m ruff check .`;
- manual check on the long real-world example from issue #37: phrase boundaries,
  timecodes, label placement at speaker changes, and line lengths at 2/64.

## Release and documentation

- Describe the change under the existing `## [Unreleased]` section of
  `docs/CHANGELOG.md`, where the other issue #37 entries already live: the SRT
  label change, the retained WebVTT attribution, and the wider lines.
- Bumping the macOS bundle version fields plus
  `tests/test_macos_packaging_config.py` to `1.3.8` and adding
  `docs/RELEASE_NOTES_1.3.8.md` happen when the release is cut, on request.
- Update the subtitle paragraphs in `README.md` and `README_EN.md` to state that
  the speaker is named on change in SRT and attributed on every cue in VTT.
- Run `graphify update .` after source changes.
- Commit on `main`. Pushing, tagging `v1.3.8`, building the macOS bundle, and
  replying on issue #37 happen only on explicit request.

## Non-goals

- Adding a user-facing speaker-label mode (`always` / `never`).
- Reintroducing the label after long pauses by the same speaker.
- Changing phrase segmentation, cue timing, or the sentence-split heuristics
  shipped in `v1.3.7`.
- Changing TXT, timecoded TXT, or Markdown output.
- Changing speaker naming in `src/core/diarization/mapping.py`
  (`Спикер №{n}` stays Russian-only).
- Adding closing `</v>` tags or other WebVTT markup.

## Success criteria

- A diarized SRT names each speaker once per turn, in plain text, and shows no
  angle brackets.
- A diarized VTT carries `<v …>` with the full speaker name on every cue.
- Unlabeled cues use the full configured line width; no visible SRT line exceeds
  `max_line_width` including its label.
- SRT and VTT cue counts and timecodes match for the same input.
- Non-diarized SRT and VTT output is unchanged.
- The full pytest suite and Ruff pass.
