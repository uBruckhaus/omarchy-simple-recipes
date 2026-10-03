"""Probe actual translation output; model-list metadata is not a language guarantee."""
import os
import json
import hashlib
import re
import threading
import time
import unicodedata
import httpx

from .recipe_languages import RECIPE_LANGUAGES
from . import codex_provider

PROBES = {code: (info["prompt_name"], "Füge 2 Gramm Salz hinzu." if code == "en" else "Add 2 grams of salt.")
          for code, info in RECIPE_LANGUAGES.items()}
_cache = {}
_lock = threading.Lock()
TTL = 600

def _canonical(text, target_lang):
    text = unicodedata.normalize("NFKC", text.lower())
    if target_lang in {"en", "de", "fr", "es", "it", "pt", "pt-BR", "sv", "da", "nb", "nl", "pl", "tr"}:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.replace("ł", "l").replace("ı", "i").replace("æ", "ae").replace("ø", "o")
    elif target_lang == "ar":
        text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return text


def _valid_translation(text, target_lang):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
    if "<think>" in text.lower():
        return False
    words = _canonical(text, target_lang)
    # CJK scripts do not separate numbers and units with spaces; Unicode decimal
    # digits (e.g. Arabic ٢ and Hindi २) still represent the same amount.
    digits = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in words)
    if len(words) > 500 or re.findall(r"\d+(?:[.,]\d+)?", digits) != ["2"]:
        return False
    vocabulary = {
        "en": (r"\b(?:add|adding)\b", r"\b(?:grams?|g)\b", r"\bsalt\b"),
        "de": (r"\b(?:fug\w*|hinzufug\w*|gib|geb\w*|zugeb\w*)\b", r"\b(?:gramm|gramme|grammen|g)\b", r"\bsalz\b"),
        "fr": (r"\b(?:ajout\w*|incorpor\w*)\b", r"\b(?:grammes?|g)\b", r"\bsel\b"),
        "es": (r"\b(?:anad\w*|agreg\w*|incorpor\w*)\b", r"\b(?:gramos?|g)\b", r"\bsal\b"),
        "it": (r"\b(?:aggiung\w*|aggiunt\w*|unisc\w*|unire)\b", r"\b(?:grammi|grammo|g)\b", r"\bsale\b"),
        "pt": (r"\b(?:adicion\w*|acrescent\w*|junt\w*)\b", r"\b(?:gramas?|g)\b", r"\bsal\b"),
        "pt-BR": (r"\b(?:adicion\w*|acrescent\w*|junt\w*)\b", r"\b(?:gramas?|g)\b", r"\bsal\b"),
        "sv": (r"\b(?:tillsatt\w*|lagg\w*)\b", r"\b(?:gram|g)\b", r"\bsalt\b"),
        "da": (r"\b(?:tilsaet\w*|tilsat\w*|tilfoj\w*|kom)\b", r"\b(?:gram|g)\b", r"\bsalt\b"),
        "nb": (r"\b(?:tilsett\w*|tilfoy\w*|ha|legg\w*)\b", r"\b(?:gram|g)\b", r"\bsalt\b"),
        "nl": (r"\b(?:voeg|toevoegen|doe)\b", r"\b(?:gram|g)\b", r"\bzout\b"),
        "pl": (r"\b(?:dodaj\w*|dodac|wsyp\w*)\b", r"\b(?:gram\w*|g)\b", r"\b(?:sol|soli)\b"),
        "tr": (r"\b(?:ekle\w*|ilave)\b", r"\b(?:gram|g)\b", r"\btuz\w*\b"),
        "ru": (r"добав\w*", r"(?:грамм\w*|г\b)", r"(?:соль|соли)"),
        "uk": (r"(?:дод\w*|добав\w*)", r"(?:грам\w*|г\b)", r"(?:сіль|солі)"),
        "zh": (r"(?:加入|添加|放入|加上|加)", r"(?:克|公克|g)", r"盐"),
        "zh-TW": (r"(?:加入|添加|放入|加上|加)", r"(?:克|公克|g)", r"鹽"),
        "ja": (r"(?:加え|加える|入れ|入れる|追加)", r"(?:グラム|g)", r"塩"),
        "ko": (r"(?:넣|추가|더하)", r"(?:그램|g)", r"소금"),
        "ar": (r"(?:[أا]ضف|[أا]ضيف|[إا]ضاف)", r"(?:غرام|جرام|غ\b)", r"ملح"),
        "hi": (r"(?:डाल|मिला|जोड़|शामिल)", r"ग्राम", r"नमक"),
    }
    return all(re.search(pattern, words) for pattern in vocabulary[target_lang])


def check_translation(base_url, model, target_lang, api_key=""):
    if base_url == codex_provider.BASE_URL:
        api_key = ""
    if target_lang not in PROBES:
        return {"success": False, "status": "unsupported_language", "message": "Choose a supported target language."}
    if not base_url or not model:
        return {"success": False, "status": "unavailable", "message": "Choose a model and configure its server URL."}
    key = (base_url.rstrip("/"), model, target_lang, hashlib.sha256(api_key.encode()).hexdigest())
    with _lock:
        cached = _cache.get(key)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1], cached=True)
    router = os.getenv("LLAMA_CPP_URL", "http://127.0.0.1:8080/v1").rstrip("/").removesuffix("/v1")
    if base_url.rstrip("/").removesuffix("/v1") == router:
        try:
            status = httpx.get(f"{router}/models", timeout=5)
            status.raise_for_status()
            row = next((row for row in status.json().get("data", []) if row.get("id") == model), {})
            if row.get("status", {}).get("value") not in ("loaded", "sleeping"):
                return {"success": False, "status": "unavailable", "target_lang": target_lang,
                        "message": "Load the selected model before checking translation."}
        except Exception:
            return {"success": False, "status": "unavailable", "target_lang": target_lang,
                    "message": "The selected model server is unavailable."}
    language, source = PROBES[target_lang]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if "openrouter.ai" in base_url:
        headers.update({"HTTP-Referer": "https://simple-recipes.local", "X-Title": "Simple Recipes"})
    payload = {"model": model, "messages": [{"role": "user", "content":
        f"Translate this cooking instruction into {language}. Preserve the amount and unit; write the amount as the digit 2. Reply only with the translated sentence, without explanation: {source}"}],
        "max_tokens": 1024, "reasoning_effort": "none"}
    try:
        if base_url == codex_provider.BASE_URL:
            reply = codex_provider.text(payload["messages"][0]["content"], model)
        else:
            response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=45)
            if response.status_code in (400, 422):
                # Some compatible servers do not accept reasoning_effort.
                payload.pop("reasoning_effort", None)
                response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=45)
            response.raise_for_status()
            reply = response.json()["choices"][0]["message"]["content"]
        if not isinstance(reply, str):
            raise ValueError("Missing text")
        passed = _valid_translation(reply, target_lang)
        result = {"success": passed, "status": "verified" if passed else "unverified", "target_lang": target_lang,
            "message": f"{language}: translation sample passed." if passed else f"{language}: translation could not be verified. Choose another model or retry."}
    except Exception:
        # Provider errors can echo credentials. Return only a generic diagnostic.
        result = {"success": False, "status": "unavailable", "target_lang": target_lang,
            "message": f"{language}: model could not be checked. Check the server, model and credentials, then retry."}
    if result["success"]:
        with _lock:
            now = time.monotonic()
            for old in list(_cache):
                if _cache[old][0] <= now:
                    del _cache[old]
            if len(_cache) >= 256:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (now + TTL, result)
    return dict(result, cached=False)

def require_translation(base_url, model, target_lang, api_key=""):
    result = check_translation(base_url, model, target_lang, api_key)
    if not result["success"]:
        raise ValueError(result["message"])


def available_languages(base_url, model, api_key=""):
    from concurrent.futures import ThreadPoolExecutor
    from .i18n import LANGUAGES, TARGET_LANGUAGES
    if base_url == codex_provider.BASE_URL:
        results = _codex_languages(model)
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda language: check_translation(base_url, model, language, api_key), TARGET_LANGUAGES))
    return {
        "model": model,
        "target_languages": [{"code": code, "name": TARGET_LANGUAGES[code]} for code, result in zip(TARGET_LANGUAGES, results) if result["success"]],
        "layout_languages": [{"code": code, "name": name} for code, name in LANGUAGES.items()],
        "checks": {code: result for code, result in zip(TARGET_LANGUAGES, results)},
    }


_codex_probe_lock = threading.Lock()


def _codex_languages(model):
    # A single structured response tests every language; each sentence is still
    # validated independently using the same rules as other providers.
    with _codex_probe_lock:
        if not codex_provider.available():
            return [{"success": False, "status": "unavailable", "target_lang": code,
                     "message": "Sign in to Codex with ChatGPT using codex login in a terminal."} for code in PROBES]
        keys = [(codex_provider.BASE_URL, model, code, hashlib.sha256(b"").hexdigest()) for code in PROBES]
        with _lock:
            cached = [_cache.get(key) for key in keys]
            if all(row and row[0] > time.monotonic() for row in cached):
                return [dict(row[1], cached=True) for row in cached]
        schema = {"type": "object", "properties": {code: {"type": "string"} for code in PROBES},
                  "required": list(PROBES), "additionalProperties": False}
        prompt = "Translate each cooking instruction into its specified language/script. Preserve 2 grams of salt, writing the amount as digit 2. Return one sentence per language code, without explanation:\n" + json.dumps(
            {code: {"language": language, "source": source} for code, (language, source) in PROBES.items()}, ensure_ascii=False)
        try:
            replies = codex_provider.complete(prompt, model, schema)
        except ValueError:
            replies = {}
        results = []
        for key, (code, (language, _)) in zip(keys, PROBES.items()):
            reply = replies.get(code)
            passed = isinstance(reply, str) and _valid_translation(reply, code)
            result = {"success": passed, "status": "verified" if passed else "unverified", "target_lang": code,
                      "message": f"{language}: translation sample {'passed' if passed else 'could not be verified'}.", "cached": False}
            results.append(result)
            if passed:
                with _lock:
                    if len(_cache) >= 256:
                        _cache.pop(next(iter(_cache)))
                    _cache[key] = (time.monotonic() + TTL, result)
        return results


def clear_translation_cache():
    with _lock:
        _cache.clear()


def verified_languages(base_url, model, api_key=""):
    """Read successful, unexpired samples without making model requests."""
    if base_url == codex_provider.BASE_URL:
        api_key = ""
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    with _lock:
        return [{"code": code, "name": info["name"]} for code, info in RECIPE_LANGUAGES.items()
                if (row := _cache.get((base_url.rstrip("/"), model, code, digest)))
                and row[0] > time.monotonic() and row[1]["success"]]
