from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, SessionLocal, normalize_phone_number
from app.models import Setting


def test_normalizes_german_and_international_phone_numbers():
    assert normalize_phone_number("0170 1234567") == "+491701234567"
    assert normalize_phone_number("0043 (660) 1234567") == "+436601234567"
    assert normalize_phone_number("+41 79 123 45 67") == "+41791234567"


def test_rejects_invalid_phone_numbers():
    assert normalize_phone_number("12345") is None
    assert normalize_phone_number("+49 Ruf-mich-an") is None
    assert normalize_phone_number("++49 170 1234567") is None


def test_settings_phone_roundtrip():
    client = TestClient(app)

    with SessionLocal() as db:
        original_row = db.scalar(select(Setting).where(Setting.key == "phone_number"))
        original = original_row.value if original_row else ""

    try:
        # Valid number is normalized and stored
        resp = client.post("/settings/phone", data={"phone_number": "0170 9999 9999"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "notice=" in resp.headers["location"]
        with SessionLocal() as db:
            row = db.scalar(select(Setting).where(Setting.key == "phone_number"))
            assert row.value == "+4917099999999"

        # Invalid number is rejected and not stored
        resp = client.post("/settings/phone", data={"phone_number": "12345"}, follow_redirects=False)
        assert resp.status_code == 303
        assert "error=" in resp.headers["location"]
        with SessionLocal() as db:
            row = db.scalar(select(Setting).where(Setting.key == "phone_number"))
            assert row.value == "+4917099999999"
    finally:
        with SessionLocal() as db:
            row = db.scalar(select(Setting).where(Setting.key == "phone_number"))
            if row:
                row.value = original
            elif original:
                db.add(Setting(key="phone_number", value=original))
            db.commit()


def test_settings_page_renders():
    client = TestClient(app)
    resp = client.get("/einstellungen?lang=de")
    assert resp.status_code == 200
    assert "Einstellungen · Simple Recipes" in resp.text
    assert 'action="/settings/ai"' in resp.text


def test_ai_settings_save_without_request_language():
    from unittest.mock import patch
    with patch("app.main.get_providers_dict", return_value={"custom": {}}):
        response = TestClient(app).post("/settings/ai", data={
            "ai_provider": "custom", "ai_model": "test-model",
        }, follow_redirects=False)
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]
