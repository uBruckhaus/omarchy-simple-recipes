from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
import pytest

from app import panel_api
from app.database import SessionLocal
from app.main import app
from app.models import Recipe


@pytest.fixture
def client():
    with patch.object(panel_api, "configuration", return_value=("custom", "http://localhost/v1", "chosen", "private-api-key", "fr", "en")):
        yield TestClient(app)


@pytest.fixture
def panel_recipes():
    with SessionLocal() as db:
        rows = [Recipe(title="Paneltest old soup", source_url="https://example.com/panel-old",
                      favorite=True, ingredients='["paneltest carrot"]', created_at=datetime.now()-timedelta(days=1)),
                Recipe(title="Paneltest recent pasta", source_url="https://example.com/panel-new", category="Pasta",
                      created_at=datetime.now())]
        db.add_all(rows); db.commit()
        ids = [row.id for row in rows]
    yield ids
    with SessionLocal() as db:
        for rid in ids:
            row = db.get(Recipe, rid)
            if row:
                db.delete(row)
        db.commit()


def test_panel_status_is_private_and_does_not_generate_ai_requests(client):
    with patch("app.translation.httpx.post") as post:
        result = client.get("/api/panel/status").json()
    assert result["model"] == "chosen" and result["provider"] == "custom"
    assert result["connected"] is None and result["configured"]
    assert result["labels"]["library"] == "Ouvrir la collection"
    assert result["target_languages"] == []
    assert "private-api-key" not in str(result)
    assert "base_url" not in result
    post.assert_not_called()


def test_search_recent_favorites_and_literal_wildcards(client, panel_recipes):
    rows = client.get("/api/panel/recipes", params={"q": "Paneltest"}).json()["recipes"]
    assert [row["id"] for row in rows] == list(reversed(panel_recipes))
    rows = client.get("/api/panel/recipes", params={"q": "paneltest", "favorites": True}).json()["recipes"]
    assert [row["id"] for row in rows] == [panel_recipes[0]]
    assert client.get("/api/panel/recipes", params={"q": "paneltest carrot"}).json()["recipes"][0]["id"] == panel_recipes[0]
    assert client.get("/api/panel/recipes", params={"q": "Paneltest%"}).json()["recipes"] == []
    assert client.get("/api/panel/recipes", params={"limit": 13}).status_code == 422


def test_favorite_updates_same_library(client, panel_recipes):
    rid = panel_recipes[1]
    assert client.post(f"/api/panel/recipes/{rid}/favorite", json={"favorite": True}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Recipe, rid).favorite
    assert client.post("/api/panel/recipes/999999/favorite", json={"favorite": True}).status_code == 404


def test_target_preference_requires_current_model_verification(client):
    assert client.post("/api/panel/preferences", json={"target_language": "zh"}).status_code == 409
    assert client.post("/api/panel/preferences", json={"ui_language": "unsupported"}).status_code == 400
    with patch.object(panel_api, "verified_languages", return_value=[{"code": "zh", "name": "中文"}]), patch.object(panel_api, "set_setting") as save:
        assert client.post("/api/panel/preferences", json={"target_language": "zh", "ui_language": "it"}).status_code == 200
    assert [(call.args[1], call.args[2]) for call in save.call_args_list] == [("ui_language", "it"), ("recipe_target_language", "zh")]


def test_language_check_uses_saved_selection_and_keeps_key_private(client):
    with patch.object(panel_api, "available_languages", return_value={"target_languages": []}) as check:
        result = client.post("/api/panel/languages", json={}).json()
    check.assert_called_once_with("http://localhost/v1", "chosen", "private-api-key")
    assert result["provider"] == "custom" and "private-api-key" not in str(result)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://", "https://[", "https://user:password@example.com/recipe"])
def test_bad_import_links_rejected(client, url):
    assert client.post("/api/panel/import", json={"url": url}).status_code == 400


def test_import_returns_immediately_and_job_routes_use_same_importer(client, panel_recipes):
    with patch.object(panel_api._executor, "submit") as submit:
        response = client.post("/api/panel/import", json={"url": "https://example.com/panel-import"})
    assert response.status_code == 202
    jid = response.json()["id"]
    assert client.get(f"/api/panel/import/{jid}").json()["state"] == "queued"
    values = submit.call_args.args[2]
    assert values["use_ai"] is False and values["llm_model"] == "chosen"
    with patch("app.main.import_url", return_value=RedirectResponse(f"/recipe/{panel_recipes[0]}", 303)) as importer:
        panel_api._run_import(jid, values)
    assert importer.call_args.kwargs["url"] == "https://example.com/panel-import"
    result = client.get(f"/api/panel/import/{jid}").json()
    assert result["state"] == "done" and result["recipe_id"] == panel_recipes[0]
    assert "private-api-key" not in str(result)
    panel_api._jobs.pop(jid)


def test_ai_import_requires_cached_verification(client):
    with patch.object(panel_api._executor, "submit") as submit:
        assert client.post("/api/panel/import", json={"url": "https://example.com/recipe", "use_ai": True}).status_code == 409
    submit.assert_not_called()


def test_failed_job_errors_do_not_expose_recipe_or_credentials(client):
    jid = "failure-test"
    panel_api._jobs[jid] = {"id": jid, "state": "queued", "updated": 0}
    with patch("app.main.import_url", side_effect=ValueError("private-api-key recipe text")):
        panel_api._run_import(jid, {})
    result = client.get(f"/api/panel/import/{jid}").json()
    assert result == {"id": jid, "state": "failed"}
    panel_api._jobs.pop(jid)
