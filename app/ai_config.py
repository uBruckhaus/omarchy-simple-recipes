import os, time, re, json
import httpx
from . import codex_provider
from sqlalchemy import select
from .models import Setting

def get_local_llama_models() -> list[str]:
    """Scan local directory /mnt/ai/Models/llama.cpp-router and query running llama-server."""
    models = []
    router_dir = os.getenv("LLAMA_MODELS_DIR", "/mnt/ai/Models/llama.cpp-router")
    if os.path.isdir(router_dir):
        try:
            for item in sorted(os.listdir(router_dir)):
                if item.endswith(".gguf") and not any(sub in item.lower() for sub in ("tts", "tokenizer", "embedding")):
                    name = item.removesuffix(".gguf")
                    if name not in models:
                        models.append(name)
        except Exception:
            pass

    # Query running llama-server if reachable
    try:
        url = os.getenv("LLAMA_CPP_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        resp = httpx.get(f"{url}/models", timeout=1.5).json()
        for m in resp.get("data", []):
            mid = m.get("id", "")
            if mid and not any(sub in mid.lower() for sub in ("tts", "tokenizer", "embedding")):
                if mid not in models:
                    models.append(mid)
    except Exception:
        pass

    if not models:
        models = [
            "gemma-4-12B-it-QAT-Q4_0",
            "Qwen3.8-27B-Q4_K_M",
            "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M",
            "gemma-4-E2B-it-Q4_K_M",
        ]
    return models

PROVIDERS = {
    "codex": {
        "name": "Codex — existing ChatGPT login",
        "type": "online",
        "base_url": codex_provider.BASE_URL,
        "default_model": codex_provider.DEFAULT_MODEL,
        "models": [codex_provider.DEFAULT_MODEL],
        "needs_key": False,
        "supports_translation": None,
        "help": "Uses your existing Codex ChatGPT sign-in and account usage limits. Recipe text is sent to OpenAI. No API key required. codex-default uses Codex's built-in default model.",
    },
    "llamacpp": {
        "name": "llama.cpp (Local ROCm)",
        "type": "local",
        "base_url": os.getenv("LLAMA_CPP_URL", "http://127.0.0.1:8080/v1"),
        "default_model": "gemma-4-12B-it-QAT-Q4_0",
        "models": [
            "gemma-4-12B-it-QAT-Q4_0",
            "Qwen3.8-27B-Q4_K_M",
            "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M",
            "gemma-4-E2B-it-Q4_K_M",
        ],
        "needs_key": False,
        "supports_translation": None,
        "help": "Runs locally on your AMD Radeon GPU via ROCm with zero cloud latency.",
    },
    "lmstudio": {
        "name": "LM Studio (Local)",
        "type": "local",
        "base_url": os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1"),
        "default_model": "google/gemma-4-26b-a4b-qat",
        "models": ["google/gemma-4-26b-a4b-qat"],
        "needs_key": False,
        "supports_translation": None,
        "help": "Runs locally via the LM Studio desktop application.",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "type": "local",
        "base_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1"),
        "default_model": "llama3.2",
        "models": ["llama3.2", "qwen2.5", "mistral", "gemma2"],
        "needs_key": False,
        "supports_translation": None,
        "help": "Local Ollama server instance (default port 11434).",
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "type": "online",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o3-mini"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "sk-proj-...",
        "help": "API Key from platform.openai.com/api-keys.",
    },
    "gemini": {
        "name": "Google Gemini",
        "type": "online",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "AIzaSy...",
        "help": "Free API Key from Google AI Studio (aistudio.google.com).",
    },
    "groq": {
        "name": "Groq (High-Speed)",
        "type": "online",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "gsk_...",
        "help": "Ultra-fast inference provider with generous free tier (console.groq.com).",
    },
    "openrouter": {
        "name": "OpenRouter (All Models / Subscription)",
        "type": "online",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.5-haiku",
        "models": [
            "anthropic/claude-3.5-haiku",
            "anthropic/claude-3.7-sonnet",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
            "deepseek/deepseek-chat",
        ],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "sk-or-v1-...",
        "help": "Unified gateway to Claude, GPT-4, Gemini & DeepSeek via openrouter.ai.",
    },
    "deepseek": {
        "name": "DeepSeek",
        "type": "online",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "sk-...",
        "help": "High-accuracy low-cost models from platform.deepseek.com.",
    },
    "mistral": {
        "name": "Mistral AI",
        "type": "online",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "models": ["mistral-small-latest", "mistral-large-latest", "codestral-latest"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "...",
        "help": "European AI provider (console.mistral.ai).",
    },
    "custom": {
        "name": "Custom (OpenAI-compatible)",
        "type": "custom",
        "base_url": "",
        "default_model": "",
        "models": [],
        "needs_key": False,
        "supports_translation": None,
        "key_placeholder": "optional API key",
        "help": "Any local or remote OpenAI-compatible /v1/chat/completions endpoint.",
    },
}

def get_providers_dict() -> dict:
    """Return a fresh copy of PROVIDERS with dynamically discovered local models."""
    provs = json.loads(json.dumps(PROVIDERS))
    provs["codex"]["models"] = codex_provider.models()
    local_lcpp = get_local_llama_models()
    provs["llamacpp"]["models"] = local_lcpp
    if local_lcpp and "gemma-4-12B-it-QAT-Q4_0" in local_lcpp:
        provs["llamacpp"]["default_model"] = "gemma-4-12B-it-QAT-Q4_0"
    elif local_lcpp:
        provs["llamacpp"]["default_model"] = local_lcpp[0]
    return provs

def get_setting(db, key: str, default: str = "") -> str:
    row = db.scalar(select(Setting).where(Setting.key == key))
    return row.value if row and row.value is not None else default

def set_setting(db, key: str, value: str):
    row = db.scalar(select(Setting).where(Setting.key == key))
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()

def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return key[:4] + "••••••••" + key[-4:]

def reset_all_settings(db) -> dict:
    """Reset all AI provider keys, models, and custom URLs to pristine defaults.
    Reactivates local providers and dynamically detected models."""
    keys_to_clear = [
        "ai_api_key", "ai_model", "custom_base_url", "codex_model",
        "llamacpp_api_key", "llamacpp_model",
        "lmstudio_api_key", "lmstudio_model",
        "ollama_api_key", "ollama_model",
        "openai_api_key", "openai_model",
        "gemini_api_key", "gemini_model",
        "groq_api_key", "groq_model",
        "openrouter_api_key", "openrouter_model",
        "deepseek_api_key", "deepseek_model",
        "mistral_api_key", "mistral_model",
        "custom_api_key", "custom_model",
    ]
    for k in keys_to_clear:
        set_setting(db, k, "")

    local_models = get_local_llama_models()
    default_model = "gemma-4-12B-it-QAT-Q4_0" if "gemma-4-12B-it-QAT-Q4_0" in local_models else (local_models[0] if local_models else "")

    set_setting(db, "ai_provider", "llamacpp")
    set_setting(db, "llamacpp_model", default_model)
    set_setting(db, "ai_model", default_model)

    return {
        "provider": "llamacpp",
        "model": default_model,
        "local_models": local_models,
    }

def test_connection(provider: str, base_url: str, model: str, api_key: str = "") -> dict:
    if provider == "codex":
        try:
            reply = codex_provider.text("Respond briefly with: OK", model or codex_provider.DEFAULT_MODEL)
            return {"success": True, "message": f"Codex connected: {reply[:40]}", "model": model}
        except ValueError as exc:
            return {"success": False, "message": str(exc)}
    provs = get_providers_dict()
    cfg = provs.get(provider, provs["custom"])
    url = (base_url or cfg["base_url"]).rstrip("/")
    if not url:
        return {"success": False, "message": "Server URL must not be empty."}
    if not model:
        model = cfg.get("default_model", "")
    if not model:
        return {"success": False, "message": "Model name must not be empty."}

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if provider == "openrouter" or "openrouter.ai" in url:
        headers["HTTP-Referer"] = "https://simple-recipes.local"
        headers["X-Title"] = "Simple Recipes"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Respond briefly with: OK"}],
        "max_tokens": 15,
        "temperature": 0.1,
    }

    t0 = time.time()
    try:
        resp = httpx.post(f"{url}/chat/completions", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        elapsed = round(time.time() - t0, 2)
        return {
            "success": True,
            "message": f"Connection successful ({elapsed}s)! Response: „{reply[:40]}“",
            "model": model,
            "elapsed": elapsed,
        }
    except httpx.HTTPStatusError as exc:
        msg = f"HTTP {exc.response.status_code}"
        try:
            err_json = exc.response.json()
            if "error" in err_json:
                detail = err_json["error"].get("message") or str(err_json["error"])
                msg += f": {detail}"
        except Exception:
            msg += f": {exc.response.text[:120]}"
        return {"success": False, "message": msg}
    except Exception as exc:
        return {"success": False, "message": f"Connection error: {str(exc)[:150]}"}
