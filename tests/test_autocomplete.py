from fastapi.testclient import TestClient
from app.main import app, SessionLocal
from app.models import Recipe

def test_api_recipes_search():
    client = TestClient(app)

    # 1. Empty query returns empty list
    response = client.get("/api/recipes/search?q=")
    assert response.status_code == 200
    assert response.json() == []

    # 2. Query with spaces returns empty list
    response = client.get("/api/recipes/search?q=   ")
    assert response.status_code == 200
    assert response.json() == []

    # 3. Add a test recipe, query it, and delete it in finally block
    with SessionLocal() as db:
        test_recipe = Recipe(
            title="Test-Mandelkuchen-Zimtschnecke",
            ingredients='["1 Ei"]',
            instructions='["Mischen"]',
            tags='["Kuchen"]',
            category="Backen",
            source_type="Test",
            source_url="http://test.com"
        )
        db.add(test_recipe)
        db.commit()
        rid = test_recipe.id

    try:
        response = client.get("/api/recipes/search?q=Mandelkuchen")
        assert response.status_code == 200
        results = response.json()
        assert len(results) > 0
        assert any(r["id"] == rid and r["title"] == "Test-Mandelkuchen-Zimtschnecke" for r in results)
    finally:
        with SessionLocal() as db:
            recipe = db.get(Recipe, rid)
            if recipe:
                db.delete(recipe)
                db.commit()

def test_ajax_recipe_list():
    client = TestClient(app)

    # Request home route with ajax=1 query parameter
    response = client.get("/?ajax=1&lang=de")
    assert response.status_code == 200

    # It should return a partial HTML chunk (does not have full HTML head/body)
    html = response.text
    assert "<!doctype html>" not in html.lower()
    assert "<html" not in html.lower()

    # It should render either empty message or grid
    assert "rezept" in html.lower() or "keine" in html.lower()

def test_recipe_favorite_toggle():
    client = TestClient(app)

    # 1. Create a test recipe
    with SessionLocal() as db:
        test_recipe = Recipe(
            title="Test-Favoriten-Rezept",
            ingredients='["1 Ei"]',
            instructions='["Mischen"]',
            tags='["Kuchen"]',
            category="Backen",
            source_type="Test",
            source_url="http://testfav.com"
        )
        db.add(test_recipe)
        db.commit()
        rid = test_recipe.id

    try:
        # 2. Toggle favorite status (first time -> True)
        response = client.post(f"/recipe/{rid}/favorite", headers={"X-Requested-With": "XMLHttpRequest"})
        assert response.status_code == 200
        assert response.json()["favorite"] is True

        # Check DB status
        with SessionLocal() as db:
            assert db.get(Recipe, rid).favorite is True

        # 3. Toggle favorite status (second time -> False)
        response = client.post(f"/recipe/{rid}/favorite", headers={"X-Requested-With": "XMLHttpRequest"})
        assert response.status_code == 200
        assert response.json()["favorite"] is False

        # Check DB status
        with SessionLocal() as db:
            assert db.get(Recipe, rid).favorite is False
    finally:
        # 4. Clean up test recipe
        with SessionLocal() as db:
            recipe = db.get(Recipe, rid)
            if recipe:
                db.delete(recipe)
                db.commit()
