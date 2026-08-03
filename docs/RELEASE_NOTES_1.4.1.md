# GigaAM Transcriber 1.4.1

## Русский

### Исправления

- Исправлена [#41](https://github.com/dubr1k/GigaAMGUI/issues/41): пакетная LLM-обработка больше не принудительно включает streaming API. Обычные JSON-ответы OpenAI-compatible и Anthropic-провайдеров снова обрабатываются корректно.
- Windows portable и offline-сборки теперь устанавливают и вшивают PyAudioWPatch до PyInstaller. Списки устройств live-захвата снова заполняются в новых Windows-релизах; при отсутствии runtime приложение показывает понятную причину вместо необработанного `ImportError`.
- Live-транскрибация корректно завершает предложения с Unicode-многоточием и с пунктуацией перед закрывающими кавычками или скобками.

### Обновление

- Для Windows live-захвата скачайте новый portable или offline-архив этого релиза. Уже загруженные offline-архивы не могут получить нативную зависимость без пересборки.

## English

### Fixes

- Fixed [#41](https://github.com/dubr1k/GigaAMGUI/issues/41): batch LLM post-processing no longer forces the streaming API. Regular JSON responses from OpenAI-compatible and Anthropic providers are processed correctly again.
- Windows portable and offline builds now install and bundle PyAudioWPatch before PyInstaller. Live-capture device lists populate in new Windows releases, and a missing runtime is reported clearly instead of raising an unhandled `ImportError`.
- Live transcription now recognizes Unicode ellipses and punctuation followed by closing quotation marks or brackets as sentence endings.

### Upgrade

- Download the new Windows portable or offline archive for live capture. Existing offline archives cannot acquire the native dependency without being rebuilt.
