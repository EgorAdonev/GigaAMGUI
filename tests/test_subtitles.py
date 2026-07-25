"""Тесты семантической разбивки SRT/VTT на subtitle cues."""

from __future__ import annotations

import pytest

from src.core.subtitles import SubtitleOptions, build_subtitle_cues


def test_build_subtitle_cues_splits_sentences_using_word_timestamps():
    utterances = [
        {
            "transcription": (
                "Петр, время и температура запекания коржей. "
                "Сорок минут, сто восемьдесят градусов. Мимо!"
            ),
            "boundaries": (45.0, 53.0),
            "words": [
                {"text": "Петр,", "start": 45.2, "end": 45.6},
                {"text": "время", "start": 45.7, "end": 46.0},
                {"text": "и", "start": 46.1, "end": 46.2},
                {"text": "температура", "start": 46.3, "end": 46.9},
                {"text": "запекания", "start": 47.0, "end": 47.6},
                {"text": "коржей.", "start": 47.7, "end": 48.7},
                {"text": "Сорок", "start": 49.0, "end": 49.4},
                {"text": "минут,", "start": 49.5, "end": 50.0},
                {"text": "сто", "start": 50.1, "end": 50.4},
                {"text": "восемьдесят", "start": 50.5, "end": 51.1},
                {"text": "градусов.", "start": 51.2, "end": 51.8},
                {"text": "Мимо!", "start": 52.2, "end": 52.6},
            ],
        }
    ]

    cues = build_subtitle_cues(utterances, SubtitleOptions())

    assert [" ".join(cue.lines) for cue in cues] == [
        "Петр, время и температура запекания коржей.",
        "Сорок минут, сто восемьдесят градусов.",
        "Мимо!",
    ]
    assert [(cue.start, cue.end) for cue in cues] == [
        (45.2, 48.7),
        (49.0, 51.8),
        (52.2, 52.6),
    ]


def test_build_subtitle_cues_splits_long_sentence_to_line_limits():
    tokens = [
        "первое", "второе", "третье", "четвертое", "пятое",
        "шестое", "седьмое", "восьмое", "девятое.",
    ]
    utterance = {
        "transcription": " ".join(tokens),
        "boundaries": (10.0, 19.0),
        "words": [
            {"text": token, "start": 10.0 + index, "end": 10.8 + index}
            for index, token in enumerate(tokens)
        ],
    }

    cues = build_subtitle_cues(
        [utterance],
        SubtitleOptions(max_line_count=2, max_line_width=20),
    )

    assert len(cues) > 1
    assert all(len(cue.lines) <= 2 for cue in cues)
    assert all(len(line) <= 20 for cue in cues for line in cue.lines)
    assert " ".join(word for cue in cues for line in cue.lines for word in line.split()) == " ".join(tokens)
    assert cues[0].start == 10.0
    assert cues[-1].end == 18.8


def test_build_subtitle_cues_falls_back_to_proportional_timings_without_words():
    cues = build_subtitle_cues(
        [{"transcription": "Раз. Два слова.", "boundaries": (0.0, 4.0)}],
        SubtitleOptions(),
    )

    assert [" ".join(cue.lines) for cue in cues] == ["Раз.", "Два слова."]
    assert cues[0].start == 0.0
    assert cues[-1].end == 4.0
    assert all(cue.start < cue.end for cue in cues)
    assert all(
        left.end <= right.start
        for left, right in zip(cues, cues[1:], strict=False)
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_line_count": 0},
        {"max_line_count": 5},
        {"max_line_width": 19},
        {"max_line_width": 101},
    ],
)
def test_subtitle_options_reject_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        SubtitleOptions(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"sentence_split": 1}, "sentence_split"),
        ({"max_line_count": True}, "max_line_count"),
        ({"max_line_width": 64.5}, "max_line_width"),
    ],
)
def test_subtitle_options_reject_invalid_types(kwargs, field):
    with pytest.raises(TypeError, match=field):
        SubtitleOptions(**kwargs)


def test_build_subtitle_cues_uses_fallback_when_word_timings_are_invalid():
    cues = build_subtitle_cues([
        {
            "transcription": "Привет мир.",
            "boundaries": (2.0, 4.0),
            "words": [
                {"text": "Привет", "start": "broken", "end": 2.5},
                {"text": "мир.", "start": 3.0, "end": 4.0},
            ],
        }
    ])

    assert len(cues) == 1
    assert cues[0].start == 2.0
    assert cues[0].end == 4.0
    assert " ".join(cues[0].lines) == "Привет мир."


def test_build_subtitle_cues_enforces_limits_for_a_single_long_token():
    token = "сверхдлинноесловобезпробелов" * 3
    cues = build_subtitle_cues(
        [{
            "transcription": token,
            "boundaries": (1.0, 4.0),
            "words": [{"text": token, "start": 1.0, "end": 4.0}],
        }],
        SubtitleOptions(max_line_count=2, max_line_width=20),
    )

    assert all(len(cue.lines) <= 2 for cue in cues)
    assert all(len(line) <= 20 for cue in cues for line in cue.lines)
    assert "".join(line for cue in cues for line in cue.lines) == token
    assert cues[0].start == 1.0
    assert cues[-1].end == 4.0


def test_build_subtitle_cues_joins_contiguous_segments_into_one_sentence():
    cues = build_subtitle_cues([
        {
            "transcription": "Это начало",
            "boundaries": (0.0, 1.0),
            "words": [
                {"text": "Это", "start": 0.0, "end": 0.4},
                {"text": "начало", "start": 0.4, "end": 1.0},
            ],
        },
        {
            "transcription": "одного предложения.",
            "boundaries": (1.0, 2.0),
            "words": [
                {"text": "одного", "start": 1.0, "end": 1.4},
                {"text": "предложения.", "start": 1.4, "end": 2.0},
            ],
        },
    ])

    assert len(cues) == 1
    assert " ".join(cues[0].lines) == "Это начало одного предложения."
    assert (cues[0].start, cues[0].end) == (0.0, 2.0)


def test_build_subtitle_cues_rejects_overlapping_word_timings():
    cues = build_subtitle_cues([
        {
            "transcription": "Первое. Второе.",
            "boundaries": (0.0, 3.0),
            "words": [
                {"text": "Первое.", "start": 0.0, "end": 2.0},
                {"text": "Второе.", "start": 1.0, "end": 3.0},
            ],
        }
    ])

    assert len(cues) == 2
    assert cues[0].end <= cues[1].start
    assert [" ".join(cue.lines) for cue in cues] == ["Первое.", "Второе."]


def test_build_subtitle_cues_uses_fallback_for_non_string_word_text():
    cues = build_subtitle_cues([
        {
            "transcription": "Привет.",
            "boundaries": (0.0, 1.0),
            "words": [{"text": None, "start": 0.0, "end": 1.0}],
        },
        {"transcription": None, "boundaries": (1.0, 2.0)},
    ])

    assert [" ".join(cue.lines) for cue in cues] == ["Привет."]


def test_build_subtitle_cues_uses_fallback_for_incomplete_word_list():
    utterances = [{
        "transcription": "Первое второе.",
        "boundaries": (0.0, 2.0),
        "words": [{"text": "второе.", "start": 1.0, "end": 2.0}],
    }]

    cues = build_subtitle_cues(utterances)

    assert len(cues) == 1
    assert cues[0].start == pytest.approx(0.0)
    assert cues[0].end == pytest.approx(2.0)
    assert cues[0].lines == ("Первое второе.",)


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


def test_labeled_cue_lines_fit_budget_when_group_continues():
    # Продолжение группы (тот же спикер, пауза <= _MAX_JOIN_GAP_SECONDS) должно
    # делиться по суженной ширине, пока метка ещё не напечатана, иначе длинное
    # слово из продолжения может попасть в cue с меткой и превысить бюджет.
    long_word = "abcdefghijklmnopqrstuvwxyz012345678ab."
    utterances = [
        {
            "transcription": "Слово",
            "boundaries": (0.0, 0.5),
            "speaker": "S1",
            "words": [{"text": "Слово", "start": 0.0, "end": 0.5}],
        },
        {
            "transcription": long_word,
            "boundaries": (0.6, 2.0),
            "speaker": "S1",
            "words": [{"text": long_word, "start": 0.6, "end": 2.0}],
        },
    ]
    options = SubtitleOptions(max_line_count=2, max_line_width=40)

    cues = build_subtitle_cues(utterances, options)

    assert cues[0].speaker_label == "S1"
    budget = options.max_line_width - len(cues[0].speaker_label) - 2
    for line in cues[0].lines:
        assert len(line) <= budget
