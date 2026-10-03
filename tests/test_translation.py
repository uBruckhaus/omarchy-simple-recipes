from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.translation import check_translation, require_translation, _cache

@pytest.fixture(autouse=True)
def empty_translation_cache():
    _cache.clear()
    yield
    _cache.clear()

def reply(text):
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": text}}]}
    return response

@pytest.mark.parametrize("language,text", [
    ("en", "Add 2 grams of salt."), ("de", "Füge 2 Gramm Salz hinzu."),
    ("fr", "Ajoutez 2 grammes de sel."), ("es", "Añade 2 gramos de sal."),
    ("it", "Aggiungi 2 grammi di sale."),
])
def test_each_target_language_is_verified_using_model_output(language, text):
    with patch("app.translation.httpx.post", return_value=reply(text)) as post:
        result = check_translation("http://localhost/v1", "chosen-model", language)
    assert result["success"]
    assert post.call_args.kwargs["json"]["model"] == "chosen-model"
    assert "2" in post.call_args.kwargs["json"]["messages"][0]["content"]

@pytest.mark.parametrize("text", ["Add 2 grams of salt.", "Füge 20 Gramm Salz hinzu.", "I cannot translate.", None])
def test_wrong_language_wrong_quantity_and_missing_output_are_not_verified(text):
    with patch("app.translation.httpx.post", return_value=reply(text)):
        assert not check_translation("http://localhost/v1", "model", "de")["success"]


def test_unavailable_model_does_not_leak_credentials_and_can_be_retried():
    with patch("app.translation.httpx.post", side_effect=httpx.ConnectError("secret-key")) as post:
        result = check_translation("http://localhost/v1", "model", "de", "secret-key")
        check_translation("http://localhost/v1", "model", "de", "secret-key")
    assert not result["success"]
    assert "secret-key" not in str(result)
    assert post.call_count == 2


def test_cache_is_specific_to_model_language_endpoint_and_credentials():
    with patch("app.translation.httpx.post", return_value=reply("Füge 2 Gramm Salz hinzu.")) as post:
        args = ("http://localhost/v1", "model-a", "de", "key-a")
        assert check_translation(*args)["success"]
        assert check_translation(*args)["cached"]
        check_translation("http://localhost/v1", "model-b", "de", "key-a")
        check_translation("http://localhost/v1", "model-a", "fr", "key-a")
        check_translation("http://another/v1", "model-a", "de", "key-a")
        check_translation("http://localhost/v1", "model-a", "de", "key-b")
    assert post.call_count == 5


def test_expired_success_is_rechecked():
    with patch("app.translation.httpx.post", return_value=reply("Füge 2 Gramm Salz hinzu.")) as post, \
         patch("app.translation.time.monotonic", side_effect=[0, 601, 601]):
        check_translation("http://localhost/v1", "model", "de")
        check_translation("http://localhost/v1", "model", "de")
    assert post.call_count == 2


def test_unknown_language_is_not_sent_to_provider():
    with patch("app.translation.httpx.post") as post:
        assert not check_translation("http://localhost/v1", "model", "xx")["success"]
    post.assert_not_called()


def test_api_uses_selected_model_language_and_key():
    with patch("app.main.check_translation", return_value={"success": True}) as check:
        response = TestClient(app).post("/api/ai/translation", data={
            "provider": "custom", "ai_model": "chosen", "target_lang": "it",
            "custom_url": "http://localhost/v1", "api_key": "private-key",
        })
    assert response.json()["success"]
    check.assert_called_once_with("http://localhost/v1", "chosen", "it", "private-key")
    assert "private-key" not in response.text


def test_api_rejects_unknown_provider():
    assert TestClient(app).post("/api/ai/translation", data={"provider": "unknown"}).status_code == 400


def test_translation_guard_refuses_unverified_model():
    with patch("app.translation.httpx.post", return_value=reply("Wrong language")):
        with pytest.raises(ValueError, match="could not be verified"):
            require_translation("http://localhost/v1", "model", "de")


def test_failed_translation_check_skips_ai_and_preserves_raw_import():
    from app.main import SessionLocal
    from app.models import Recipe
    from sqlalchemy import select
    source = "https://example.com/translation-guard"
    raw = {"title": "Original", "emoji": "", "image_url": "", "source_url": source,
           "source_type": "Webseite", "ingredients": ["2 g salt"], "instructions": ["Add salt"],
           "tags": [], "duration_minutes": 1, "servings": "1", "calories": None}
    with patch("app.main.extract", return_value=raw), \
         patch("app.main.require_translation", side_effect=ValueError("Translation not verified")) as check, \
         patch("app.main.normalize") as normalize:
        response = TestClient(app).post("/import", data={"url": source, "use_ai": "true", "provider": "llamacpp", "llm_model": "selected", "target_lang": "de"}, follow_redirects=False)
    assert response.status_code == 303
    assert "notice=" in response.headers["location"]
    assert check.call_args.args[1:3] == ("selected", "de")
    normalize.assert_not_called()
    with SessionLocal() as db:
        recipe = db.scalar(select(Recipe).where(Recipe.source_url == source))
        assert recipe.title == "Original"
        db.delete(recipe)
        db.commit()


def test_language_discovery_lists_only_verified_targets_and_real_layouts():
    from app.translation import available_languages
    def probe(url, model, language, key):
        return {"success": language in ("de", "it"), "target_lang": language}
    with patch("app.translation.check_translation", side_effect=probe) as check:
        result = available_languages("http://localhost/v1", "chosen-model", "private")
    assert [item["code"] for item in result["target_languages"]] == ["de", "it"]
    assert [item["code"] for item in result["layout_languages"]] == ["en", "de", "fr", "it", "es"]
    from app.i18n import TARGET_LANGUAGES
    assert check.call_count == len(TARGET_LANGUAGES)
    assert "private" not in str(result)


def test_offline_model_keeps_layout_languages_available():
    from app.translation import available_languages
    with patch("app.translation.check_translation", return_value={"success": False}):
        result = available_languages("http://localhost/v1", "offline-model")
    assert result["target_languages"] == []
    assert len(result["layout_languages"]) == 5


def test_language_api_applies_selected_online_and_local_models():
    with patch("app.main.available_languages", return_value={"target_languages": [], "layout_languages": []}) as check:
        for provider, endpoint in [("openai", "https://api.openai.com/v1"), ("llamacpp", "http://127.0.0.1:8080/v1")]:
            response = TestClient(app).post("/api/ai/languages", data={"provider": provider, "ai_model": "selected", "api_key": "private"})
            assert response.status_code == 200
            check.assert_called_with(endpoint, "selected", "private")


@pytest.mark.parametrize("language,text", [
    ("de", "Fügen Sie bitte 2 g Salz hinzu."),
    ("de", "Geben Sie 2 Gramm Salz dazu."),
    ("fr", "Veuillez ajouter 2 grammes de sel."),
    ("es", "Por favor, añada 2 gramos de sal."),
    ("it", "Aggiungere 2 grammi di sale, per favore."),
    ("en", "Please add 2 grams of salt."),
    ("de", "<think>I should translate to German.</think>\nFügen Sie 2 Gramm Salz hinzu."),
])
def test_equivalent_wording_is_not_hidden(language, text):
    with patch("app.translation.httpx.post", return_value=reply(text)):
        assert check_translation("http://localhost/v1", "model", language)["success"]


def test_probe_has_room_for_reasoning_and_compatible_fallback():
    rejected = reply("")
    rejected.status_code = 400
    accepted = reply("Fügen Sie 2 Gramm Salz hinzu.")
    with patch("app.translation.httpx.post", side_effect=[rejected, accepted]) as post:
        result = check_translation("http://localhost/v1", "model", "de")
    assert result["success"]
    assert post.call_count == 2
    assert post.call_args.kwargs["json"]["max_tokens"] >= 1024
    assert "reasoning_effort" not in post.call_args.kwargs["json"]


@pytest.mark.parametrize("text", ["Füge 2 Kilogramm Salz hinzu.", "Füge 2 Gramm Zucker hinzu.", "<think>Füge 2 Gramm Salz hinzu."])
def test_wrong_ingredient_unit_and_unfinished_reasoning_are_rejected(text):
    with patch("app.translation.httpx.post", return_value=reply(text)):
        assert not check_translation("http://localhost/v1", "model", "de")["success"]

@pytest.mark.parametrize("language,text", [
    ("pt", "Adicione 2 gramas de sal."), ("nl", "Voeg 2 gram zout toe."),
    ("pt-BR", "Acrescente 2 gramas de sal."), ("sv", "Tillsätt 2 gram salt."),
    ("da", "Tilsæt 2 gram salt."), ("nb", "Tilsett 2 gram salt."),
    ("pl", "Dodaj 2 gramy soli."), ("tr", "2 gram tuz ekleyin."),
    ("ru", "Добавьте 2 грамма соли."), ("uk", "Додайте 2 грами солі."),
    ("zh", "加入2克盐。"), ("zh-TW", "加入２公克鹽。"),
    ("ja", "塩を2グラム加えてください。"), ("ko", "소금 2그램을 넣으세요."),
    ("ar", "أضف ٢ غرام من الملح."), ("hi", "२ ग्राम नमक डालें।"),
])
def test_additional_targets_and_unicode_scripts(language, text):
    with patch("app.translation.httpx.post", return_value=reply(text)):
        assert check_translation("http://localhost/v1", "model", language)["success"]

@pytest.mark.parametrize("language,text", [
    ("zh", "加入20克盐。"), ("zh", "加入2公斤盐。"), ("zh", "加入2克糖。"),
    ("ja", "Add 2 grams of salt."), ("ar", "أضف ٢٠ غرام من الملح."),
    ("sv", "Tillsätt 2 gram socker."), ("da", "Tilsæt 20 gram salt."),
    ("nb", "Tilsett 2 kilo salt."), ("pt-BR", "Add 2 grams of salt."),
])
def test_unicode_targets_reject_wrong_language_amount_units_or_ingredient(language, text):
    with patch("app.translation.httpx.post", return_value=reply(text)):
        assert not check_translation("http://localhost/v1", "model", language)["success"]

@pytest.mark.parametrize("language,language_name", [("zh", "Simplified Chinese"), ("zh-TW", "Traditional Chinese"), ("ja", "Japanese"), ("ar", "Arabic")])
def test_recipe_normalization_uses_selected_language_and_preserves_unicode(language, language_name):
    from app.lmstudio import normalize
    response = reply('')
    response.json.return_value = {"choices": [{"message": {"content": '{"title":"盐汤"}'}}]}
    with patch("app.lmstudio.httpx.post", return_value=response) as post:
        result = normalize({"title": "Salt soup"}, target_lang=language)
    assert result["title"] == "盐汤"
    prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert f"entirely in {language_name}" in prompt
    assert "Keep JSON property names in English" in prompt


def test_target_catalog_and_probe_catalog_stay_in_sync():
    from app.translation import PROBES
    from app.i18n import TARGET_LANGUAGES
    assert set(PROBES) == set(TARGET_LANGUAGES)
    assert "zh" in TARGET_LANGUAGES and "zh-TW" in TARGET_LANGUAGES


@pytest.mark.parametrize('interface, expected', [('en', 'US kitchen measurements'), ('de', 'metric kitchen measurements'), ('fr', 'metric kitchen measurements')])
def test_units_depend_on_interface_and_translation_covers_both_sections(interface, expected):
    from app.lmstudio import normalize
    response = reply('')
    response.json.return_value = {'choices': [{'message': {'content': '{"title":"Soupe"}'}}]}
    with patch('app.lmstudio.httpx.post', return_value=response) as post:
        normalize({'title':'Soup','ingredients':['1 oz salt'],'instructions':['Add salt.']}, target_lang='fr', ui_lang=interface)
    prompt = post.call_args.kwargs['json']['messages'][0]['content']
    assert expected in prompt and 'EVERY ingredient and EVERY instruction step' in prompt
    assert 'entirely in French' in prompt
