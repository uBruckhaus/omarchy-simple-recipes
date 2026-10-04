import json, os, time, re, threading
import httpx
from .recipe_languages import RECIPE_LANGUAGES
from . import cli_providers

BASE_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
MODEL = os.getenv("LM_STUDIO_MODEL", "google/gemma-4-26b-a4b-qat")
LCPP_BASE_URL = os.getenv("LLAMA_CPP_URL", "http://127.0.0.1:8080")

MODEL_SWITCH_LOCK = threading.RLock()

SCHEMA = {"type":"json_schema","json_schema":{"name":"rezept","strict":True,"schema":{"type":"object","properties":{
    "title":{"type":"string"},"emoji":{"type":"string"},"ingredients":{"type":"array","items":{"type":"string"}},
    "instructions":{"type":"array","items":{"type":"string"}},"tags":{"type":"array","items":{"type":"string"}},
    "duration_minutes":{"type":["integer","null"]},"servings":{"type":"string"},"calories":{"type":["integer","null"]}
},"required":["title","emoji","ingredients","instructions","tags","duration_minutes","servings","calories"],"additionalProperties":False}}}

def available():
    try:
        native_url = BASE_URL.removesuffix("/v1") + "/api/v1/models"
        data = httpx.get(native_url, timeout=2).json()
        llms = [m for m in data.get("models", []) if m.get("type") == "llm"]
        active = next((m["key"] for m in llms if m.get("loaded_instances")), None)
        return {"online": True, "models": [m["key"] for m in llms], "active": active or (llms[0]["key"] if llms else MODEL)}
    except Exception:
        try:
            data = httpx.get(f"{BASE_URL}/models", timeout=2).json()
            models = [m["id"] for m in data.get("data", []) if "embedding" not in m["id"].lower()]
            return {"online": True, "models": models, "active": models[0] if models else MODEL}
        except Exception:
            return {"online": False, "models": [], "active": MODEL}

def lcpp_available():
    """Status of the local llama.cpp `llama serve` (OpenAI-compatible API)."""
    base = LCPP_BASE_URL.rstrip("/")
    try:
        data = httpx.get(f"{base}/v1/models", timeout=2).json()
        models, active = [], ""
        for m in data.get("data", []):
            mid = m.get("id", "")
            if not mid or any(sub in mid.lower() for sub in ("tts", "tokenizer", "embedding")):
                continue
            models.append(mid)
            if isinstance(m.get("status"), dict) and m["status"].get("value") == "loaded":
                active = mid
        return {"online": True, "models": models, "active": active or (models[0] if models else "")}
    except Exception:
        return {"online": False, "models": [], "active": ""}

def normalize(
    recipe: dict,
    raw_text: str = "",
    base_url: str = BASE_URL,
    model: str = MODEL,
    api_key: str = "",
    max_tokens: int = 4000,
    target_lang: str = "en",
    ui_lang: str | None = None,
) -> dict:
    lang = (target_lang or "en").strip()
    if lang not in RECIPE_LANGUAGES:
        raise ValueError("Unsupported recipe target language")
    language = RECIPE_LANGUAGES[lang]["prompt_name"]
    units = (
        "Use US kitchen measurements (ounces, pounds, cups, tablespoons, teaspoons and Fahrenheit); convert metric quantities and temperatures consistently in both ingredients and instructions. "
        if ui_lang == "en" else
        "Use metric kitchen measurements (g, kg, ml, L and Celsius); convert imperial quantities and temperatures consistently in both ingredients and instructions. "
    )
    prompt = (
        f"Translate and format the following recipe entirely in {language}. "
        "Translate the title, ingredients, instructions, tags and servings into the target language, using its usual script. "
        "Keep JSON property names in English. Preserve ingredients, meaning and quantities faithfully. "
        "When an ingredient or instruction array is empty, extract the missing entries from the additional source text and existing recipe text before translating. Only include details supported by the source. "
        "Translate EVERY ingredient and EVERY instruction step, not only the title. Return ingredients and instructions as separate arrays of translated strings. "
        "Do not leave ingredient names or instruction sentences in the source language. Preserve every ingredient and preparation detail; do not summarize, omit steps or invent quantities. "
        + units +
        "Provide appropriate tags, exactly one emoji, total duration in minutes "
        "and calories per serving (null if unknown).\n\n"
    )

    content = prompt + json.dumps(recipe, ensure_ascii=False) + "\n\nAdditional text:\n" + raw_text[:24000]
    cli = cli_providers.backend(base_url)
    if cli:
        return cli.complete(content, model, SCHEMA["json_schema"]["schema"], timeout=300)
    
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://simple-recipes.local"
        headers["X-Title"] = "Simple Recipes"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "response_format": SCHEMA,
        "max_tokens": max_tokens,
        "reasoning_effort": "none",
    }
    
    def _parse_content(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())

    try:
        response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=300)
        response.raise_for_status()
        return _parse_content(response.json()["choices"][0]["message"]["content"])
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 422):
            fallback_payload = dict(payload)
            fallback_payload.pop("reasoning_effort", None)
            fallback_payload["response_format"] = {"type": "json_object"}
            try:
                response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=fallback_payload, headers=headers, timeout=300)
                response.raise_for_status()
                return _parse_content(response.json()["choices"][0]["message"]["content"])
            except Exception:
                fallback_payload.pop("response_format", None)
                response = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=fallback_payload, headers=headers, timeout=300)
                response.raise_for_status()
                return _parse_content(response.json()["choices"][0]["message"]["content"])
        else:
            raise

def load_model(model: str, provider: str = "lmstudio"):
    model = model.strip()
    if provider == "llamacpp":
        base = LCPP_BASE_URL.rstrip("/").removesuffix("/v1")
        with MODEL_SWITCH_LOCK:
            listing = httpx.get(f"{base}/models", timeout=10)
            listing.raise_for_status()
            models = listing.json().get("data", [])
            chosen = next((item for item in models if item.get("id") == model), None)
            if chosen is None:
                raise ValueError("Selected model is not available on this server")
            if chosen.get("status", {}).get("value") in ("loaded", "sleeping"):
                return {"success": True}
            response = httpx.post(f"{base}/models/load", json={"model": model}, timeout=120)
            if response.status_code != 200 and "model limit reached" in response.text.lower():
                # Explicitly switching a single-model router requires releasing
                # the previous resident model; merely retrying cannot succeed.
                for item in models:
                    if item.get("id") != model and item.get("status", {}).get("value") in ("loaded", "sleeping"):
                        unload = httpx.post(f"{base}/models/unload", json={"model": item["id"]}, timeout=30)
                        unload.raise_for_status()
                response = httpx.post(f"{base}/models/load", json={"model": model}, timeout=120)
            response.raise_for_status()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                status = httpx.get(f"{base}/models", timeout=10)
                status.raise_for_status()
                item = next((item for item in status.json().get("data", []) if item.get("id") == model), {})
                state = item.get("status", {})
                if state.get("value") in ("loaded", "sleeping"):
                    return {"success": True}
                if state.get("failed"):
                    raise RuntimeError("Selected model failed to load")
                time.sleep(0.5)
            raise TimeoutError("Selected model did not become ready")

    native_url = BASE_URL.removesuffix("/v1")
    
    # 1. Unload all currently loaded model instances to free up VRAM/RAM first
    try:
        models_data = httpx.get(f"{native_url}/api/v1/models", timeout=5).json()
        for m in models_data.get("models", []):
            if m.get("key") == model and m.get("loaded_instances"):
                return {"success": True}
        for m in models_data.get("models", []):
            for instance in m.get("loaded_instances", []):
                instance_id = instance.get("id")
                if instance_id:
                    httpx.post(f"{native_url}/api/v1/models/unload", json={"instance_id": instance_id}, timeout=30)
    except Exception:
        pass

    # 2. Load the new model
    response = httpx.post(f"{native_url}/api/v1/models/load", json={"model": model}, timeout=600)
    response.raise_for_status()
    return response.json()

def suggest_category_icon(name: str, fallback: str = "🏷️") -> str:
    """Ask the active local model for one fitting category emoji."""
    status=available()
    if not status["online"]:
        return fallback
    payload={"model":status["active"],"messages":[{"role":"user","content":
        f"Wähle genau ein gut erkennbares Emoji für die Rezeptkategorie „{name}“. Antworte nur mit dem Emoji, ohne Text."}],
        "temperature":0.1,"max_tokens":12}
    try:
        response=httpx.post(f"{BASE_URL}/chat/completions",json=payload,timeout=30)
        response.raise_for_status()
        icon=response.json()["choices"][0]["message"]["content"].strip()
        if icon and len(icon) <= 16 and not any(char.isalnum() for char in icon):
            return icon
    except Exception:
        pass
    return fallback
