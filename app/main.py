import json, re, os
from urllib.parse import quote
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect, select, update, or_, delete
from .database import Base, SessionLocal, engine
from .models import Category, Recipe, Setting
from .extractor import extract, duration_class, canonicalize_url
from .lmstudio import available, lcpp_available, load_model, normalize, suggest_category_icon, MODEL_SWITCH_LOCK
from .ai_config import PROVIDERS, get_providers_dict, get_setting, set_setting, mask_key, test_connection, reset_all_settings
from .translation import check_translation, require_translation, available_languages, clear_translation_cache
from .i18n import TRANSLATIONS, t, localize_category, localize_duration, LANGUAGES, TARGET_LANGUAGES, DEFAULT_LANGUAGE, DEFAULT_TARGET_LANGUAGE

table_names = inspect(engine).get_table_names()
with engine.begin() as connection:
    if "recipes" in table_names and "category" not in {c["name"] for c in inspect(engine).get_columns("recipes")}:
        connection.exec_driver_sql("ALTER TABLE recipes ADD COLUMN category VARCHAR(80) NOT NULL DEFAULT ''")
    if "users" in table_names and "phone_number" not in {c["name"] for c in inspect(engine).get_columns("users")}:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN phone_number VARCHAR(16) NOT NULL DEFAULT ''")
    if "categories" in table_names and "icon" not in {c["name"] for c in inspect(engine).get_columns("categories")}:
        connection.exec_driver_sql("ALTER TABLE categories ADD COLUMN icon VARCHAR(16) NOT NULL DEFAULT '🏷️'")
    if "recipes" in table_names and "favorite" not in {c["name"] for c in inspect(engine).get_columns("recipes")}:
        connection.exec_driver_sql("ALTER TABLE recipes ADD COLUMN favorite BOOLEAN NOT NULL DEFAULT 0")
Base.metadata.create_all(engine)
# Ensure 'chunks' column exists in recipes table (SQLite migration)
with engine.begin() as conn:
    cols = [c['name'] for c in inspect(engine).get_columns('recipes')]
    if 'chunks' not in cols:
        conn.exec_driver_sql('ALTER TABLE recipes ADD COLUMN chunks INTEGER NOT NULL DEFAULT 1')

# One-time migration: carry over the phone number from the (now removed) user
# account into the settings table, if we have not stored one yet.
with SessionLocal() as db:
    if db.scalar(select(Setting).where(Setting.key == "phone_number")) is None:
        try:
            with engine.connect() as conn:
                row = conn.exec_driver_sql(
                    "SELECT phone_number FROM users WHERE phone_number != '' ORDER BY id LIMIT 1"
                ).fetchone()
            if row and row[0]:
                db.add(Setting(key="phone_number", value=row[0]))
                db.commit()
        except Exception:
            pass  # no users table (fresh database)

app = FastAPI(title="Simple Recipes")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Register template translation helpers
templates.env.globals["t"] = t
templates.env.globals["ui_strings"] = lambda language: {**TRANSLATIONS["en"], **TRANSLATIONS.get(language, {})}
templates.env.globals["localize_category"] = localize_category
templates.env.globals["localize_duration"] = localize_duration
templates.env.globals["LANGUAGES"] = LANGUAGES
templates.env.globals["TARGET_LANGUAGES"] = TARGET_LANGUAGES

def get_app_languages(db, request: Request):
    """Retrieve UI layout language and recipe target language from request or settings."""
    q_lang = request.query_params.get("lang") if request is not None else None
    if q_lang and q_lang in LANGUAGES:
        set_setting(db, "ui_language", q_lang)
        ui_lang = q_lang
    else:
        ui_lang = get_setting(db, "ui_language", DEFAULT_LANGUAGE)
        if ui_lang not in LANGUAGES:
            ui_lang = DEFAULT_LANGUAGE

    q_target = request.query_params.get("target_lang") if request is not None else None
    if q_target and q_target in TARGET_LANGUAGES:
        set_setting(db, "recipe_target_language", q_target)
        target_lang = q_target
    else:
        target_lang = get_setting(db, "recipe_target_language", DEFAULT_TARGET_LANGUAGE)
        if target_lang not in TARGET_LANGUAGES:
            target_lang = DEFAULT_TARGET_LANGUAGE

    return ui_lang, target_lang

@app.get("/ca.crt")
def download_ca():
    ca_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "certs", "ca-cert.pem"))
    if os.path.exists(ca_path):
        return FileResponse(ca_path, media_type="application/x-x509-ca-cert", filename="simple-recipes-ca.crt")
    raise HTTPException(status_code=404, detail="CA certificate not found")


def normalize_phone_number(value):
    """Normalize common German/international input to E.164."""
    value=value.strip()
    if not value or re.search(r"[^0-9+(). /-]", value): return None
    compact=re.sub(r"[(). /-]", "", value)
    if compact.startswith("00"): compact="+"+compact[2:]
    elif compact.startswith("0"): compact="+49"+compact[1:]
    if not re.fullmatch(r"\+[1-9]\d{7,14}", compact): return None
    return compact

def stored_phone_number():
    with SessionLocal() as db:
        row = db.scalar(select(Setting).where(Setting.key == "phone_number"))
        return row.value if row else ""

@app.get("/einstellungen", response_class=HTMLResponse)
def settings_page(request:Request, error:str="", notice:str=""):
    with SessionLocal() as db:
        ui_lang, target_lang = get_app_languages(db, request)
        curr_provider = get_setting(db, "ai_provider", "llamacpp")
        curr_key = get_setting(db, f"{curr_provider}_api_key") or get_setting(db, "ai_api_key")
        curr_model = get_setting(db, f"{curr_provider}_model") or get_setting(db, "ai_model")
        curr_url = get_setting(db, "custom_base_url")

        provs = get_providers_dict()

        saved_keys = {}
        masked_keys = {}
        for p, cfg in provs.items():
            if cfg.get("needs_key"):
                k = get_setting(db, f"{p}_api_key") or (get_setting(db, "ai_api_key") if p == curr_provider else "")
                saved_keys[p] = bool(k)
                masked_keys[p] = mask_key(k)

        saved_models = {}
        for p in provs:
            m = get_setting(db, f"{p}_model")
            if m:
                saved_models[p] = m

        return templates.TemplateResponse(request, "settings.html", {
            "ui_lang": ui_lang,
            "target_lang": target_lang,
            "target_languages": TARGET_LANGUAGES,
            "languages": LANGUAGES,
            "phone_number": stored_phone_number(),
            "providers": provs,
            "providers_json": json.dumps(provs),
            "current_ai_provider": curr_provider,
            "current_api_key": curr_key,
            "current_ai_model": curr_model,
            "current_custom_url": curr_url,
            "saved_keys": saved_keys,
            "masked_keys": masked_keys,
            "saved_models": saved_models,
            "error": error,
            "notice": notice,
        })

@app.post("/settings/language")
def save_language_settings(
    ui_language: str = Form(...),
    recipe_target_language: str = Form(...),
):
    with SessionLocal() as db:
        if ui_language in LANGUAGES:
            set_setting(db, "ui_language", ui_language)
        if recipe_target_language in TARGET_LANGUAGES:
            set_setting(db, "recipe_target_language", recipe_target_language)
    msg = "Language settings saved" if ui_language == "en" else "Spracheinstellungen gespeichert"
    return RedirectResponse(f"/einstellungen?notice={quote(msg, safe='+')}", 303)

@app.post("/settings/reset")
@app.post("/settings/ai/reset")
def reset_app(request: Request, reset_confirm: str = Form(...)):
    if reset_confirm != "delete-all":
        raise HTTPException(status_code=400, detail="Reset requires explicit confirmation")
    with SessionLocal() as db:
        ui_lang, _ = get_app_languages(db, request)
        db.execute(delete(Recipe))
        db.execute(delete(Category))
        db.execute(delete(Setting))
        # Old installations migrated this value from users at startup.
        if "users" in inspect(engine).get_table_names():
            db.connection().exec_driver_sql("UPDATE users SET phone_number = ''")
        db.commit()
    clear_translation_cache()
    msg = "All recipes, phone number, API keys and preferences have been cleared." if ui_lang == "en" else "Alle Rezepte, Telefonnummer, API-Keys und Einstellungen wurden gelöscht."
    return RedirectResponse(f"/einstellungen?notice={quote(msg, safe='+')}", 303)


@app.post("/settings/ai")
def save_ai_settings(
    ai_provider: str = Form(...),
    api_key: str = Form(""),
    ai_model: str = Form(""),
    custom_url: str = Form(""),
):
    with SessionLocal() as db:
        p = ai_provider.strip()
        provs = get_providers_dict()
        if p in provs:
            set_setting(db, "ai_provider", p)
        if api_key.strip():
            set_setting(db, f"{p}_api_key", api_key.strip())
            set_setting(db, "ai_api_key", api_key.strip())
        if ai_model.strip():
            set_setting(db, f"{p}_model", ai_model.strip())
            set_setting(db, "ai_model", ai_model.strip())
        if custom_url.strip():
            set_setting(db, "custom_base_url", custom_url.strip())
        ui_lang, _ = get_app_languages(db, None)
    msg = "AI settings successfully saved" if ui_lang == "en" else "KI-Einstellungen erfolgreich gespeichert"
    return RedirectResponse(f"/einstellungen?notice={quote(msg, safe='+')}", 303)

@app.post("/api/ai/test")
def api_test_ai(
    provider: str = Form(...),
    api_key: str = Form(""),
    ai_model: str = Form(""),
    custom_url: str = Form(""),
):
    with SessionLocal() as db:
        p = provider.strip()
        key = api_key.strip() or get_setting(db, f"{p}_api_key") or get_setting(db, "ai_api_key")
        model = ai_model.strip() or get_setting(db, f"{p}_model") or get_setting(db, "ai_model")
        url = custom_url.strip() or get_setting(db, "custom_base_url")

    return test_connection(p, url, model, key)

def selected_ai_configuration(provider, model, api_key, custom_url):
    cfg = PROVIDERS.get(provider)
    if cfg is None:
        raise HTTPException(status_code=400, detail="Unknown provider")
    with SessionLocal() as db:
        model = model.strip() or get_setting(db, f"{provider}_model") or cfg.get("default_model", "")
        key = api_key.strip() or get_setting(db, f"{provider}_api_key")
        if not key and provider == get_setting(db, "ai_provider", "llamacpp"):
            key = get_setting(db, "ai_api_key")
        url = (custom_url.strip() or get_setting(db, "custom_base_url")) if provider == "custom" else cfg.get("base_url", "")
    return url, model, key


@app.post("/api/ai/translation")
def api_translation_check(
    provider: str = Form(...), ai_model: str = Form(""),
    target_lang: str = Form(""), api_key: str = Form(""), custom_url: str = Form(""),
):
    url, model, key = selected_ai_configuration(provider, ai_model, api_key, custom_url)
    with SessionLocal() as db:
        language = target_lang or get_setting(db, "recipe_target_language", DEFAULT_TARGET_LANGUAGE)
    return check_translation(url, model, language, key)


@app.post("/api/ai/languages")
def api_model_languages(
    provider: str = Form(...), ai_model: str = Form(""),
    api_key: str = Form(""), custom_url: str = Form(""),
):
    url, model, key = selected_ai_configuration(provider, ai_model, api_key, custom_url)
    return available_languages(url, model, key)


@app.post("/settings/phone")
def update_phone(phone_number:str=Form(...)):
    phone_number=normalize_phone_number(phone_number)
    if not phone_number:
        return RedirectResponse("/einstellungen?error=Bitte+eine+gültige+Telefonnummer+angeben",303)
    with SessionLocal() as db:
        row=db.scalar(select(Setting).where(Setting.key=="phone_number"))
        if row: row.value=phone_number
        else: db.add(Setting(key="phone_number", value=phone_number))
        db.commit()
    return RedirectResponse("/einstellungen?notice=Telefonnummer+gespeichert",303)

def unpack(r):
    r.ingredients_list=json.loads(r.ingredients); r.instructions_list=json.loads(r.instructions); r.tags_list=json.loads(r.tags); return r

CATEGORY_RULES = {
    "Pasta": ("pasta", "nudel", "spaghetti", "penne", "tagliatelle", "lasagne", "gnocchi", "ravioli", "macaroni", "fettuccine", "rigatoni", "tortellini", "orzo", "carbonara", "bolognese", "arrabbiata", "pesto"),
    "Pizza": ("pizza", "calzone", "flammkuchen"),
    "Suppe": ("suppe", "soup", "eintopf", "stew", "brühe", "broth", "chowder", "ramen", "goulash", "minestrone"),
    "Salat": ("salat", "salad", "bowl", "coleslaw", "dressing"),
    "Backen": ("brot", "brötchen", "kuchen", "muffin", "muffins", "backen", "bread", "cake", "cookie", "cookies", "biscuit", "biscuits", "pie", "tart", "waffle", "waffel", "teig", "dough", "pancake", "pancakes", "brownie", "brownies", "gebäck", "pastry"),
    "Dessert": ("dessert", "nachtisch", "creme", "eis", "tiramisu", "pudding", "süß", "sweet", "ice cream", "mousse", "parfait", "schokolade", "chocolate", "sorbet"),
    "Frühstück": ("frühstück", "breakfast", "porridge", "müsli", "omelett", "omelette", "egg", "eggs", "rührei", "spiegelei", "brunch"),
    "Fleisch": ("hähnchen", "huhn", "chicken", "rind", "beef", "schwein", "pork", "steak", "hackfleisch", "meat", "bacon", "speck", "turkey", "pute", "lamb", "lamm", "sausage", "wurst", "schnitzel", "gulasch", "braten", "filet", "ribs", "rippchen", "burger", "patty", "veal", "kalb"),
    "Fisch": ("fisch", "fish", "lachs", "salmon", "thunfisch", "tuna", "garnele", "shrimp", "prawn", "seafood", "meeresfrüchte", "cod", "kabeljau", "forelle", "trout", "dorade", "zander", "crab", "krabbe", "calamari"),
    "Vegetarisch": ("vegetarisch", "vegetarian", "vegan", "veggie", "tofu", "gemüse", "vegetable", "vegetables", "aubergine", "eggplant", "zucchini", "pilz", "pilze", "mushroom", "mushrooms", "linsen", "lentil", "kichererbse", "kichererbsen", "chickpea", "falafel", "parmigiana", "spinat", "spinach", "avocado", "curry"),
}
DEFAULT_CATEGORIES = list(CATEGORY_RULES) + ["Sonstiges"]
CATEGORY_ICONS = {
    "Pasta":"🍝", "Pizza":"🍕", "Suppe":"🥣", "Salat":"🥗", "Backen":"🥐",
    "Dessert":"🍰", "Frühstück":"🍳", "Fleisch":"🥩", "Fisch":"🐠",
    "Vegetarisch":"🌱", "Sonstiges":"🗂️",
}

def fallback_category_icon(name):
    lowered=name.lower()
    choices=(("🔥",("grill","bbq")),("🍹",("getränk","drink","cocktail")),
             ("🍪",("keks","cookie")),("🍞",("brot","bread")),
             ("🍗",("huhn","hähnchen","chicken")),("🍚",("reis","rice")),
             ("🫙",("mittag","abend","gericht")),("🍎",("gesund","obst","frucht")))
    return next((icon for icon, words in choices if any(word in lowered for word in words)),"🏷️")

def category_icons(db):
    return {category.name:category.icon or CATEGORY_ICONS.get(category.name,"🏷️")
            for category in db.scalars(select(Category).order_by(Category.name))}

def category_for(recipe, force: bool = False):
    if not force and getattr(recipe, "category", ""): return recipe.category
    title = (getattr(recipe, "title", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in title for word in words): return cat
    ingredients = (getattr(recipe, "ingredients", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in ingredients for word in words): return cat
    tags = (getattr(recipe, "tags", "") or "").lower()
    for cat, words in CATEGORY_RULES.items():
        if any(word in tags for word in words): return cat
    return "Sonstiges"

def ensure_categories(db):
    existing=set(db.scalars(select(Category.name)).all())
    # Seed the complete set only for a new database. Afterwards deleted default
    # categories must stay deleted; only the required fallback is recreated.
    required = DEFAULT_CATEGORIES if not existing else ["Sonstiges"]
    for name in required:
        if name not in existing: db.add(Category(name=name,icon=CATEGORY_ICONS.get(name,"🏷️")))
    for category in db.scalars(select(Category)):
        if category.icon in ("", "🏷️"):
            category.icon=CATEGORY_ICONS.get(category.name,fallback_category_icon(category.name))
    db.commit()

@app.get("/", response_class=HTMLResponse)
def index(request:Request, q:str="", sort:str="newest", category:str="", view:str="flat", favorites:str="", error:str="", notice:str=""):
    with SessionLocal() as db:
        ensure_categories(db)
        ordering = {
            "newest": Recipe.created_at.desc(),
            "oldest": Recipe.created_at.asc(),
            "title": Recipe.title.asc(),
            "duration": Recipe.duration_minutes.asc().nulls_last(),
            "calories": Recipe.calories.asc().nulls_last(),
            "tried": Recipe.tried.desc(),
        }
        sort = sort if sort in ordering else "newest"
        stmt=select(Recipe).order_by(ordering[sort])
        recipes=db.scalars(stmt).all()
        favorites_bool = (favorites == "1")
        if favorites_bool:
            recipes=[r for r in recipes if r.favorite]
        if q: recipes=[r for r in recipes if q.lower() in (r.title+r.tags).lower()]
        categorized = [(r, category_for(r)) for r in recipes]
        categories = db.scalars(select(Category.name).order_by(Category.name)).all()
        for recipe, inferred in categorized:
            if not recipe.category: recipe.category=inferred
        db.commit()
        if category: categorized=[item for item in categorized if item[1] == category]
        visible=[]
        for recipe, cat in categorized:
            recipe.category=cat; visible.append(unpack(recipe))
        
        grouped_recipes = []
        icons = category_icons(db)
        is_grouped = (view == "grouped" and not category)
        
        if is_grouped:
            from collections import defaultdict
            grouped_map = defaultdict(list)
            for r in visible:
                grouped_map[r.category].append(r)
                
            for cat_name in categories:
                if cat_name in grouped_map:
                    grouped_recipes.append((cat_name, icons.get(cat_name, "🏷️"), grouped_map[cat_name]))
            for cat_name, r_list in grouped_map.items():
                if cat_name not in categories:
                    grouped_recipes.append((cat_name, icons.get(cat_name, "🏷️"), r_list))
                
        ui_lang, target_lang = get_app_languages(db, request)
        lm = available()
        lcpp = lcpp_available()
        provs = get_providers_dict()
        saved_provider = get_setting(db, "ai_provider", "llamacpp")
        saved_key = get_setting(db, f"{saved_provider}_api_key") or get_setting(db, "ai_api_key")
        is_online = provs.get(saved_provider, {}).get("type") == "online"
        codex_ready = False
        if saved_provider == "codex":
            from .codex_provider import available as codex_available
            codex_ready = codex_available()
        ai_online = lm["online"] or lcpp["online"] or codex_ready or (is_online and bool(saved_key) and saved_provider != "codex")
        saved_model = get_setting(db, f"{saved_provider}_model") or get_setting(db, "ai_model")

        context = {
            "recipes": visible,
            "grouped_recipes": grouped_recipes if is_grouped else None,
            "categories": categories,
            "category_icons": icons,
            "category": category,
            "view": view,
            "q": q,
            "sort": sort,
            "favorites": favorites_bool,
            "error": error,
            "notice": notice,
            "lm": lm,
            "lcpp": lcpp,
            "ai_online": ai_online,
            "is_online": is_online,
            "saved_key": bool(saved_key),
            "codex_ready": codex_ready,
            "saved_provider": saved_provider,
            "saved_model": saved_model,
            "providers_config": provs,
            "ui_lang": ui_lang,
            "target_lang": target_lang,
            "target_languages": TARGET_LANGUAGES,
            "languages": LANGUAGES,
        }
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.query_params.get("ajax") == "1":
            return templates.TemplateResponse(request, "partials/recipes_list.html", context)
            
        return templates.TemplateResponse(request, "index.html", context)

@app.post("/categories")
def add_category(name:str=Form(...), next_url:str=Form("/"), recipe_id:int|None=Form(None)):
    name=name.strip()
    next_url=next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"
    separator="&" if "?" in next_url else "?"
    if not name or len(name)>80: return RedirectResponse(f"{next_url}{separator}error=Ungültiger+Kategoriename",303)
    icon=suggest_category_icon(name,fallback_category_icon(name))
    with SessionLocal() as db:
        if not db.scalar(select(Category).where(Category.name==name)):
            db.add(Category(name=name,icon=icon))
        recipe=db.get(Recipe,recipe_id) if recipe_id is not None else None
        if recipe:
            recipe.category=name
        db.commit()
    notice="Kategorie+angelegt+und+zugewiesen" if recipe else "Kategorie+angelegt"
    return RedirectResponse(f"{next_url}{separator}notice={notice}",303)

@app.post("/categories/rename")
def rename_category(old_name:str=Form(...), new_name:str=Form(...)):
    new_name=new_name.strip()
    if not new_name or len(new_name)>80: return RedirectResponse("/?error=Ungültiger+Kategoriename",303)
    with SessionLocal() as db:
        category=db.scalar(select(Category).where(Category.name==old_name))
        if not category: return RedirectResponse("/?error=Kategorie+nicht+gefunden",303)
        if db.scalar(select(Category).where(Category.name==new_name)):
            return RedirectResponse("/?error=Kategorie+existiert+bereits",303)
        category.name=new_name
        db.execute(update(Recipe).where(Recipe.category==old_name).values(category=new_name)); db.commit()
    return RedirectResponse("/?notice=Kategorie+umbenannt",303)

@app.post("/categories/delete")
def delete_category(name:str=Form(...)):
    name=name.strip()
    if name == "Sonstiges":
        return RedirectResponse("/?error=Die+Kategorie+Sonstiges+kann+nicht+gelöscht+werden",303)
    with SessionLocal() as db:
        category=db.scalar(select(Category).where(Category.name==name))
        if not category:
            return RedirectResponse("/?error=Kategorie+nicht+gefunden",303)
        if not db.scalar(select(Category).where(Category.name=="Sonstiges")):
            db.add(Category(name="Sonstiges",icon=CATEGORY_ICONS["Sonstiges"]))
            db.flush()
        db.execute(update(Recipe).where(Recipe.category==name).values(category="Sonstiges"))
        db.delete(category)
        db.commit()
    return RedirectResponse("/?notice=Kategorie+gelöscht;+Rezepte+nach+Sonstiges+verschoben",303)

def select_model(provider, model, custom_url=""):
    if provider not in PROVIDERS or not model.strip():
        raise ValueError("Choose a provider and model")
    model = model.strip()
    if provider == "codex":
        from .codex_provider import require_login
        require_login()
    with MODEL_SWITCH_LOCK:
        if provider in ("llamacpp", "lmstudio"):
            load_model(model, provider)
        with SessionLocal() as db:
            set_setting(db, "ai_provider", provider)
            set_setting(db, f"{provider}_model", model)
            set_setting(db, "ai_model", model)
            if provider == "custom" and custom_url:
                set_setting(db, "custom_base_url", custom_url.strip())
    return model


@app.post("/api/ai/select")
def api_select_model(provider: str = Form(...), ai_model: str = Form(...), custom_url: str = Form("")):
    try:
        model = select_model(provider, ai_model, custom_url)
        return {"success": True, "model": model}
    except Exception:
        with SessionLocal() as db:
            language = get_setting(db, "ui_language", DEFAULT_LANGUAGE)
        return JSONResponse({"success": False, "message": t("model_failed", language)}, status_code=409)


@app.post("/lmstudio/load")
def change_lmstudio_model(llm_model: str = Form(...), provider: str = Form("lmstudio")):
    with SessionLocal() as db:
        language = get_setting(db, "ui_language", DEFAULT_LANGUAGE)
    try:
        model = select_model(provider, llm_model)
        message = t("model_loaded", language).replace("{model}", model)
        return RedirectResponse(f"/?notice={quote(message, safe='+')}", 303)
    except Exception:
        return RedirectResponse(f"/?error={quote(t('model_failed', language), safe='+')}", 303)

LLM_PROVIDER_URLS = {k: v.get("base_url", "") for k, v in PROVIDERS.items()}

@app.post("/import")
def import_url(
    url: str = Form(...),
    use_ai: bool = Form(True),
    provider: str = Form(""),
    llm_model: str = Form(""),
    custom_model: str = Form(""),
    custom_url: str = Form(""),
    provider_token: str = Form(""),
    target_lang: str = Form(""),
):
    try:
        raw_url = url.strip()
        clean_url = canonicalize_url(raw_url) or raw_url

        # Prevent duplicate imports: check before costly extraction and AI processing
        with SessionLocal() as db:
            existing = db.scalar(
                select(Recipe).where(
                    or_(Recipe.source_url == clean_url, Recipe.source_url == raw_url)
                )
            )
            if not existing:
                for r in db.scalars(select(Recipe)).all():
                    if canonicalize_url(r.source_url) == clean_url:
                        existing = r
                        break
            if existing:
                return RedirectResponse(f"/recipe/{existing.id}?notice={quote(f'Rezept bereits vorhanden: {existing.title}', safe='+')}", 303)

        data = extract(raw_url)
        data["source_url"] = clean_url
        raw_text = data.pop("raw_text", "")
        ai_notice = ""
        if use_ai:
            with SessionLocal() as db:
                if not target_lang or target_lang not in TARGET_LANGUAGES:
                    target_lang = get_setting(db, "recipe_target_language", DEFAULT_TARGET_LANGUAGE)

                provs = get_providers_dict()
                p = provider.strip()
                if not p or p not in provs:
                    p = get_setting(db, "ai_provider", "llamacpp")
                cfg = provs.get(p, provs["custom"])

                if p == "custom":
                    base_url = custom_url.strip() or get_setting(db, "custom_base_url")
                else:
                    base_url = cfg.get("base_url", "")

                if p in ("ollama", "custom"):
                    selected_model = custom_model.strip() or get_setting(db, f"{p}_model") or cfg.get("default_model", "")
                else:
                    selected_model = llm_model.strip() or get_setting(db, f"{p}_model") or cfg.get("default_model", "")

                token = provider_token.strip() or get_setting(db, f"{p}_api_key") or get_setting(db, "ai_api_key")

            try:
                # Thinking models (e.g. Qwen via llama.cpp) spend part of the budget
                # on reasoning, so they get a larger token budget.
                require_translation(base_url, selected_model, target_lang, token)
                cleaned = normalize(
                    data,
                    raw_text,
                    base_url=base_url,
                    model=selected_model,
                    api_key=token,
                    max_tokens=8000 if p == "llamacpp" else 4000,
                    target_lang=target_lang,
                )
                data.update(cleaned)
            except Exception as exc:
                # AI is a convenience, not a requirement: keep the raw extraction.
                ai_notice = f"AI unavailable ({str(exc)[:80]}) – Recipe saved without AI processing"
        if not data.get("instructions") and raw_text:
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            if lines:
                data["instructions"] = lines
        data["duration_class"] = duration_class(data.get("duration_minutes"))
        for k in ("ingredients", "instructions", "tags"):
            data[k] = json.dumps(data.get(k, []), ensure_ascii=False)
        with SessionLocal() as db:
            old = db.scalar(select(Recipe).where(or_(Recipe.source_url == clean_url, Recipe.source_url == raw_url)))
            if old:
                for k, v in data.items():
                    setattr(old, k, v)
                recipe = old
            else:
                recipe = Recipe(**data)
                db.add(recipe)
            if not recipe.category:
                recipe.category = category_for(recipe)
            db.commit()
            db.refresh(recipe)
            rid = recipe.id
        if ai_notice:
            return RedirectResponse(f"/?notice={quote(ai_notice, safe='+')}", 303)
        return RedirectResponse(f"/recipe/{rid}", 303)
    except Exception as exc:
        return RedirectResponse(f"/?error={quote(str(exc)[:240], safe='+')}", 303)

@app.post("/recipe/{rid}/reprocess")
def reprocess_recipe(rid: int, request: Request):
    with SessionLocal() as db:
        recipe = db.get(Recipe, rid)
        if not recipe:
            return RedirectResponse("/?error=Recipe+not+found", 303)

        ui_lang, target_lang = get_app_languages(db, request)
        provs = get_providers_dict()
        saved_p = get_setting(db, "ai_provider", "llamacpp")
        cfg = provs.get(saved_p, provs["llamacpp"])
        p = saved_p
        token = get_setting(db, f"{p}_api_key") or get_setting(db, "ai_api_key")

        if p == "custom":
            base_url = get_setting(db, "custom_base_url")
        else:
            base_url = cfg.get("base_url", "")

        selected_model = get_setting(db, f"{p}_model") or get_setting(db, "ai_model")
        if not selected_model:
            if p == "llamacpp":
                selected_model = lcpp_available().get("active") or cfg.get("default_model", "gemma-4-12B-it-QAT-Q4_0")
            elif p == "lmstudio":
                selected_model = available().get("active") or cfg.get("default_model", "")
            else:
                selected_model = cfg.get("default_model", "")

        try:
            ingredients = json.loads(recipe.ingredients) if recipe.ingredients else []
            instructions = json.loads(recipe.instructions) if recipe.instructions else []
            tags = json.loads(recipe.tags) if recipe.tags else []
        except Exception:
            ingredients, instructions, tags = [], [], []

        recipe_data = {
            "title": recipe.title,
            "emoji": recipe.emoji or "🍽️",
            "ingredients": ingredients,
            "instructions": instructions,
            "tags": tags,
            "duration_minutes": recipe.duration_minutes,
            "servings": recipe.servings or "",
            "calories": recipe.calories,
        }
        raw_text = "\n".join(instructions)

        try:
            require_translation(base_url, selected_model, target_lang, token)
            cleaned = normalize(
                recipe_data,
                raw_text,
                base_url=base_url,
                model=selected_model,
                api_key=token,
                max_tokens=8000 if p == "llamacpp" else 4000,
                target_lang=target_lang,
            )
            recipe.title = cleaned.get("title", recipe.title)
            recipe.emoji = cleaned.get("emoji", recipe.emoji)
            recipe.duration_minutes = cleaned.get("duration_minutes", recipe.duration_minutes)
            recipe.duration_class = duration_class(recipe.duration_minutes)
            recipe.servings = str(cleaned.get("servings", recipe.servings or ""))
            recipe.calories = cleaned.get("calories", recipe.calories)
            if cleaned.get("ingredients"):
                recipe.ingredients = json.dumps(cleaned["ingredients"], ensure_ascii=False)
            if cleaned.get("instructions"):
                recipe.instructions = json.dumps(cleaned["instructions"], ensure_ascii=False)
            if cleaned.get("tags"):
                recipe.tags = json.dumps(cleaned["tags"], ensure_ascii=False)
            recipe.category = category_for(recipe, force=True)
            db.commit()
            msg = "Recipe successfully translated and updated with AI" if ui_lang == "en" else "Rezept erfolgreich mit KI übersetzt und aufbereitet"
            return RedirectResponse(f"/recipe/{rid}?notice={quote(msg, safe='+')}", 303)
        except Exception as exc:
            msg = f"AI processing failed: {str(exc)[:180]}" if ui_lang == "en" else f"KI-Aufbereitung fehlgeschlagen: {str(exc)[:180]}"
            return RedirectResponse(f"/recipe/{rid}?error={quote(msg, safe='+')}", 303)

@app.get("/recipe/{rid}",response_class=HTMLResponse)
def detail(request:Request,rid:int,notice:str=""):
    with SessionLocal() as db:
        ui_lang, target_lang = get_app_languages(db, request)
        recipe=db.get(Recipe,rid)
        ensure_categories(db)
        if recipe and not recipe.category:
            recipe.category=category_for(recipe); db.commit()
        categories=db.scalars(select(Category.name).order_by(Category.name)).all()
        phone_setting=db.scalar(select(Setting).where(Setting.key=="phone_number"))
        recipe=unpack(recipe)

        ing_header = "Ingredients" if ui_lang == "en" else "Zutaten"
        prep_header = "Instructions" if ui_lang == "en" else "Zubereitung"
        img_header = "Recipe Image" if ui_lang == "en" else "Bild zum Rezept"
        src_header = "Original Recipe" if ui_lang == "en" else "Original-Rezept"

        recipe_text=f"{recipe.title}\n\n{ing_header}:\n"+"\n".join(f"- {item}" for item in recipe.ingredients_list)
        instructions="\n".join(f"{number}. {item}" for number, item in enumerate(recipe.instructions_list, 1))
        image_text=f"\n\n{img_header}:\n{recipe.image_url}" if recipe.image_url else ""
        source_text=f"\n\n{src_header}:\n{recipe.source_url}" if recipe.source_url else ""
        whatsapp_text=f"{recipe_text}\n\n{prep_header}:\n{instructions}{image_text}{source_text}"
        whatsapp_ingredients=recipe_text
        return templates.TemplateResponse(request,"detail.html",{
            "r":recipe,
            "categories":categories,
            "category_icons":category_icons(db),
            "whatsapp_text":whatsapp_text,
            "whatsapp_ingredients":whatsapp_ingredients,
            "phone_number":phone_setting.value if phone_setting else "",
            "notice":notice,
            "ui_lang": ui_lang,
            "target_lang": target_lang,
            "target_languages": TARGET_LANGUAGES,
        })

@app.post("/recipe/{rid}/category")
def assign_category(rid:int, category:str=Form(...)):
    with SessionLocal() as db:
        recipe=db.get(Recipe,rid)
        valid=db.scalar(select(Category).where(Category.name==category))
        if recipe and valid: recipe.category=category; db.commit()
    return RedirectResponse(f"/recipe/{rid}",303)

@app.post("/recipe/{rid}/tried")
def tried(rid:int):
    with SessionLocal() as db:
        r=db.get(Recipe,rid); r.tried=not r.tried; db.commit()
    return RedirectResponse(f"/recipe/{rid}",303)

@app.post("/recipe/{rid}/favorite")
def toggle_favorite(rid:int, request:Request):
    with SessionLocal() as db:
        r=db.get(Recipe,rid)
        if r:
            r.favorite=not r.favorite
            db.commit()
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return {"favorite": r.favorite}
            return RedirectResponse(f"/recipe/{rid}",303)
    raise HTTPException(status_code=404, detail="Rezept nicht gefunden")

@app.post("/recipe/{rid}/delete")
def delete_recipe(rid:int):
    with SessionLocal() as db:
        recipe=db.get(Recipe,rid)
        if recipe:
            db.delete(recipe); db.commit()
    return RedirectResponse("/",303)

@app.get("/api/recipes/search")
def api_search_recipes(q: str = ""):
    if not q.strip():
        return []
    with SessionLocal() as db:
        stmt = select(Recipe).where(Recipe.title.ilike(f"%{q.strip()}%")).limit(10)
        recipes = db.scalars(stmt).all()
        return [{"id": r.id, "title": r.title, "emoji": r.emoji or "🍽️", "category": r.category or "Sonstiges"} for r in recipes]

@app.get("/api/youtube/search")
def api_search_youtube(q: str = ""):
    q = q.strip()
    if not q:
        return []
    import yt_dlp
    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "playlist_items": "1-5",
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch5:{q}", download=False)
        entries = result.get("entries", []) if result else []
        results = []
        for entry in entries[:5]:
            duration_sec = entry.get("duration")
            if duration_sec is not None:
                m, s = divmod(int(duration_sec), 60)
                h, m = divmod(m, 60)
                duration_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            else:
                duration_str = ""
            
            thumbnails = entry.get("thumbnails", [])
            thumbnail_url = ""
            if thumbnails:
                thumbnail_url = thumbnails[-1].get("url") or thumbnails[0].get("url", "")
            
            results.append({
                "id": entry.get("id"),
                "title": entry.get("title", "Unbekanntes Video"),
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                "thumbnail": thumbnail_url,
                "duration": duration_str,
                "channel": entry.get("channel") or entry.get("uploader") or "Unbekannt",
            })
        return results
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/health")
def health(): return {"status":"ok","lm_studio":available(),"llama_cpp":lcpp_available()}


from . import panel_api
panel_api.install(app)
