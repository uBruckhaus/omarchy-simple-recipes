import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app import claude_provider as claude
from app import cli_providers


def test_login_status_uses_claude_auth_json():
    with patch.object(claude, "executable", return_value="/usr/bin/claude"), patch.object(claude.subprocess, "run") as run:
        run.return_value = MagicMock(returncode=0, stdout=json.dumps({"loggedIn": True}))
        claude.require_login()
        run.return_value = MagicMock(returncode=0, stdout=json.dumps({"loggedIn": False}))
        with pytest.raises(ValueError):
            claude.require_login()


def test_complete_runs_without_tools_and_returns_structured_output(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    process = MagicMock(returncode=0, pid=1)
    process.communicate.return_value = (json.dumps({"is_error": False, "structured_output": {"text": "Salz"}}), "")
    with patch.object(claude, "require_login"), patch.object(claude, "executable", return_value="claude"), \
         patch.object(claude.subprocess, "Popen", return_value=process) as popen:
        assert claude.text("recipe", "haiku") == "Salz"
    command = popen.call_args.args[0]
    assert command[command.index("--tools") + 1] == ""
    assert "--no-session-persistence" in command and "--strict-mcp-config" in command
    assert command[command.index("--model") + 1] == "haiku"
    assert "ANTHROPIC_API_KEY" not in popen.call_args.kwargs["env"]


def test_complete_reports_errors_and_timeouts():
    process = MagicMock(returncode=1, pid=7)
    process.communicate.return_value = (json.dumps({"is_error": True}), "")
    with patch.object(claude, "require_login"), patch.object(claude, "executable", return_value="claude"), patch.object(claude.subprocess, "Popen", return_value=process):
        with pytest.raises(ValueError):
            claude.complete("text")
    process.communicate.side_effect = [subprocess.TimeoutExpired("claude", 1), ("", "")]
    with patch.object(claude, "require_login"), patch.object(claude, "executable", return_value="claude"), \
         patch.object(claude.subprocess, "Popen", return_value=process), patch.object(claude.os, "killpg") as kill:
        with pytest.raises(ValueError, match="timed out"):
            claude.complete("text", timeout=1)
    kill.assert_called_once()


def test_recipe_processing_routes_to_claude():
    from app.lmstudio import normalize
    result = {"title": "Soupe", "ingredients": ["sel"], "instructions": ["Cuire"]}
    with patch.object(claude, "complete", return_value=result) as complete, patch("app.lmstudio.httpx.post") as post:
        assert normalize({"title": "Soup"}, base_url=claude.BASE_URL, model="sonnet", target_lang="fr") == result
    complete.assert_called_once(); post.assert_not_called()


def test_detected_prefers_claude_then_codex():
    with patch.object(cli_providers.claude_provider, "available", return_value=True), \
         patch.object(cli_providers.codex_provider, "available", return_value=True):
        assert cli_providers.detected() == ["claude", "codex"]
    with patch.object(cli_providers.claude_provider, "available", return_value=False), \
         patch.object(cli_providers.codex_provider, "available", return_value=True):
        assert cli_providers.detected() == ["codex"]


def test_non_ascii_schema_keys_are_aliased_and_restored():
    schema = {"type": "object", "properties": {"category.Frühstück": {"type": "string"}, "ui.title": {"type": "string"}},
              "required": ["category.Frühstück", "ui.title"], "additionalProperties": False}
    process = MagicMock(returncode=0, pid=1)
    process.communicate.return_value = (json.dumps({"structured_output": {"key_0": "朝食", "ui.title": "タイトル"}}), "")
    with patch.object(claude, "require_login"), patch.object(claude, "executable", return_value="claude"), \
         patch.object(claude.subprocess, "Popen", return_value=process) as popen:
        assert claude.complete("labels", "sonnet", schema) == {"category.Frühstück": "朝食", "ui.title": "タイトル"}
    command = popen.call_args.args[0]
    sent = json.loads(command[command.index("--json-schema") + 1])
    assert list(sent["properties"]) == ["key_0", "ui.title"] and sent["required"] == ["key_0", "ui.title"]
