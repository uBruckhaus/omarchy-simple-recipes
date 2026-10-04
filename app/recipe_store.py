"""Desktop recipe operations. No HTTP framework or browser dependency."""
import json
import hashlib
import time
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, inspect, or_, select
from .database import Base, DATA_DIR, SessionLocal, engine
from .models import Category, Recipe, Setting
from .categories import category_for, ensure_categories, fallback_category_icon
from .ai_config import PROVIDERS, get_setting, set_setting
from .extractor import canonicalize_url, duration_class, extract, split_recipe_text
from .i18n import LANGUAGES, TARGET_LANGUAGES
from .lmstudio import MODEL_SWITCH_LOCK, load_model, normalize
from .translation import available_languages, clear_translation_cache, require_translation, verified_languages


class TranslationUnavailable(ValueError):
    pass


class IncompleteRecipeTranslation(ValueError):
    pass


def initialize():
    tables = inspect(engine).get_table_names()
    migrations = {"recipes": {"category": "VARCHAR(80) NOT NULL DEFAULT ''", "favorite": "BOOLEAN NOT NULL DEFAULT 0", "chunks": "INTEGER NOT NULL DEFAULT 1"},
                  "categories": {"icon": "VARCHAR(16) NOT NULL DEFAULT '🏷️'"},
                  "users": {"phone_number": "VARCHAR(16) NOT NULL DEFAULT ''"}}
    with engine.begin() as connection:
        for table, columns in migrations.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspect(engine).get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if "users" in tables and db.scalar(select(Setting).where(Setting.key == "phone_number")) is None:
            row = db.connection().exec_driver_sql("SELECT phone_number FROM users WHERE phone_number != '' ORDER BY id LIMIT 1").fetchone()
            if row:
                set_setting(db, "phone_number", row[0])
        ensure_categories(db)


def setting(key, default=""):
    with SessionLocal() as db:
        return get_setting(db, key, default)


def save_settings(values):
    with SessionLocal() as db:
        for key, value in values.items():
            row = db.scalar(select(Setting).where(Setting.key == key))
            if row:
                row.value = str(value)
            else:
                db.add(Setting(key=key, value=str(value)))
        db.commit()


def configuration():
    provider = setting("ai_provider", "llamacpp")
    if provider not in PROVIDERS:
        provider = "llamacpp"
    cfg = PROVIDERS[provider]
    model = setting(f"{provider}_model") or setting("ai_model") or cfg["default_model"]
    key = setting(f"{provider}_api_key") or setting("ai_api_key")
    url = setting("custom_base_url") if provider == "custom" else cfg["base_url"]
    return {"provider": provider, "model": model, "api_key": key, "base_url": url}


def select_model(provider, model, key="", custom_url=""):
    if provider not in PROVIDERS or not model.strip():
        raise ValueError("Choose a provider and model")
    model = model.strip()
    with MODEL_SWITCH_LOCK:
        from . import local_runtime
        # Single entry point: frees the other runtimes and waits for VRAM before a local
        # model loads; for online providers it releases what this app loaded.
        local_runtime.ensure(provider=provider, model=model)
        if provider in ("codex", "claude"):
            from .cli_providers import NAMES
            NAMES[provider].require_login()
        values = {"ai_provider": provider, f"{provider}_model": model, "ai_model": model, "ai_enabled": "1"}
        if key.strip() and PROVIDERS[provider].get("needs_key"):
            values[f"{provider}_api_key"] = key.strip()
            values["ai_api_key"] = key.strip()
        if provider == "custom":
            if not custom_url.strip():
                raise ValueError("Enter the server URL")
            values["custom_base_url"] = custom_url.strip().rstrip("/")
            if key.strip():
                values["custom_api_key"] = key.strip()
        save_settings(values)
    return model


def check_languages():
    cfg = configuration()
    result = available_languages(cfg["base_url"], cfg["model"], cfg["api_key"])
    if result["target_languages"]:
        save_settings({"verified_target_languages": json.dumps({"fingerprint": language_fingerprint(cfg), "checked_at": time.time(),
                      "codes": [row["code"] for row in result["target_languages"]]})})
    return result


def language_fingerprint(cfg):
    return hashlib.sha256(json.dumps([cfg["provider"], cfg["base_url"], cfg["model"], cfg["api_key"]]).encode()).hexdigest()


def saved_languages():
    try:
        value = json.loads(setting("verified_target_languages", "{}"))
        return value if isinstance(value, dict) and value.get("fingerprint") == language_fingerprint(configuration()) else {}
    except (ValueError, TypeError):
        return {}


def languages_need_check():
    # Opening an already configured app should not repeatedly spend model quota.
    # Import still checks its selected target; Settings can refresh all targets.
    return not any(code in TARGET_LANGUAGES for code in saved_languages().get("codes", []))


def targets():
    if not setting("ai_provider"):
        return []
    cfg = configuration()
    current = verified_languages(cfg["base_url"], cfg["model"], cfg["api_key"])
    return current or [{"code": code, "name": TARGET_LANGUAGES[code]} for code in saved_languages().get("codes", []) if code in TARGET_LANGUAGES]


def _decode(row):
    result = {column.name: getattr(row, column.name) for column in Recipe.__table__.columns}
    for name in ("ingredients", "instructions", "tags"):
        try:
            result[name] = json.loads(result[name])
        except (TypeError, ValueError):
            result[name] = []
        if not isinstance(result[name], list):
            result[name] = []
    return result


def recipes(query="", favorite=False, category="", sort="newest"):
    with SessionLocal() as db:
        statement = select(Recipe)
        if query.strip():
            statement = statement.where(or_(Recipe.title.contains(query.strip(), autoescape=True),
                Recipe.ingredients.contains(query.strip(), autoescape=True), Recipe.tags.contains(query.strip(), autoescape=True)))
        if favorite:
            statement = statement.where(Recipe.favorite.is_(True))
        if category:
            statement = statement.where(Recipe.category == category)
        ordering = {"newest": Recipe.created_at.desc(), "oldest": Recipe.created_at,
                    "title": Recipe.title, "duration": Recipe.duration_minutes.asc().nulls_last(),
                    "calories": Recipe.calories.asc().nulls_last(), "tried": Recipe.tried.desc()}
        return [_decode(row) for row in db.scalars(statement.order_by(ordering.get(sort, ordering["newest"]), Recipe.id.desc()))]


def recipe(rid):
    with SessionLocal() as db:
        row = db.get(Recipe, rid)
        return _decode(row) if row else None


def categories():
    with SessionLocal() as db:
        return list(db.scalars(select(Category.name).order_by(Category.name)))


def add_category(name):
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Enter a category name (up to 80 characters)")
    with SessionLocal() as db:
        if db.scalar(select(Category).where(Category.name == name)) is None:
            db.add(Category(name=name, icon=fallback_category_icon(name)))
            db.commit()


def rename_category(old, new):
    new = new.strip()
    if old == "Sonstiges" or not new or len(new) > 80:
        raise ValueError("Choose a valid category name")
    with SessionLocal() as db:
        row = db.scalar(select(Category).where(Category.name == old))
        if row is None or db.scalar(select(Category).where(Category.name == new)):
            raise ValueError("Category missing or name already exists")
        row.name = new
        for item in db.scalars(select(Recipe).where(Recipe.category == old)):
            item.category = new
        db.commit()


def remove_category(name):
    if name == "Sonstiges":
        raise ValueError("The fallback category cannot be deleted")
    with SessionLocal() as db:
        for item in db.scalars(select(Recipe).where(Recipe.category == name)):
            item.category = "Sonstiges"
        db.execute(delete(Category).where(Category.name == name))
        db.commit()


def update_recipe(rid, values):
    allowed = {"title", "emoji", "ingredients", "instructions", "tags", "category", "duration_minutes",
               "servings", "calories", "image_url", "favorite", "tried"}
    if "title" in values and (not values["title"].strip() or len(values["title"]) > 300):
        raise ValueError("Enter a recipe title (up to 300 characters)")
    with SessionLocal() as db:
        row = db.get(Recipe, rid)
        if row is None:
            raise ValueError("Recipe not found")
        for name, value in values.items():
            if name in allowed:
                if name in ("ingredients", "instructions", "tags"):
                    value = json.dumps(value, ensure_ascii=False)
                setattr(row, name, value)
        row.duration_class = duration_class(row.duration_minutes)
        db.commit()


def new_recipe():
    with SessionLocal() as db:
        row = Recipe(title="New recipe", source_url="manual:" + uuid4().hex, source_type="Manual", category="Sonstiges")
        db.add(row); db.commit(); db.refresh(row)
        return row.id


def delete_recipe(rid):
    with SessionLocal() as db:
        db.execute(delete(Recipe).where(Recipe.id == rid)); db.commit()


def _ai_source_text(raw, transcript):
    if not transcript:
        return raw
    return (raw + "\n\nVideo transcript (spoken recipe):\n" + transcript).strip()


def import_recipe(url, use_ai=False, target_language=None, progress=None):
    report = progress or (lambda step: None)
    url = url.strip()
    clean_url = canonicalize_url(url) or url
    with SessionLocal() as db:
        existing = db.scalar(select(Recipe).where(Recipe.source_url.in_([url, clean_url])))
        if existing:
            return {"id": existing.id, "duplicate": True, "without_ai": False}
    report("progress_reading")
    data = extract(url)
    data["source_url"] = clean_url
    raw = data.pop("raw_text", "")
    transcript = data.pop("transcript", "")
    if raw:
        ingredients, instructions = split_recipe_text(raw)
        if not data.get("ingredients"):
            data["ingredients"] = ingredients
        if not data.get("instructions"):
            data["instructions"] = instructions
    without_ai = False
    ai_error = ""
    if use_ai:
        cfg = configuration()
        target = target_language or setting("recipe_target_language", "en")
        try:
            report("progress_checking")
            try:
                require_translation(cfg["base_url"], cfg["model"], target, cfg["api_key"])
            except ValueError as exc:
                raise TranslationUnavailable(str(exc)) from exc
            report("progress_ai")
            translated = normalize(dict(data), _ai_source_text(raw, transcript), base_url=cfg["base_url"], model=cfg["model"],
                                  api_key=cfg["api_key"], target_lang=target,
                                  ui_lang=setting("ui_language", "en"),
                                  max_tokens=8000 if cfg["provider"] in ("llamacpp", "lmstudio", "ollama") else 4000)
            if not all(isinstance(translated.get(key), list) and translated[key] and all(isinstance(item, str) for item in translated[key]) for key in ("ingredients", "instructions")):
                raise IncompleteRecipeTranslation("AI returned an incomplete recipe")
            data.update(translated)
        except TranslationUnavailable:
            without_ai, ai_error = True, "translation_unavailable"
        except IncompleteRecipeTranslation:
            without_ai, ai_error = True, "ai_no_recipe"
        except Exception:
            without_ai, ai_error = True, "ai_request_failed"
    report("progress_saving")
    if not data.get("instructions") and raw:
        data["instructions"] = [line.strip() for line in raw.splitlines() if line.strip()]
    allowed = {column.name for column in Recipe.__table__.columns} - {"id", "created_at"}
    data = {key: value for key, value in data.items() if key in allowed}
    for key in ("ingredients", "instructions", "tags"):
        data[key] = json.dumps(data.get(key, []), ensure_ascii=False)
    data["duration_class"] = duration_class(data.get("duration_minutes"))
    data["category"] = category_for(SimpleNamespace(**data))
    with SessionLocal() as db:
        existing = db.scalar(select(Recipe).where(Recipe.source_url == clean_url))
        if existing:
            return {"id": existing.id, "duplicate": True, "without_ai": False}
        row = Recipe(**data)
        db.add(row); db.commit(); db.refresh(row)
        return {"id": row.id, "duplicate": False, "without_ai": without_ai, "ai_error": ai_error}


def reprocess(rid, target, progress=None):
    report = progress or (lambda step: None)
    original = recipe(rid)
    if original is None:
        raise ValueError("Recipe not found")
    cfg = configuration()
    report("progress_checking")
    try:
        require_translation(cfg["base_url"], cfg["model"], target, cfg["api_key"])
    except ValueError as exc:
        raise TranslationUnavailable("Translation model could not be verified") from exc
    source = {key: original[key] for key in ("title", "ingredients", "instructions", "tags", "duration_minutes", "servings", "calories")}
    raw = ""
    if (not source["ingredients"] or not source["instructions"]) and (original.get("source_url") or "").startswith(("https://", "http://")):
        report("progress_reading")
        extracted = extract(original["source_url"])
        raw = extracted.get("raw_text", "")
        ingredients, instructions = split_recipe_text(raw)
        raw = _ai_source_text(raw, extracted.get("transcript", ""))
        for name, fallback in (("ingredients", ingredients), ("instructions", instructions)):
            if not source[name]:
                source[name] = extracted.get(name) or fallback
    report("progress_ai")
    cleaned = normalize(source, raw,
                        base_url=cfg["base_url"], model=cfg["model"], api_key=cfg["api_key"], target_lang=target,
                        ui_lang=setting("ui_language", "en"), max_tokens=8000)
    for name in ("ingredients", "instructions"):
        if not isinstance(cleaned.get(name), list) or not cleaned[name] or not all(isinstance(item, str) and item.strip() for item in cleaned[name]):
            raise IncompleteRecipeTranslation("AI returned incomplete ingredients or instructions")
    # A failure above leaves the stored recipe untouched.
    update_recipe(rid, cleaned)
    return rid


def normalize_phone(value):
    value = value.strip()
    if not value:
        return ""
    if re.search(r"[^0-9+(). /-]", value):
        raise ValueError("Enter a valid telephone number")
    value = re.sub(r"[(). /-]", "", value)
    if value.startswith("00"):
        value = "+" + value[2:]
    elif value.startswith("0"):
        value = "+49" + value[1:]
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise ValueError("Enter a valid telephone number")
    return value


def reset_all(confirmation):
    if confirmation != "delete-all":
        raise ValueError("Reset requires confirmation")
    with SessionLocal() as db:
        for model in (Recipe, Category, Setting):
            db.execute(delete(model))
        if "users" in inspect(engine).get_table_names():
            db.connection().exec_driver_sql("UPDATE users SET phone_number = ''")
        db.commit()
    clear_translation_cache()


def backup_database(destination):
    destination = Path(destination)
    if destination.resolve() == (DATA_DIR / "rezepte.db").resolve():
        raise ValueError("Choose a different backup file")
    with sqlite3.connect(DATA_DIR / "rezepte.db") as source, sqlite3.connect(destination) as target:
        source.backup(target)
    destination.chmod(0o600)


def export_recipes(destination):
    records = recipes()
    for row in records:
        row["created_at"] = row["created_at"].isoformat()
    Path(destination).write_text(json.dumps({"format": "simple-recipes", "version": 1, "recipes": records}, ensure_ascii=False, indent=2))
    Path(destination).chmod(0o600)


def restore_recipes(source):
    payload = json.loads(Path(source).read_text())
    if not isinstance(payload, dict) or payload.get("format") != "simple-recipes" or payload.get("version") != 1 or not isinstance(payload.get("recipes"), list):
        raise ValueError("Choose a Simple Recipes JSON export")
    records = payload["recipes"]
    count = 0
    with SessionLocal() as db:
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("title"), str) or not record["title"].strip() or len(record["title"]) > 300:
                raise ValueError("Invalid recipe export")
            url = record.get("source_url") or "manual:" + uuid4().hex
            if not isinstance(url, str):
                raise ValueError("Invalid recipe export")
            if db.scalar(select(Recipe).where(Recipe.source_url == url)):
                continue
            values = {key: record[key] for key in ("title", "emoji", "image_url", "source_type", "category", "duration_minutes", "servings", "calories", "favorite", "tried") if key in record}
            for key in ("duration_minutes", "calories"):
                if values.get(key) is not None and (type(values[key]) is not int or values[key] < 0):
                    raise ValueError("Invalid recipe export")
            for key in ("emoji", "image_url", "source_type", "category", "servings"):
                if values.get(key) is not None and not isinstance(values[key], str):
                    raise ValueError("Invalid recipe export")
            for key in ("favorite", "tried"):
                if key in values and (type(values[key]) not in (bool, int) or values[key] not in (0, 1)):
                    raise ValueError("Invalid recipe export")
            for key in ("ingredients", "instructions", "tags"):
                items = record.get(key, [])
                if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                    raise ValueError("Invalid recipe export")
                values[key] = json.dumps(items, ensure_ascii=False)
            values["source_url"] = url
            values["duration_class"] = duration_class(values.get("duration_minutes"))
            db.add(Recipe(**values)); count += 1
        db.commit()
    return count


def search_videos(query, limit=10, language=""):
    import yt_dlp
    from .recipe_languages import RECIPE_LANGUAGES
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Choose between 1 and 50 results")
    if language and language not in RECIPE_LANGUAGES:
        raise ValueError("Choose a supported search language")
    options = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True, "socket_timeout": 15}
    search = query.strip()[:200]
    if language:
        # YouTube offers a preference, not a reliable audio-language filter.
        youtube_language = {"nb": "no", "zh": "zh-CN", "zh-TW": "zh-TW"}.get(language, language)
        options["extractor_args"] = {"youtube": {"lang": [youtube_language]}}
        search += " " + RECIPE_LANGUAGES[language]["prompt_name"]
    with yt_dlp.YoutubeDL(options) as downloader:
        data = downloader.extract_info(f"ytsearch{limit}:" + search, download=False)
    return [{"title": item.get("title", ""), "url": "https://www.youtube.com/watch?v=" + item["id"],
             "group": item.get("uploader") or item.get("channel") or "YouTube", "duration": item.get("duration"),
             "thumbnail": "https://i.ytimg.com/vi/" + item["id"] + "/mqdefault.jpg"}
            for item in data.get("entries", []) if item and item.get("id")][:limit]
