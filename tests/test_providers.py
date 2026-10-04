import json
from unittest.mock import MagicMock, patch

from app import ai_config, local_runtime
from app import recipe_store as store


def test_lmstudio_is_available_when_only_the_lms_cli_is_installed():
    with patch.object(ai_config, "lmstudio_cli", return_value="/home/u/.lmstudio/bin/lms"), patch.object(ai_config, "lmstudio_running", return_value=False):
        assert ai_config.get_provider_status("lmstudio") == (True, "provider_ready")
    with patch.object(ai_config, "lmstudio_cli", return_value=""), patch.object(ai_config, "lmstudio_running", return_value=False):
        assert ai_config.get_provider_status("lmstudio") == (False, "provider_not_installed")


def test_lmstudio_models_come_from_lms_catalog_when_server_is_down():
    listing = MagicMock(stdout=json.dumps([{"type": "embedding", "modelKey": "nomic"}, {"type": "llm", "modelKey": "gemma-4-e2b-it"}]))
    with patch.object(ai_config.httpx, "get", side_effect=ai_config.httpx.ConnectError("down")), \
         patch.object(ai_config, "lmstudio_cli", return_value="lms"), patch("subprocess.run", return_value=listing):
        assert ai_config.get_lmstudio_models() == ["gemma-4-e2b-it"]


def test_ollama_models_are_discovered():
    response = MagicMock(); response.json.return_value = {"models": [{"name": "llama3.2:latest"}, {"name": "nomic-embed-text"}]}
    with patch.object(ai_config.httpx, "get", return_value=response):
        assert ai_config.get_ollama_models() == ["llama3.2"]


def test_online_models_are_listed_for_a_saved_key():
    ai_config._online_models.clear()
    response = MagicMock(); response.json.return_value = {"data": [{"id": "grok-4"}, {"id": "grok-2-image"}, {"id": "models/grok-3-mini"}]}
    with patch.object(ai_config.httpx, "get", return_value=response) as get:
        assert ai_config.get_online_models("xai", "xai-key") == ["grok-3-mini", "grok-4"]
        assert ai_config.get_online_models("xai", "xai-key") == ["grok-3-mini", "grok-4"]
    get.assert_called_once()
    assert get.call_args.args[0] == "https://api.x.ai/v1/models"
    assert ai_config.get_online_models("xai", "") == [] and ai_config.get_online_models("lmstudio", "k") == []


def test_xai_needs_a_key():
    assert ai_config.PROVIDERS["xai"]["needs_key"]
    with patch.object(store, "setting", return_value=""), patch.dict("os.environ", {}, clear=False):
        assert ai_config.get_provider_status("xai") == (False, "provider_not_configured")


def test_lmstudio_server_is_started_before_loading_model():
    states = iter([False, False, True])
    with patch("app.ai_config.lmstudio_running", side_effect=lambda: next(states)), patch("app.ai_config.lmstudio_cli", return_value="lms"), \
         patch.object(local_runtime.subprocess, "run") as run, patch.object(local_runtime, "load_model") as load, patch.object(local_runtime.time, "sleep"), \
         patch.object(local_runtime, "_lmstudio_catalog", return_value=[]), patch.object(local_runtime, "require_vram"):
        local_runtime.ensure_lmstudio("gemma")
    assert run.call_args.args[0] == ["lms", "server", "start"]
    load.assert_called_once_with("gemma", "lmstudio")
    local_runtime._lmstudio_server_started = False


def test_releasing_lmstudio_unloads_every_loaded_instance():
    listing = MagicMock(); listing.json.return_value = {"models": [
        {"key": "mine", "loaded_instances": [{"id": "mine-1"}]}, {"key": "other", "loaded_instances": [{"id": "other-1"}]}]}
    with patch.object(local_runtime.httpx, "get", return_value=listing), patch.object(local_runtime.httpx, "post") as post:
        local_runtime.release_lmstudio()
    assert [call.kwargs["json"] for call in post.call_args_list] == [{"instance_id": "mine-1"}, {"instance_id": "other-1"}]


def test_shipped_interface_languages_load_without_a_model():
    from app import interface_languages
    from app.i18n import t
    with patch.object(interface_languages, "shipped", side_effect=lambda code: {"native.import_tab": "取り込み", "ui.ingredients": "材料"} if code == "ja" else {}), \
         patch.object(store, "setting", side_effect=lambda key, default="": default):
        assert interface_languages.load("ja")
        assert "ja" in interface_languages.available()
    assert t("ingredients", "ja") == "材料"


def test_shipped_locale_files_are_complete_and_keep_markup():
    import re
    from pathlib import Path
    from app.interface_languages import source_strings
    source = source_strings(); markup = re.compile(r"\{[^}]*\}|</?\w+[^>]*>")
    files = sorted((Path(__file__).resolve().parent.parent / "app/locales").glob("*.json"))
    assert files
    for path in files:
        values = json.loads(path.read_text())
        missing = [key for key in source if key not in values]
        # New labels added after generation fall back to English; existing ones must keep markup.
        assert len(missing) < 20, (path.name, missing[:5])
        for key, value in values.items():
            if key in source:
                assert sorted(markup.findall(source[key])) == sorted(markup.findall(value)), (path.name, key)


def test_ollama_service_is_started_and_model_preloaded():
    states = iter([False, False, True])
    with patch.object(local_runtime, "ollama_running", side_effect=lambda: next(states)), \
         patch.object(local_runtime, "ollama_unit_installed", return_value=True), \
         patch.object(local_runtime.subprocess, "run") as run, patch.object(local_runtime.httpx, "post") as post, \
         patch.object(local_runtime, "_ollama_loaded", return_value=[]), patch.object(local_runtime, "require_vram"), \
         patch.object(local_runtime.time, "sleep"):
        local_runtime.ensure_ollama("gemma")
    assert run.call_args.args[0] == ["systemctl", "--user", "start", "ollama.service"]
    assert post.call_args.kwargs["json"] == {"model": "gemma", "keep_alive": "10m"}
    assert local_runtime._ollama_started
    local_runtime._ollama_started = False


def test_ollama_without_service_or_server_is_reported_unavailable():
    import pytest
    with patch.object(local_runtime, "ollama_running", return_value=False), patch.object(local_runtime, "ollama_unit_installed", return_value=False):
        with pytest.raises(store.TranslationUnavailable):
            local_runtime.ensure_ollama("gemma")


def test_releasing_ollama_unloads_loaded_models_and_stops_service():
    ps = MagicMock(); ps.json.return_value = {"models": [{"name": "gemma:latest"}]}
    with patch.object(local_runtime, "ollama_running", return_value=True), patch.object(local_runtime, "ollama_unit_installed", return_value=True), \
         patch.object(local_runtime.httpx, "get", return_value=ps), patch.object(local_runtime.httpx, "post") as post, \
         patch.object(local_runtime.subprocess, "run") as run:
        local_runtime.release_ollama()
    assert post.call_args.kwargs["json"] == {"model": "gemma:latest", "keep_alive": 0}
    assert run.call_args.args[0] == ["systemctl", "--user", "stop", "ollama.service"]


def test_loading_a_local_model_first_releases_every_other_runtime():
    released = []
    with patch.object(local_runtime, "_holds_gpu", return_value=True), patch.object(local_runtime, "wait_for_vram_release") as wait, \
         patch.dict(local_runtime.RELEASE, {name: (lambda name=name: released.append(name)) for name in local_runtime.LOCAL}), \
         patch.object(store, "configuration", return_value={"provider": "ollama", "model": "gemma", "base_url": "", "api_key": ""}), \
         patch.object(local_runtime, "ensure_ollama") as ensure_ollama:
        local_runtime.ensure()
    assert released == ["llamacpp", "lmstudio"]
    wait.assert_called_once()
    ensure_ollama.assert_called_once_with("gemma")
    assert "ollama" in local_runtime._used
    local_runtime._used.clear()


def test_online_provider_releases_only_runtimes_this_app_loaded():
    released = []
    local_runtime._used.clear(); local_runtime._used.add("lmstudio")
    with patch.object(local_runtime, "_holds_gpu", return_value=True), patch.object(local_runtime, "wait_for_vram_release"), \
         patch.dict(local_runtime.RELEASE, {name: (lambda name=name: released.append(name)) for name in local_runtime.LOCAL}), \
         patch.object(store, "configuration", return_value={"provider": "claude", "model": "sonnet", "base_url": "", "api_key": ""}):
        local_runtime.ensure()
    assert released == ["lmstudio"] and not local_runtime._used


def test_hiding_releases_everything_the_app_used_and_the_selected_runtime():
    released = []
    local_runtime._used.clear(); local_runtime._used.add("lmstudio")
    with patch.object(local_runtime, "_holds_gpu", return_value=True), patch.object(local_runtime, "wait_for_vram_release"), \
         patch.dict(local_runtime.RELEASE, {name: (lambda name=name: released.append(name)) for name in local_runtime.LOCAL}), \
         patch.object(store, "configuration", return_value={"provider": "ollama", "model": "gemma", "base_url": "", "api_key": ""}):
        local_runtime.stop()
    assert released == ["llamacpp", "lmstudio", "ollama"]


def test_switching_provider_in_settings_frees_previous_runtime():
    released = []
    local_runtime._used.clear(); local_runtime._used.update({"ollama"})
    with patch.object(local_runtime, "_holds_gpu", return_value=True), patch.object(local_runtime, "wait_for_vram_release"), \
         patch.dict(local_runtime.RELEASE, {name: (lambda name=name: released.append(name)) for name in local_runtime.LOCAL}):
        local_runtime.release_unselected("lmstudio")
    assert released == ["ollama"]


def test_too_little_free_vram_is_refused_before_loading():
    import pytest
    with patch.object(local_runtime, "vram", return_value=(20 * 2**30, 24 * 2**30)):
        with pytest.raises(store.TranslationUnavailable, match="Not enough free GPU memory"):
            local_runtime.require_vram(9 * 2**30)
        local_runtime.require_vram(3 * 2**30)


def test_vram_release_waits_until_memory_stops_dropping():
    readings = iter([(18 * 2**30, 0), (12 * 2**30, 0), (2 * 2**30, 0)] + [(2 * 2**30, 0)] * 50)
    clock = iter(range(0, 1000))
    with patch.object(local_runtime, "vram", side_effect=lambda: next(readings)), patch.object(local_runtime.time, "sleep"), \
         patch.object(local_runtime.time, "monotonic", side_effect=lambda: next(clock) * 0.25):
        local_runtime.wait_for_vram_release()
    assert next(readings)[0] == 2 * 2**30


def test_ollama_models_are_listed_from_manifests_when_server_is_stopped(tmp_path, monkeypatch):
    library = tmp_path / "manifests/registry.ollama.ai/library"
    (library / "gemma-4-12b").mkdir(parents=True); (library / "gemma-4-12b/latest").write_text("{}")
    (library / "qwen").mkdir(); (library / "qwen/7b").write_text("{}")
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    with patch.object(ai_config.httpx, "get", side_effect=ai_config.httpx.ConnectError("down")):
        assert ai_config.get_ollama_models() == ["gemma-4-12b", "qwen:7b"]
