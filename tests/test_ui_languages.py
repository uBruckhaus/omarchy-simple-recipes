from fastapi.testclient import TestClient
from unittest.mock import patch
import pytest
from app.main import app
from app.i18n import TRANSLATIONS, LANGUAGES, localize_category, localize_duration

@pytest.mark.parametrize('code,nav,settings', [('fr','Recettes','Paramètres'), ('it','Ricette','Impostazioni'), ('es','Recetas','Ajustes')])
def test_new_interfaces_render_and_are_selectable(code, nav, settings):
    client = TestClient(app)
    homepage = client.get('/?lang='+code)
    assert homepage.status_code == 200
    assert f'lang="{code}"' in homepage.text
    assert nav in homepage.text
    page = client.get('/einstellungen?lang='+code)
    assert page.status_code == 200
    assert settings in page.text
    for language in LANGUAGES:
        assert f'value="{language}"' in page.text
    assert 'window.recipeLayouts' in page.text
    assert set(TRANSLATIONS['en']) <= set(TRANSLATIONS[code])

@pytest.mark.parametrize('code', ['fr','it','es'])
def test_categories_and_durations_are_translated(code):
    assert localize_category('Sonstiges', code) not in ('Sonstiges', 'Other')
    assert localize_duration('unbekannt', code) not in ('unbekannt', 'Unknown')
