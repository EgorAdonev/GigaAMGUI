# GigaAM Transcriber 1.4.6

## Русский

### Безопасность

- Из зависимостей полностью исключены пакеты OpenTelemetry
  (opentelemetry-api/sdk/exporter-otlp*/proto/semantic-conventions): код
  приложения их не импортирует, ни одна зависимость их не требует.
- Это устраняет срабатывания сканера уязвимостей на
  opentelemetry-exporter-otlp-proto-grpc (CVE-2023-33953, CVE-2023-44487,
  CVE-2023-4785, CVE-2023-32732). Все перечисленные CVE затрагивают только
  gRPC <= 1.53.x; реальный grpcio в сборке — 1.76.0, срабатывание было ложным
  (сканер отображал версию PyPI-пакета на CPE `grpc:grpc`), но теперь
  компонент отсутствует в поставке целиком.
- Сборки всех платформ прошли дымовые тесты без OpenTelemetry (selfcheck,
  offline-models-smoke с HF_HUB_OFFLINE=1, sortformer-onnx-smoke).

## English

### Security

- Removed the OpenTelemetry packages from dependencies entirely
  (opentelemetry-api/sdk/exporter-otlp*/proto/semantic-conventions): the
  application code does not import them and no dependency requires them.
- This eliminates the dependency-scanner findings against
  opentelemetry-exporter-otlp-proto-grpc (CVE-2023-33953, CVE-2023-44487,
  CVE-2023-4785, CVE-2023-32732). All of these CVEs affect only
  gRPC <= 1.53.x; the actually bundled grpcio is 1.76.0, so the match was a
  false positive (the scanner mapped the PyPI package version onto the
  `grpc:grpc` CPE) — but the component is now absent from the distribution
  altogether.
- All platform builds passed their smoke gates without OpenTelemetry
  (selfcheck, offline-models-smoke with HF_HUB_OFFLINE=1,
  sortformer-onnx-smoke).
