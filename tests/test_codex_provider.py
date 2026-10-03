import json
from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from app import codex_provider as codex
from app.main import app
from app.lmstudio import normalize, SCHEMA
from app.translation import available_languages, check_translation, clear_translation_cache


def test_existing_chatgpt_login_is_required():
    with patch.object(codex, "executable", return_value="/usr/bin/codex"), patch.object(codex.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT")
        codex.require_login()
        run.return_value = subprocess.CompletedProcess([], 0, "Logged in using an API key", "")
        with pytest.raises(ValueError, match="Sign in"):
            codex.require_login()


def test_cli_is_isolated_and_does_not_receive_api_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-use")
    monkeypatch.setenv("CODEX_API_KEY", "do-not-use")
    def launch(command, **kwargs):
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "features.shell_tool=true" not in command
        assert command[command.index("--disable") + 1] == "shell_tool"
        assert "OPENAI_API_KEY" not in kwargs["env"] and "CODEX_API_KEY" not in kwargs["env"]
        assert kwargs["start_new_session"]
        assert Path(kwargs["cwd"]).name.startswith("simple-recipes-codex-")
        output = Path(command[command.index("--output-last-message") + 1])
        process = MagicMock(returncode=0)
        def communicate(prompt, timeout):
            assert prompt == "recipe text"
            output.write_text('{"text":"translated recipe"}')
            return "", ""
        process.communicate.side_effect = communicate
        return process
    with patch.object(codex, "require_login"), patch.object(codex, "executable", return_value="/usr/bin/codex"), patch.object(codex.subprocess, "Popen", side_effect=launch):
        assert codex.text("recipe text", "chosen-model") == "translated recipe"


def test_timeout_kills_cli_process_group():
    process = MagicMock(pid=123, returncode=0)
    process.communicate.side_effect = [subprocess.TimeoutExpired("codex", 1), ("", "")]
    with patch.object(codex, "require_login"), patch.object(codex, "executable", return_value="codex"), patch.object(codex.subprocess, "Popen", return_value=process), patch.object(codex.os, "killpg") as kill:
        with pytest.raises(ValueError, match="timed out"):
            codex.complete("text", timeout=1)
    kill.assert_called_once_with(123, codex.signal.SIGKILL)


def test_failure_does_not_expose_cli_output():
    process = MagicMock(returncode=1)
    process.communicate.return_value = ("private recipe", "private token")
    with patch.object(codex, "require_login"), patch.object(codex, "executable", return_value="codex"), patch.object(codex.subprocess, "Popen", return_value=process):
        with pytest.raises(ValueError) as error:
            codex.complete("text")
    assert "private" not in str(error.value)


def test_recipe_processing_uses_codex_recipe_schema():
    result = {"title": "Soupe"}
    with patch.object(codex, "complete", return_value=result) as complete, patch("app.lmstudio.httpx.post") as post:
        assert normalize({"title": "Soup"}, base_url=codex.BASE_URL, model="chosen", target_lang="fr") == result
    assert "French" in complete.call_args.args[0]
    assert complete.call_args.args[1:] == ("chosen", SCHEMA["json_schema"]["schema"])
    post.assert_not_called()


def test_batched_languages_validate_samples_and_cache_for_import():
    clear_translation_cache()
    with patch.object(codex, "available", return_value=True), patch.object(codex, "complete", return_value={
        "en": "Add 2 grams of salt.", "fr": "Ajoutez 2 grammes de sel.",
        "zh": "加入2克盐。", "es": "Añade 20 gramos de sal."}) as complete:
        result = available_languages(codex.BASE_URL, "chosen")
        assert {row["code"] for row in result["target_languages"]} == {"en", "fr", "zh"}
        assert {row["code"] for row in result["layout_languages"]} == {"en", "de", "fr", "it", "es"}
        assert check_translation(codex.BASE_URL, "chosen", "fr", "unused-old-api-key")["cached"]
        complete.assert_called_once()
    clear_translation_cache()


def test_selecting_codex_requires_login_before_persisting():
    with patch.object(codex, "require_login", side_effect=ValueError("Sign in")):
        assert TestClient(app).post("/api/ai/select", data={"provider": "codex", "ai_model": "chosen"}).status_code == 409


def test_provider_visible_on_import_and_settings_without_api_key():
    client = TestClient(app)
    for url in ("/", "/einstellungen"):
        response = client.get(url)
        assert 'value="codex"' in response.text
        assert "existing ChatGPT login" in response.text
