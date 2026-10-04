import pytest
from app.extractor import minutes, duration_class, find_recipe, media_source, text_steps, validate_public_url, clean_media_text, canonicalize_url

def test_duration():
    assert minutes("PT1H25M") == 85
    assert duration_class(25) == "kurz"
    assert duration_class(45) == "mittel"
    assert duration_class(120) == "lang"

def test_howto_section_dict_instructions():
    section = {"@type": "HowToSection", "name": "Kochen", "itemListElement": [
        {"@type": "HowToStep", "text": "Wasser kochen"},
        {"@type": "HowToStep", "text": "Pasta zugeben"},
    ]}
    assert text_steps(section) == ["Wasser kochen", "Pasta zugeben"]
    assert text_steps({"@type": "HowToStep", "text": "Einmaliger Schritt"}) == ["Einmaliger Schritt"]
    assert text_steps(None) == []

def test_graph_recipe():
    assert find_recipe({"@graph":[{"@type":"Thing"},{"@type":"Recipe","name":"Suppe"}]})["name"] == "Suppe"

def test_social_media_sources():
    assert media_source("https://www.instagram.com/reel/example/") == ("Instagram", "📸")
    assert media_source("https://m.facebook.com/watch/?v=123") == ("Facebook", "📘")
    assert media_source("https://fb.watch/example/") == ("Facebook", "📘")
    assert media_source("https://notinstagram.com/reel/example/") is None


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/secret",
    "http://localhost/admin",
    "http://[::1]/secret",
    "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/internal",
    "http://192.168.1.10/router",
    "http://172.16.5.4/lanservice",
    "http://0.0.0.0/backdoor",
])
def test_blocks_internal_addresses(url):
    with pytest.raises(ValueError, match="[Ii]nterne"):
        validate_public_url(url)


def test_allows_public_targets():
    # IP literals: no DNS needed, deterministic
    assert validate_public_url("http://8.8.8.8/recipe") is True
    assert validate_public_url("https://93.184.216.34/recipe") is True


def test_blocks_nonstandard_ports_and_schemes():
    with pytest.raises(ValueError, match="Standard-Web-Ports"):
        validate_public_url("http://8.8.8.8:8080/x")
    with pytest.raises(ValueError, match="http\\(s\\)"):
        validate_public_url("ftp://example.com/file")
    with pytest.raises(ValueError, match="http\\(s\\)"):
        validate_public_url("file:///etc/passwd")


def test_clean_media_text():
    raw = (
        "Rezept-Titel\n"
        "-------------------------------------\n"
        "Hier mein Kochbuch:\n"
        "https://amzn.to/example\n"
        "► https://bit.ly/example\n"
        "Folgt mir auf Instagram:\n"
        "https://www.instagram.com/chef\n"
        "-------------------------------------\n"
        "Zutaten:\n"
        "- 500 g Mehl\n"
        "- 250 ml Milch\n"
        "\n"
        "Zubereitung:\n"
        "1. Teig kneten.\n"
    )
    cleaned = clean_media_text(raw)
    assert "Rezept-Titel" in cleaned
    assert "Zutaten:" in cleaned
    assert "- 500 g Mehl" in cleaned
    assert "1. Teig kneten." in cleaned
    assert "amzn.to" not in cleaned
    assert "bit.ly" not in cleaned
    assert "instagram.com" not in cleaned
    assert "-------------------------------------" not in cleaned

    assert clean_media_text("") == ""
    assert clean_media_text(None) == ""


def test_canonicalize_url():
    # YouTube tracking parameters
    assert canonicalize_url("https://www.youtube.com/watch?v=tG--c6srwag&pp=ygUPbGFzZ25lIGhlbnNzbGVy") == "https://www.youtube.com/watch?v=tG--c6srwag"
    # youtu.be shortlinks
    assert canonicalize_url("https://youtu.be/tG--c6srwag?si=xyz123") == "https://www.youtube.com/watch?v=tG--c6srwag"
    # YouTube mobile
    assert canonicalize_url("https://m.youtube.com/watch?v=tG--c6srwag") == "https://www.youtube.com/watch?v=tG--c6srwag"
    # YouTube shorts
    assert canonicalize_url("https://www.youtube.com/shorts/tG--c6srwag") == "https://www.youtube.com/watch?v=tG--c6srwag"
    # General URL tracking parameters & trailing slashes
    assert canonicalize_url("https://www.chefkoch.de/rezepte/123/suppe.html?utm_source=feed&ref=banner") == "https://www.chefkoch.de/rezepte/123/suppe.html"
    assert canonicalize_url("https://example.com/rezept/") == "https://example.com/rezept"
    assert canonicalize_url("") == ""
    assert canonicalize_url(None) == ""




def test_string_instructions_are_steps_not_individual_characters():
    assert text_steps('Mix flour.\n<p>Bake for 20 minutes.</p>') == ['Mix flour.', 'Bake for 20 minutes.']


def test_video_description_separates_ingredients_and_steps_without_ai():
    from app.extractor import split_recipe_text
    ingredients, steps = split_recipe_text('My soup\nIngredients:\n- 2 g salt\n- 1 L water\nInstructions:\n1. Add salt.\n2. Boil.\nNotes:\nSubscribe!')
    assert ingredients == ['2 g salt', '1 L water']
    assert steps == ['1. Add salt.', '2. Boil.']


def test_caption_track_prefers_uploaded_then_original_auto_captions():
    from app.extractor import _caption_track
    info = {"language": "de", "subtitles": {}, "automatic_captions": {
        "en": [{"ext": "json3", "url": "https://yt/en"}], "de-orig": [{"ext": "vtt", "url": "https://yt/de-vtt"}, {"ext": "json3", "url": "https://yt/de"}]}}
    assert _caption_track(info) == ("json3", "https://yt/de")
    info["subtitles"] = {"live_chat": [{"ext": "json", "url": "x"}], "de": [{"ext": "vtt", "url": "https://yt/manual"}]}
    assert _caption_track(info) == ("vtt", "https://yt/manual")
    assert _caption_track({"automatic_captions": {"fr": [{"ext": "json3", "url": "u"}]}}) is None


def test_media_transcript_joins_caption_events():
    from unittest.mock import MagicMock, patch
    from app import extractor
    response = MagicMock()
    response.json.return_value = {"events": [{"segs": [{"utf8": "[Musik]"}]}, {"segs": [{"utf8": "drei Eier "}, {"utf8": "200 Gramm Mehl"}]}, {"segs": [{"utf8": "\n"}]}]}
    with patch.object(extractor, "_caption_track", return_value=("json3", "https://yt/cap")), patch.object(extractor, "fetch_public", return_value=response):
        assert extractor.media_transcript({}) == "drei Eier 200 Gramm Mehl"


def _addrinfo(*ips):
    import socket
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


def test_fetch_public_connects_to_the_validated_address_not_a_second_lookup():
    from unittest.mock import MagicMock, patch
    import httpx
    from app import extractor
    sent = []
    def send(request, **_):
        sent.append(request)
        return httpx.Response(200, text="<html>ok</html>", request=request)
    lookups = iter([_addrinfo("93.184.216.34"), _addrinfo("127.0.0.1")])  # a rebinding DNS answer would come second
    with patch.object(extractor.socket, "getaddrinfo", side_effect=lambda *a, **k: next(lookups)), \
         patch.object(httpx.Client, "send", side_effect=send):
        response = extractor.fetch_public("https://recipes.example/soup")
    assert response.text == "<html>ok</html>" and len(sent) == 1
    assert sent[0].url.host == "93.184.216.34"
    assert sent[0].headers["Host"] == "recipes.example"
    assert sent[0].extensions["sni_hostname"] == "recipes.example"


def test_fetch_public_rejects_private_and_mixed_dns_answers_before_connecting():
    import pytest
    from unittest.mock import patch
    import httpx
    from app import extractor
    for answer in (_addrinfo("10.0.0.5"), _addrinfo("93.184.216.34", "192.168.1.10"), _addrinfo("::ffff:127.0.0.1"), _addrinfo("100.64.0.1")):
        with patch.object(extractor.socket, "getaddrinfo", return_value=answer), patch.object(httpx.Client, "send") as send:
            with pytest.raises(ValueError):
                extractor.fetch_public("https://rebind.example/")
        send.assert_not_called()


def test_fetch_public_checks_every_redirect_hop():
    import pytest
    from unittest.mock import patch
    import httpx
    from app import extractor
    answers = {"public.example": _addrinfo("93.184.216.34"), "internal.example": _addrinfo("10.1.2.3")}
    def send(request, **_):
        return httpx.Response(302, headers={"location": "http://internal.example/admin"}, request=request)
    with patch.object(extractor.socket, "getaddrinfo", side_effect=lambda host, *a, **k: answers[host]), \
         patch.object(httpx.Client, "send", side_effect=send) as sent:
        with pytest.raises(ValueError, match="Interne"):
            extractor.fetch_public("https://public.example/recipe")
    assert sent.call_count == 1
