from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app, SessionLocal, engine
from app.models import Recipe, Setting, Category
from app.translation import _cache


def test_full_reset_clears_recipes_phone_credentials_preferences_and_legacy_phone():
    with SessionLocal() as db:
        db.add(Recipe(title="Reset test recipe", source_url="https://example.com/reset-test"))
        for key, value in [("phone_number", "+491701234567"), ("openai_api_key", "test-secret"), ("custom_model", "custom")]:
            row = db.scalar(select(Setting).where(Setting.key == key))
            if row: row.value = value
            else: db.add(Setting(key=key, value=value))
        db.commit()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone_number VARCHAR(16))")
        conn.exec_driver_sql("INSERT INTO users (phone_number) VALUES ('+491701234567')")
    _cache['reset-test'] = (999999999999, {"success": True})
    response = TestClient(app).post("/settings/reset", data={"reset_confirm": "delete-all"}, follow_redirects=False)
    assert response.status_code == 303
    with SessionLocal() as db:
        for entity in (Recipe, Setting, Category):
            assert db.scalar(select(func.count()).select_from(entity)) == 0
    with engine.connect() as conn:
        assert not conn.exec_driver_sql("SELECT phone_number FROM users WHERE phone_number != ''").fetchall()
    assert not _cache


def test_unconfirmed_reset_preserves_recipe_and_phone():
    with SessionLocal() as db:
        recipe = Recipe(title="Keep this", source_url="https://example.com/keep")
        db.add(recipe)
        db.add(Setting(key="phone_number", value="+491709999999"))
        db.commit()
        rid = recipe.id
    client = TestClient(app)
    assert client.post("/settings/reset").status_code == 422
    assert client.post("/settings/reset", data={"reset_confirm": "wrong"}).status_code == 400
    with SessionLocal() as db:
        assert db.get(Recipe, rid).title == "Keep this"
        assert db.scalar(select(Setting).where(Setting.key == "phone_number")).value == "+491709999999"
        db.delete(db.get(Recipe, rid))
        db.delete(db.scalar(select(Setting).where(Setting.key == "phone_number")))
        db.commit()


def test_reset_confirmation_mentions_every_deleted_kind_in_both_layouts():
    client = TestClient(app)
    english = client.get("/einstellungen?lang=en").text
    german = client.get("/einstellungen?lang=de").text
    assert "Delete all recipes, categories, the phone number, API keys and preferences?" in english
    import json, re
    from bs4 import BeautifulSoup
    handler = BeautifulSoup(german, 'html.parser').find('form', action='/settings/reset')['onsubmit']
    message = json.loads(re.search(r'confirm\((.*)\)', handler).group(1))
    assert "Alle Rezepte, Kategorien, die Telefonnummer, API-Keys und Einstellungen löschen?" in message
    assert 'name="reset_confirm" value="delete-all"' in english
