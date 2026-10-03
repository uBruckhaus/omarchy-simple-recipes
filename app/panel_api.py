"""Small native-panel API; expensive imports run outside shell and HTTP requests."""
from concurrent.futures import ThreadPoolExecutor
import re
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .ai_config import PROVIDERS, get_setting, set_setting
from .database import SessionLocal
from .i18n import LANGUAGES, TARGET_LANGUAGES, localize_category
from .models import Recipe
from .panel_locales import LABELS
from .translation import available_languages, verified_languages

_jobs = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recipe-import")


class ImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    use_ai: bool = False


class FavoriteRequest(BaseModel):
    favorite: bool


class PreferencesRequest(BaseModel):
    target_language: str | None = None
    ui_language: str | None = None


def configuration():
    from .main import selected_ai_configuration, get_app_languages
    with SessionLocal() as db:
        provider = get_setting(db, "ai_provider", "llamacpp")
        ui, target = get_app_languages(db, None)
    url, model, key = selected_ai_configuration(provider, "", "", "")
    return provider, url, model, key, ui, target


def status():
    from .lmstudio import available, lcpp_available
    from .codex_provider import available as codex_available
    provider, url, model, key, ui, target = configuration()
    if provider == "codex":
        connected = codex_available()
    elif provider == "llamacpp":
        connected = lcpp_available()["online"]
    elif provider == "lmstudio":
        connected = available()["online"]
    else:
        # Configuration readiness is not a live connection check.
        connected = None
    targets = verified_languages(url, model, key)
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Recipe.id)))
    return {"provider": provider, "provider_name": PROVIDERS[provider]["name"],
            "model": model, "connected": connected, "configured": bool(url and model and
            (key or not PROVIDERS[provider].get("needs_key"))),
            "target_language": target, "target_languages": targets,
            "ui_language": ui, "layout_languages": [{"code": c, "name": n} for c, n in LANGUAGES.items()],
            "labels": LABELS.get(ui, LABELS["en"]), "recipe_count": total}


def _run_import(job_id, values):
    from .main import import_url
    with _jobs_lock:
        _jobs[job_id]["state"] = "running"
    try:
        response = import_url(**values)
        location = response.headers.get("location", "")
        match = re.match(r"/recipe/(\d+)", location)
        if match:
            result = {"state": "done", "recipe_id": int(match[1]), "without_ai": False}
        elif "notice=" in location:
            from .extractor import canonicalize_url
            with SessionLocal() as db:
                row = db.scalar(select(Recipe).where(Recipe.source_url == (canonicalize_url(values["url"]) or values["url"])))
                if row is None:
                    raise ValueError("No imported recipe")
                result = {"state": "done", "recipe_id": row.id, "without_ai": True}
        else:
            result = {"state": "failed"}
    except Exception:
        # Neither scraped content nor provider diagnostics belong in job errors.
        result = {"state": "failed"}
    with _jobs_lock:
        _jobs[job_id].update(result, updated=time.monotonic())


def install(app):
    @app.get("/api/panel/ping")
    def ping():
        return {"ready": True}

    @app.get("/api/panel/status")
    def panel_status():
        return status()

    @app.get("/api/panel/recipes")
    def recipes(q: str = Query("", max_length=200), favorites: bool = False, limit: int = Query(8, ge=1, le=12)):
        with SessionLocal() as db:
            ui = get_setting(db, "ui_language", "en")
            statement = select(Recipe)
            if favorites:
                statement = statement.where(Recipe.favorite.is_(True))
            if q.strip():
                from sqlalchemy import or_
                statement = statement.where(or_(Recipe.title.contains(q.strip(), autoescape=True),
                    Recipe.ingredients.contains(q.strip(), autoescape=True), Recipe.category.contains(q.strip(), autoescape=True)))
            rows = db.scalars(statement.order_by(Recipe.created_at.desc(), Recipe.id.desc()).limit(limit))
            return {"recipes": [{"id": r.id, "title": r.title, "emoji": r.emoji,
                "category": localize_category(r.category, ui), "favorite": r.favorite,
                "duration_minutes": r.duration_minutes} for r in rows]}

    @app.post("/api/panel/recipes/{rid}/favorite")
    def favorite(rid: int, body: FavoriteRequest):
        with SessionLocal() as db:
            recipe = db.get(Recipe, rid)
            if recipe is None:
                raise HTTPException(404, "Recipe not found")
            recipe.favorite = body.favorite
            db.commit()
        return {"success": True}

    @app.post("/api/panel/languages")
    def languages():
        provider, url, model, key, _, _ = configuration()
        return dict(available_languages(url, model, key), provider=provider)

    @app.post("/api/panel/preferences")
    def preferences(body: PreferencesRequest):
        provider, url, model, key, _, _ = configuration()
        if body.ui_language is not None and body.ui_language not in LANGUAGES:
            raise HTTPException(400, "Unsupported interface language")
        if body.target_language is not None and body.target_language not in {row["code"] for row in verified_languages(url, model, key)}:
            raise HTTPException(409, "Verify the selected model's target language first")
        with SessionLocal() as db:
            if body.ui_language is not None:
                set_setting(db, "ui_language", body.ui_language)
            if body.target_language is not None:
                set_setting(db, "recipe_target_language", body.target_language)
        return {"success": True}

    @app.post("/api/panel/import", status_code=202)
    def start_import(body: ImportRequest):
        url = body.url.strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise HTTPException(400, "Enter a public recipe link") from None
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(400, "Enter a public recipe link")
        provider, base_url, model, key, _, target = configuration()
        if body.use_ai and target not in {row["code"] for row in verified_languages(base_url, model, key)}:
            raise HTTPException(409, "Verify the selected model's target language first")
        values = {"url": url, "use_ai": body.use_ai, "provider": provider, "llm_model": model,
                  "custom_model": model, "custom_url": base_url if provider == "custom" else "",
                  "provider_token": key, "target_lang": target}
        with _jobs_lock:
            now = time.monotonic()
            for job_id in list(_jobs):
                if _jobs[job_id]["state"] in ("done", "failed") and now - _jobs[job_id]["updated"] > 3600:
                    del _jobs[job_id]
            pending = [job for job in _jobs.values() if job["state"] in ("queued", "running")]
            if len(pending) >= 3:
                raise HTTPException(429, "Wait for an import to finish")
            if len(_jobs) >= 32:
                completed = next((jid for jid, job in _jobs.items() if job["state"] in ("done", "failed")), None)
                if completed:
                    del _jobs[completed]
            job_id = uuid4().hex
            _jobs[job_id] = {"id": job_id, "state": "queued", "updated": now}
        _executor.submit(_run_import, job_id, values)
        return {"id": job_id, "state": "queued"}

    @app.get("/api/panel/import/{job_id}")
    def import_status(job_id: str):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                raise HTTPException(404, "Import not found")
            return {key: value for key, value in job.items() if key != "updated"}
