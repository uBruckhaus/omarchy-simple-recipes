from unittest.mock import patch, MagicMock
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, SessionLocal
from app.models import Recipe
from app.lmstudio import normalize

SOURCE_URL = "https://example.com/ki-import-test"

FAKE_EXTRACTED = {
    "title": "Roh-Suppe",
    "emoji": "🥣",
    "image_url": "",
    "source_url": SOURCE_URL,
    "source_type": "Webseite",
    "ingredients": ["1 L Brühe"],
    "instructions": ["Kochen"],
    "tags": ["Suppe"],
    "duration_minutes": 30,
    "servings": "2",
    "calories": 100,
}


def _cleanup():
    with SessionLocal() as db:
        recipe = db.scalar(select(Recipe).where(Recipe.source_url == SOURCE_URL))
        if recipe:
            db.delete(recipe)
            db.commit()


def test_import_without_ai_skips_normalize():
    _cleanup()
    client = TestClient(app)
    with patch("app.main.extract", return_value=dict(FAKE_EXTRACTED)), \
         patch("app.main.normalize") as mock_normalize:
        resp = client.post("/import", data={
            "url": "https://example.com/ki-import-test",
            "use_ai": "false",
            "provider": "llamacpp",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "notice=" not in resp.headers["location"]
    mock_normalize.assert_not_called()
    with SessionLocal() as db:
        recipe = db.scalar(select(Recipe).where(Recipe.source_url == SOURCE_URL))
        assert recipe is not None
        assert recipe.title == "Roh-Suppe"
        assert recipe.ingredients == '["1 L Brühe"]'
    _cleanup()


def test_import_with_ai_uses_llamacpp_url_and_model():
    _cleanup()
    cleaned = dict(FAKE_EXTRACTED, title="KI-Suppe")
    client = TestClient(app)
    with patch("app.main.extract", return_value=dict(FAKE_EXTRACTED)), \
         patch("app.main.normalize", return_value=cleaned) as mock_normalize:
        resp = client.post("/import", data={
            "url": "https://example.com/ki-import-test",
            "use_ai": "true",
            "provider": "llamacpp",
            "llm_model": "Qwen3.8-27B-Q4_K_M",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "notice=" not in resp.headers["location"]
    kwargs = mock_normalize.call_args.kwargs
    assert kwargs["base_url"] == "http://127.0.0.1:8080/v1"
    assert kwargs["model"] == "Qwen3.8-27B-Q4_K_M"
    assert kwargs["max_tokens"] == 8000
    with SessionLocal() as db:
        recipe = db.scalar(select(Recipe).where(Recipe.source_url == SOURCE_URL))
        assert recipe.title == "KI-Suppe"
    _cleanup()


def test_import_falls_back_to_raw_data_when_ai_fails():
    _cleanup()
    client = TestClient(app)
    with patch("app.main.extract", return_value=dict(FAKE_EXTRACTED)), \
         patch("app.main.normalize", side_effect=Exception("Connection refused")):
        resp = client.post("/import", data={
            "url": "https://example.com/ki-import-test",
            "use_ai": "true",
            "provider": "llamacpp",
            "llm_model": "Qwen3.8-27B-Q4_K_M",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "notice=" in resp.headers["location"]
    with SessionLocal() as db:
        recipe = db.scalar(select(Recipe).where(Recipe.source_url == SOURCE_URL))
        assert recipe is not None
        assert recipe.title == "Roh-Suppe"
    _cleanup()


def test_import_defaults_use_ai_true_when_field_missing():
    _cleanup()
    client = TestClient(app)
    with patch("app.main.extract", return_value=dict(FAKE_EXTRACTED)), \
         patch("app.main.normalize", side_effect=Exception("offline")) as mock_normalize:
        resp = client.post("/import", data={
            "url": "https://example.com/ki-import-test",
        }, follow_redirects=False)
    assert resp.status_code == 303
    # Fehlendes Feld (z. B. natives Formular ohne JS) => KI bleibt Standard
    mock_normalize.assert_called_once()
    _cleanup()


def test_load_model_endpoint_passes_provider_for_lmstudio():
    client = TestClient(app)
    with patch("app.main.load_model") as mock_load:
        resp = client.post("/lmstudio/load", data={
            "llm_model": "google/gemma-4-26b-a4b-qat",
            "provider": "lmstudio",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "notice=" in resp.headers["location"]
    assert mock_load.call_args.args == ("google/gemma-4-26b-a4b-qat", "lmstudio")


def test_load_model_llamacpp_reports_clear_error_without_network():
    client = TestClient(app)
    with patch("app.lmstudio.httpx.get", side_effect=httpx.ConnectError("offline")), \
         patch("app.lmstudio.httpx.post", side_effect=httpx.ConnectError("offline")), \
         patch("app.lmstudio.time.sleep"):
        resp = client.post("/lmstudio/load", data={
            "llm_model": "Qwen3.8-27B-Q4_K_M",
            "provider": "llamacpp",
        }, follow_redirects=False)
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]


def test_normalize_sends_reasoning_effort_none():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"title": "Suppe"}'}}]
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        res = normalize({"title": "Test"}, "zusatz")
        assert res == {"title": "Suppe"}
        payload = mock_post.call_args.kwargs["json"]
        assert payload.get("reasoning_effort") == "none"


def test_normalize_retries_without_reasoning_effort_on_400():
    req = httpx.Request("POST", "http://127.0.0.1:1234/v1/chat/completions")
    err_resp = httpx.Response(400, request=req)
    ok_resp = MagicMock()
    ok_resp.json.return_value = {
        "choices": [{"message": {"content": '{"title": "Fallback Suppe"}'}}]
    }
    with patch("httpx.post", side_effect=[
        httpx.HTTPStatusError("Bad Request", request=req, response=err_resp),
        ok_resp,
    ]) as mock_post:
        res = normalize({"title": "Test"}, "zusatz")
        assert res == {"title": "Fallback Suppe"}
        assert mock_post.call_count == 2
        first_payload = mock_post.call_args_list[0].kwargs["json"]
        second_payload = mock_post.call_args_list[1].kwargs["json"]
        assert first_payload.get("reasoning_effort") == "none"
        assert "reasoning_effort" not in second_payload


def test_import_duplicate_url_redirects_to_existing_recipe_without_ai():
    _cleanup()
    client = TestClient(app)
    # First import: successfully imports
    with patch("app.main.extract", return_value=dict(FAKE_EXTRACTED)), \
         patch("app.main.normalize", return_value=dict(FAKE_EXTRACTED)):
        resp1 = client.post("/import", data={
            "url": "https://example.com/ki-import-test",
            "use_ai": "false",
        }, follow_redirects=False)
        assert resp1.status_code == 303
        with SessionLocal() as db:
            recipe = db.scalar(select(Recipe).where(Recipe.source_url == SOURCE_URL))
            assert recipe is not None
            rid = recipe.id

    # Second import with tracking parameter: skips extract and normalize, redirects to existing recipe
    with patch("app.main.extract") as mock_extract, \
         patch("app.main.normalize") as mock_normalize:
        resp2 = client.post("/import", data={
            "url": "https://example.com/ki-import-test?utm_source=duplicate_tracker&ref=test",
            "use_ai": "true",
        }, follow_redirects=False)
        assert resp2.status_code == 303
        assert f"/recipe/{rid}" in resp2.headers["location"]
        assert "notice=" in resp2.headers["location"]
        assert "bereits" in resp2.headers["location"]
        mock_extract.assert_not_called()
        mock_normalize.assert_not_called()
    _cleanup()


