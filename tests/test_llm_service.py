"""Характеризующие тесты llm_service — фиксируют диспетч и дивергенции GUI/web 1:1."""
import subprocess

import pytest

from src.services import llm_service


class _Proc:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_prompt_text_shape():
    text = llm_service.build_prompt_text("  привет  ", "  сделай саммари  ")
    assert text.startswith("Ты обрабатываешь транскрипт на русском языке. Не выдумывай факты")
    assert "Инструкция:\nсделай саммари" in text
    assert "Транскрипт:\nпривет" in text
    assert text.endswith("\n")


def test_build_prompt_text_matches_legacy_literal():
    # эталон, ранее продублированный в app_qt.py и web_app.py
    expected = (
        "Ты обрабатываешь транскрипт на русском языке. "
        "Не выдумывай факты, явно помечай неясности.\n\n"
        "Инструкция:\nP\n\n"
        "Транскрипт:\nT\n"
    )
    assert llm_service.build_prompt_text("T", "P") == expected


def test_run_provider_unknown_raises():
    with pytest.raises(llm_service.UnknownLLMProvider) as exc:
        llm_service.run_provider({}, "t", "p", provider="Nope", strict_empty_cli=True)
    assert exc.value.provider == "Nope"


def test_api_provider_forwards_stream_callback(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, settings):
            captured["settings"] = settings

        def process_transcript(self, text, prompt, stream_callback=None):
            stream_callback("часть")
            return "ответ"

    monkeypatch.setattr(llm_service, "LLMClient", FakeClient)
    chunks = []

    result = llm_service.run_provider(
        {"api_url": "https://example.test", "api_key": "key", "model": "model", "temperature": 0.2},
        "текст", "промпт", provider="API", strict_empty_cli=True, on_stream_chunk=chunks.append,
    )

    assert result == "ответ"
    assert chunks == ["часть"]


def test_claude_empty_strict_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, "", ""))
    with pytest.raises(llm_service.EmptyLLMResponse):
        llm_service.run_provider(
            {"claude_path": "claude"}, "t", "p", provider="Claude Code", strict_empty_cli=True,
        )


def test_claude_empty_nonstrict_returns_empty(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, "", ""))
    result = llm_service.run_provider(
        {"claude_path": "claude"}, "t", "p", provider="Claude Code", strict_empty_cli=False,
    )
    assert result == ""


def test_claude_nonempty_returns_stripped(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, "  ответ  ", ""))
    result = llm_service.run_provider(
        {"claude_path": "claude"}, "t", "p", provider="Claude Code", strict_empty_cli=True,
    )
    assert result == "ответ"


def test_claude_error_returncode_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, "", "boom"))
    with pytest.raises(RuntimeError, match="boom"):
        llm_service.run_provider(
            {"claude_path": "claude"}, "t", "p", provider="Claude Code", strict_empty_cli=True,
        )


def test_codex_uses_json_output_without_a_shared_model_and_reads_agent_message(monkeypatch):
    captured = {}

    def fake_run(command, *args, **kwargs):
        captured["command"] = command
        output_path = command[command.index("-o") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            output.write("fallback answer")
        return _Proc(
            0,
            '{"type":"item.completed","item":{"type":"agent_message","text":"final answer"}}\n',
            "Codex startup progress",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = llm_service.run_provider(
        {"codex_path": "codex", "model": "shared-api-model"},
        "T", "P", provider="Codex", strict_empty_cli=True,
    )

    assert result == "final answer"
    assert captured["command"][:4] == ["codex", "exec", "--json", "-o"]
    assert "-m" not in captured["command"]
    assert captured["command"][-1] == "-"


def test_codex_uses_output_file_when_json_has_no_agent_message(monkeypatch):
    def fake_run(command, *args, **kwargs):
        output_path = command[command.index("-o") + 1]
        with open(output_path, "w", encoding="utf-8") as output:
            output.write("  file answer  ")
        return _Proc(0, '{"type":"thread.started"}\n', "progress banner")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = llm_service.run_provider(
        {"codex_path": "codex"}, "T", "P", provider="Codex", strict_empty_cli=True,
    )

    assert result == "file answer"


def test_codex_failure_surfaces_concise_actionable_diagnostics(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Proc(2, "", "authentication failed"))

    with pytest.raises(RuntimeError, match=r"Codex failed \(exit 2\).*codex login"):
        llm_service.run_provider(
            {"codex_path": "codex"}, "T", "P", provider="Codex", strict_empty_cli=True,
        )


def test_opencode_empty_always_strict(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, "", ""))
    with pytest.raises(llm_service.EmptyLLMResponse):
        llm_service.run_provider(
            {"opencode_path": "opencode"}, "t", "p", provider="OpenCode", strict_empty_cli=False,
        )


def test_opencode_command_shape(monkeypatch):
    captured = {}

    def fake_run(command, *a, **k):
        captured["cmd"] = command
        return _Proc(0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm_service.run_provider(
        {"opencode_path": "oc", "model": "m", "opencode_args": "--flag x"},
        "T", "P", provider="OpenCode", strict_empty_cli=True,
    )
    assert captured["cmd"][0] == "oc"
    assert "--model" in captured["cmd"] and "m" in captured["cmd"]
    assert "--flag" in captured["cmd"] and "x" in captured["cmd"]
    # последний аргумент — собранный prompt
    assert captured["cmd"][-1] == llm_service.build_prompt_text("T", "P")


def test_cancelled_cli_provider_terminates_its_subprocess(monkeypatch):
    class HangingProcess:
        returncode = None

        def __init__(self):
            self.terminated = False

        def communicate(self, timeout=None):
            if self.terminated:
                return "", ""
            raise subprocess.TimeoutExpired("opencode", timeout)

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.terminate()

    process = HangingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(llm_service.LLMCancelled):
        llm_service.run_provider(
            {"opencode_path": "opencode"}, "t", "p", provider="OpenCode",
            strict_empty_cli=True, cancel_check=lambda: True,
        )

    assert process.terminated is True
