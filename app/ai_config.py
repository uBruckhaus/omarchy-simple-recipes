import os, time, re, json, shutil
from pathlib import Path
import httpx
from . import claude_provider, codex_provider
from sqlalchemy import select
from .models import Setting

def is_local_llama_installed() -> bool:
    """Check if local llama-server binary, service, or models exist on disk."""
    if shutil.which("llama-server"):
        return True
    user_bin = Path.home() / ".local/bin/llama-server"
    if user_bin.is_file() and os.access(user_bin, os.X_OK):
        return True
    service_file = Path.home() / ".config/systemd/user/llama-server.service"
    if service_file.is_file():
        return True
    models_dir = Path(os.getenv("LLAMA_MODELS_DIR", "/mnt/ai/Models/llama.cpp-router"))
    if models_dir.is_dir() and any(models_dir.glob("*.gguf")):
        return True
    return False

def lmstudio_cli() -> str:
    """LM Studio's `lms` command, which can start its headless server on demand."""
    found = shutil.which("lms")
    if found:
        return found
    candidate = Path.home() / ".lmstudio/bin/lms"
    return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else ""

def lmstudio_running() -> bool:
    try:
        url = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1").rstrip("/")
        return httpx.get(f"{url}/models", timeout=0.3).status_code == 200
    except Exception:
        return False

def is_lmstudio_available() -> bool:
    """Check if LM Studio is installed (the app starts its server) or already reachable."""
    return bool(lmstudio_cli()) or lmstudio_running()

def get_lmstudio_models() -> list[str]:
    """LLMs downloaded in LM Studio, from the running server or the `lms` catalog."""
    native_url = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1").rstrip("/").removesuffix("/v1")
    try:
        data = httpx.get(f"{native_url}/api/v1/models", timeout=1).json()
        models = [m["key"] for m in data.get("models", []) if m.get("type") == "llm" and m.get("key")]
        if models:
            return models
    except Exception:
        pass
    cli = lmstudio_cli()
    if cli:
        try:
            import subprocess
            result = subprocess.run([cli, "ls", "--json"], capture_output=True, text=True, timeout=10)
            return [m["modelKey"] for m in json.loads(result.stdout) if m.get("type") == "llm" and m.get("modelKey")]
        except Exception:
            pass
    return []

def get_ollama_models() -> list[str]:
    """Models from the running server, else from the manifests in OLLAMA_MODELS (server may be stopped)."""
    try:
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/").removesuffix("/v1")
        data = httpx.get(f"{url}/api/tags", timeout=1).json()
        return [m["name"].removesuffix(":latest") for m in data.get("models", []) if m.get("name") and "embed" not in m["name"].lower()]
    except Exception:
        pass
    models = []
    for root in {Path(os.getenv("OLLAMA_MODELS", "/mnt/ai/Models")), Path.home() / ".ollama/models"}:
        library = root / "manifests/registry.ollama.ai/library"
        try:
            for manifest in sorted(library.glob("*/*")):
                name = manifest.parent.name + ("" if manifest.name == "latest" else ":" + manifest.name)
                if "embed" not in name and name not in models:
                    models.append(name)
        except OSError:
            pass
    return models

_online_models = {}

def get_online_models(provider: str, api_key: str) -> list[str]:
    """Ask an OpenAI-compatible provider which models this key may use (cached per key)."""
    cfg = PROVIDERS.get(provider, {})
    if not api_key or cfg.get("type") != "online" or not cfg.get("base_url", "").startswith("https://"):
        return []
    cache_key = (provider, hash(api_key))
    if cache_key in _online_models:
        return _online_models[cache_key]
    models = []
    try:
        response = httpx.get(cfg["base_url"].rstrip("/") + "/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=4)
        response.raise_for_status()
        skip = ("embed", "whisper", "tts", "dall-e", "image", "audio", "moderation", "transcribe", "realtime", "guard")
        models = sorted({str(m.get("id", "")).removeprefix("models/") for m in response.json().get("data", [])
                         if m.get("id") and not any(word in str(m["id"]).lower() for word in skip)})
    except Exception:
        return []
    _online_models[cache_key] = models
    return models

def is_ollama_available() -> bool:
    """Check if Ollama is reachable or installed locally (the app starts ollama.service on demand)."""
    if shutil.which("ollama") or (Path.home() / ".local/bin/ollama").exists():
        return True
    try:
        url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/").removesuffix("/v1")
        resp = httpx.get(f"{url}/api/tags", timeout=0.15)
        if resp.status_code == 200:
            return True
    except Exception:
        pass
    return False

def get_provider_status(provider: str) -> tuple[bool, str]:
    """Check readiness of a provider.
    Returns (is_ready, status_key).
    status_key corresponds to i18n keys:
      'provider_ready'
      'provider_not_installed'
      'provider_not_configured'
      'provider_not_logged_in'
    """
    from . import recipe_store as store

    if provider == "llamacpp":
        if is_local_llama_installed():
            return True, "provider_ready"
        return False, "provider_not_installed"

    if provider == "codex":
        if codex_provider.available():
            return True, "provider_ready"
        return False, "provider_not_logged_in"

    if provider == "claude":
        if claude_provider.available():
            return True, "provider_ready"
        return False, "provider_not_logged_in"

    if provider == "lmstudio":
        if is_lmstudio_available():
            return True, "provider_ready"
        return False, "provider_not_installed"

    if provider == "ollama":
        if is_ollama_available():
            return True, "provider_ready"
        return False, "provider_not_installed"

    if provider in ("openai", "gemini", "groq", "xai", "openrouter", "deepseek", "mistral"):
        saved_key = store.setting(f"{provider}_api_key") or os.getenv(f"{provider.upper()}_API_KEY", "")
        if not saved_key and store.setting("ai_provider") == provider:
            saved_key = store.setting("ai_api_key")
        if saved_key:
            return True, "provider_ready"
        return False, "provider_not_configured"

    if provider == "custom":
        url = store.setting("custom_base_url")
        if url:
            return True, "provider_ready"
        return False, "provider_not_configured"

    return False, "provider_not_configured"

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
    "claude": {
        "name": "Claude — existing Claude login",
        "type": "online",
        "base_url": claude_provider.BASE_URL,
        "default_model": claude_provider.DEFAULT_MODEL,
        "models": claude_provider.models(),
        "needs_key": False,
        "supports_translation": None,
        "help": "Uses your existing Claude Code sign-in (claude.ai subscription) and its usage limits. Recipe text is sent to Anthropic. No API key required. claude-default uses Claude Code's default model.",
    },
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
        "help": "Runs locally with LM Studio. The app starts the LM Studio server (lms server start) and loads the selected model when needed, and unloads it when the window is hidden.",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "type": "local",
        "base_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/v1"),
        "default_model": "llama3.2",
        "models": ["llama3.2", "qwen2.5", "mistral", "gemma2"],
        "needs_key": False,
        "supports_translation": None,
        "help": "Local Ollama server on your GPU. The app starts ollama.service when needed and unloads the model and stops the service when the window is hidden. GGUFs in /mnt/ai/Models and models from ollama pull are listed automatically.",
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
    "xai": {
        "name": "xAI Grok",
        "type": "online",
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-4",
        "models": ["grok-4", "grok-3-mini"],
        "needs_key": True,
        "supports_translation": None,
        "key_placeholder": "xai-...",
        "help": "Grok models from xAI with an API key from console.x.ai. The model list is loaded from your account once the key is saved.",
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
    for provider, discover in (("lmstudio", get_lmstudio_models), ("ollama", get_ollama_models)):
        found = discover()
        if found:
            provs[provider]["models"] = found
            provs[provider]["default_model"] = found[0]
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
        "ai_api_key", "ai_model", "custom_base_url", "codex_model", "claude_model",
        "llamacpp_api_key", "llamacpp_model",
        "lmstudio_api_key", "lmstudio_model",
        "ollama_api_key", "ollama_model",
        "openai_api_key", "openai_model",
        "gemini_api_key", "gemini_model",
        "groq_api_key", "groq_model",
        "xai_api_key", "xai_model",
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
    if provider in ("codex", "claude"):
        cli = codex_provider if provider == "codex" else claude_provider
        try:
            reply = cli.text("Respond briefly with: OK", model or cli.DEFAULT_MODEL)
            return {"success": True, "message": f"{provider.capitalize()} connected: {reply[:40]}", "model": model}
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
