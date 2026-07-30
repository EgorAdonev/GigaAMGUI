## Русский

- Исправлено ложное сообщение о повторном скачивании моделей Pyannote при каждом запуске диаризации.
- Проверка локальных моделей теперь использует фактический каталог `HF_HUB_CACHE`, выбранный библиотекой Hugging Face Hub.
- Если модели уже загружены, приложение сразу переходит к их загрузке в память; реальное скачивание показывается только для действительно отсутствующих моделей.

## English

- Fixed the false Pyannote model re-download message shown on every diarization run.
- Local model detection now uses the actual `HF_HUB_CACHE` directory selected by Hugging Face Hub.
- Cached models now proceed directly to loading; the download stage is shown only when model files are genuinely missing.
