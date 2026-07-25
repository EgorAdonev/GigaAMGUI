# GigaAM Transcriber 1.3.8

## Русский

Релиз 1.3.8 закрывает follow-up к [issue #37](https://github.com/dubr1k/GigaAMGUI/issues/37): в диаризованных субтитрах имя спикера больше не повторяется в каждом блоке.

### Что изменилось

- SRT называет спикера только при смене говорящего — как это давно делают TXT и Markdown. Долгая пауза того же спикера метку не повторяет.
- Формат метки в SRT изменён с `<Спикер №1>` на обычный текст `Спикер №1:`. Угловые скобки не являются тегом SubRip: ffmpeg выводит их буквально, а плееры и парсеры, вырезающие `<...>`, удаляют метку целиком.
- VTT сохраняет стандартный voice span `<v Спикер №1>` на каждом cue. WebVTT не переносит состояние между cues, поэтому cue без него теряет атрибуцию: ломается стилизация `::cue(v[voice="..."])` и обработка внешними инструментами. Аннотация невидима в конформных плеерах, поэтому визуально ничего не дублируется.
- Имя в VTT больше не обрезается: длинные имена сокращаются только в видимой SRT-метке.
- Ширина строки резервируется под метку только в тех cue, где её печатают. Остальные cue используют всю настроенную длину строки — при 64 символах и имени `Спикер №1` это возвращает около 11 символов на строку.
- Длинное слово, разрезанное под узкую строку, снова склеивается без пробела. Раньше при малых значениях `--subtitle-max-width` внутрь слова мог попасть пробел и изменить границы слов для потребителей субтитров.
- Сокращённая метка спикера больше не начинается с пробела при экстремально узкой строке.
- TXT, таймкодированный TXT и Markdown не изменены.

### Интерфейсы

- Новых настроек нет. Поведение меток спикеров не конфигурируется: Desktop GUI, Web GUI, Python CLI и Rust TUI работают как раньше и передают те же три параметра субтитров.
- Существующие `--subtitle-sentence-split`, `--subtitle-max-lines`, `--subtitle-max-width` и команды TUI `/subtitle-split`, `/subtitle-lines`, `/subtitle-width` не изменились.

### Проверка

- Оба факта о форматах, на которых держится решение, проверены запуском ffmpeg, а не по памяти: `subrip` пропускает `<Спикер №1>` как обычный текст, `webvtt` полностью вырезает `<v ...>`.
- Обратная совместимость доказана побайтово: SRT и VTT для недиаризованного входа сгенерированы на базовом коммите и на релизном для 36 комбинаций настроек — 38119 байт, идентичны.
- Проверено, что ни одна видимая строка SRT не превышает `max_line_width` вместе с меткой, включая случайную выборку по ширинам, длинам имён и токенам до 90 символов.
- Добавлены тесты, фиксирующие намеренные решения: метка не возвращается после паузы, промежуточная группа без спикера не сбрасывает состояние, `sentence_split=False` с диаризацией, пустое имя спикера, склейка разрезанного слова.
- 659 Python-тестов проходят; два предсуществующих падения вызваны файлом `.env` в корне репозитория и воспроизводятся на базовом коммите.
- Ruff чист на всех изменённых файлах.

---

## English

Release 1.3.8 closes the follow-up on [issue #37](https://github.com/dubr1k/GigaAMGUI/issues/37): diarized subtitles no longer repeat the speaker name in every block.

### What changed

- SRT names a speaker only when the speaker changes, the way TXT and Markdown have always done. A long pause by the same speaker does not reintroduce the label.
- The SRT label format changed from `<Спикер №1>` to plain `Спикер №1:`. Angle brackets are not a SubRip tag: ffmpeg emits them literally, while players and parsers that strip `<...>` delete the label entirely.
- VTT keeps a standard `<v Спикер №1>` voice span on every cue. WebVTT carries no state between cues, so a cue without one loses attribution — breaking `::cue(v[voice="..."])` styling and downstream tooling. The annotation is not rendered by conforming players, so nothing is visually duplicated.
- The VTT name is no longer truncated; long names are shortened only in the visible SRT label.
- Line width is reserved for the label only on cues that draw one. Every other cue uses the full configured width, which returns roughly 11 columns per line at width 64 with the name `Спикер №1`.
- A long word split to fit a narrow line is rejoined without a space. Previously small `--subtitle-max-width` values could inject a space inside a word and change word boundaries for subtitle consumers.
- A truncated speaker label no longer starts with a space at extremely narrow widths.
- TXT, timecoded TXT, and Markdown are unchanged.

### Interfaces

- No new settings. Speaker labelling is not configurable: Desktop GUI, Web GUI, Python CLI, and Rust TUI behave as before and pass the same three subtitle options.
- The existing `--subtitle-sentence-split`, `--subtitle-max-lines`, `--subtitle-max-width` flags and the TUI `/subtitle-split`, `/subtitle-lines`, `/subtitle-width` commands are unchanged.

### Validation

- Both format facts the design rests on were verified by running ffmpeg rather than from memory: the `subrip` decoder passes `<Спикер №1>` through as literal text, and the `webvtt` decoder drops `<v ...>` entirely.
- Backward compatibility is proven byte-for-byte: non-diarized SRT and VTT were generated at the base commit and at the release commit across 36 option combinations — 38119 bytes, identical.
- No visible SRT line exceeds `max_line_width` including its label, confirmed by a randomized sweep over widths, speaker-name lengths, and tokens up to 90 characters.
- New tests pin the deliberate decisions: no relabel after a pause, an intervening speaker-less group does not reset the state, `sentence_split=False` with diarization, a blank speaker name, and split-word rejoining.
- 659 Python tests pass; two pre-existing failures come from a repo-root `.env` file and reproduce on the base commit.
- Ruff is clean on every changed file.
