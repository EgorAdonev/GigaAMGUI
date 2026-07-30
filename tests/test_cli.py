import json

import cli


def test_cli_stats_manager_writes_to_configured_path(tmp_path, monkeypatch):
    stats_file = tmp_path / "writable results" / "processing_stats.json"
    monkeypatch.setattr(cli, "STATS_FILE", str(stats_file), raising=False)

    stats = cli._create_stats_manager()
    stats.add_processing_record(
        file_path="fixture.wav",
        file_size=1024,
        duration=10.0,
        conversion_time=1.0,
        transcription_time=2.0,
    )

    payload = json.loads(stats_file.read_text(encoding="utf-8"))
    assert payload["history"][0]["file_name"] == "fixture.wav"
