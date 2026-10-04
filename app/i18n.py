# Simple Recipes - Internationalization (i18n) Module
# Default layout language: English ("en")

DEFAULT_LANGUAGE = "en"
DEFAULT_TARGET_LANGUAGE = "en"

LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "it": "Italiano",
    "es": "Español",
}

from .recipe_languages import RECIPE_LANGUAGES
TARGET_LANGUAGES = {code: info["name"] for code, info in RECIPE_LANGUAGES.items()}

CATEGORY_TRANSLATIONS = {
    "en": {
        "Pasta": "Pasta",
        "Pizza": "Pizza",
        "Suppe": "Soup",
        "Salat": "Salad",
        "Backen": "Baking",
        "Dessert": "Dessert",
        "Frühstück": "Breakfast",
        "Fleisch": "Meat",
        "Fisch": "Fish",
        "Vegetarisch": "Vegetarian",
        "Sonstiges": "Other",
    },
    "de": {
        "Pasta": "Pasta",
        "Pizza": "Pizza",
        "Suppe": "Suppe",
        "Salat": "Salat",
        "Backen": "Backen",
        "Dessert": "Dessert",
        "Frühstück": "Frühstück",
        "Fleisch": "Fleisch",
        "Fisch": "Fisch",
        "Vegetarisch": "Vegetarisch",
        "Sonstiges": "Sonstiges",
    },
}

DURATION_CLASS_TRANSLATIONS = {
    "en": {
        "kurz": "Quick",
        "mittel": "Medium",
        "lang": "Long",
        "unbekannt": "Unknown",
    },
    "de": {
        "kurz": "Kurz",
        "mittel": "Mittel",
        "lang": "Lang",
        "unbekannt": "Unbekannt",
    },
}

TRANSLATIONS = {
    "en": {
        # App
        "app_name": "Simple Recipes",
        "app_tagline": "Your personal recipe collection",
        "nav_recipes": "Recipes",
        "nav_settings": "Settings",
        
        # Hero & Dropzone
        "hero_eyebrow": "YOUR PERSONAL RECIPE COLLECTION",
        "hero_title": "What would you like<br><em>to cook today?</em>",
        "hero_subtitle": "Paste a link from a recipe site, YouTube, Instagram or Facebook. Everything is organized and kept locally on your machine.",
        "tab_import_url": "Import Link",
        "tab_video_search": "🎬 Video Search",
        "import_label": "Drop recipe link here",
        "import_sub": "Drag & drop a URL or paste it directly",
        "import_btn": "Import",
        "import_placeholder": "https://…",
        "video_label": "Recipe Video Search",
        "video_sub": "Search for up to 5 recipe videos on YouTube",
        "video_placeholder": "e.g. Lasagna Jamie Oliver…",
        "video_search_btn": "Search",
        "provider_label": "Provider",
        "model_label": "Model",
        "model_name_label": "Model Name",
        "custom_model_placeholder": "e.g. llama3.2",
        "server_url_label": "Server URL",
        "api_key_label": "API Key",
        "target_lang_label": "Recipe Target Language",
        "use_ai_label": "Translate with AI",
        "import_without_ai_notice": "– Import without AI possible",
        "connected": "connected",
        "offline": "offline",
        "active_online": "active (Online API)",
        "model_active": "active",
        "provider_ready": "ready",
        "provider_not_installed": "not installed",
        "provider_not_configured": "not configured",
        "provider_not_logged_in": "not signed in",
        "provider_not_installed_tip": "This local provider is not installed or running.",
        "provider_not_configured_tip": "API key required. Select to enter your key.",
        "provider_not_logged_in_tip": "Run 'codex login' in a terminal to authenticate.",
        
        # Toolbar & Filters
        "recipes_count": "recipes",
        "view_flat": "List",
        "view_grouped": "Grouped",
        "favorites": "Favorites",
        "search_placeholder": "Search recipes…",
        "sort_newest": "Newest first",
        "sort_oldest": "Oldest first",
        "sort_title": "Name A–Z",
        "sort_duration": "Shortest duration",
        "sort_calories": "Lowest calories",
        "sort_tried": "Tried recipes first",
        
        # Recipe Card & List
        "min": "min",
        "status_tried": "tried",
        "status_untried": "not tried yet",
        "no_recipes_title": "No recipes found.",
        "no_recipes_sub": "Choose a different category or import a new recipe.",
        
        # Recipe Detail
        "back_to_recipes": "← All Recipes",
        "ingredients": "Ingredients",
        "instructions": "Instructions",
        "duration": "Duration",
        "servings": "Servings",
        "calories": "Calories",
        "cal_per_serving": "kcal / serving",
        "action_start_cooking": "👨‍🍳 Cooking Mode",
        "action_reprocess_ai": "✨ Reprocess with AI",
        "action_share": "Share",
        "action_share_whatsapp": "Share via WhatsApp",
        "action_delete": "Delete recipe",
        "action_delete_confirm": "Do you really want to delete this recipe?",
        "share_modal_title": "Share Recipe",
        "share_modal_sub": "Choose how you would like to share:",
        "share_all": "Send complete recipe",
        "share_ingredients": "Send ingredients list only",
        "source_original": "Original Recipe:",
        "category_label": "Category",
        "category_new": "+ New Category",
        
        # Cooking Mode
        "cooking_mode_title": "Cooking Mode",
        "cooking_step": "Step",
        "cooking_of": "of",
        "cooking_prev": "← Previous",
        "cooking_next": "Next →",
        "cooking_done": "✓ Finished",
        "cooking_close": "Exit Cooking Mode",
        "timer_start": "Start timer",
        
        # Processing Overlay
        "processing_eyebrow": "RECIPE IS BEING PROCESSED",
        "processing_title": "AI is preparing the recipe",
        "processing_subtitle": "Extracting · Translating · Converting units",
        "processing_cancel": "Cancel",
        "processing_cancel_sub": "The running request will be cancelled.",
        
        # Settings
        "settings_title": "Settings · Simple Recipes",
        "settings_heading": "Settings",
        "lang_eyebrow": "LOCALIZATION",
        "lang_heading": "🌐 Language & Translation",
        "lang_desc": "Set your layout language and the target translation language for recipe imports.",
        "lang_layout_label": "Interface language",
        "lang_recipe_label": "Recipe Target Language",
        "lang_save_btn": "Save Language Settings",
        
        "ai_eyebrow": "ARTIFICIAL INTELLIGENCE",
        "ai_heading": "🤖 AI Providers & Models",
        "ai_desc": "Choose which AI prepares, translates, and normalizes recipe ingredients into metric units. You can use your local GPU (llama.cpp ROCm, LM Studio) or fast cloud AI providers (Google Gemini, OpenAI, Groq, OpenRouter etc.).",
        "ai_provider_label": "AI Provider",
        "ai_custom_url_label": "Server URL (OpenAI-compatible)",
        "ai_api_key_label": "API Key / Token",
        "ai_recommended_model_label": "Recommended Model",
        "ai_custom_model_option": "✏️ Enter custom model manually…",
        "ai_model_name_label": "Model Name",
        "ai_model_name_help": "Passed directly to the /v1/chat/completions endpoint.",
        "ai_test_btn": "Test Connection",
        "ai_save_btn": "Save AI Settings",
        "ai_reset_btn": "🔄 Reset recipes and settings",
        "ai_reset_confirm": "Delete all recipes, categories, the phone number, API keys and preferences? This cannot be undone.",
        "key_saved": "Saved",
        "key_not_saved": "No API key configured",
        "key_leave_empty_hint": "(leave blank to keep current)",
        
        "notifications_eyebrow": "NOTIFICATIONS",
        "whatsapp_heading": "📱 WhatsApp Ingredients List",
        "whatsapp_desc": "This phone number will be pre-filled as the default recipient when sharing ingredient lists.",
        "phone_label": "WhatsApp Phone Number",
        "phone_save_btn": "Save Phone Number",
        "phone_help": "German numbers may start with 0; international numbers with + or 00.",
    },
    
    "de": {
        # App
        "app_name": "Simple Recipes",
        "app_tagline": "Deine persönliche Rezeptsammlung",
        "nav_recipes": "Rezepte",
        "nav_settings": "Einstellungen",
        
        # Hero & Dropzone
        "hero_eyebrow": "DEINE PERSÖNLICHE REZEPTSAMMLUNG",
        "hero_title": "Was möchtest du<br><em>heute kochen?</em>",
        "hero_subtitle": "Füge einen Link von einer Rezeptseite, YouTube, Instagram oder Facebook ein. Alles landet ordentlich und lokal auf deinem Rechner.",
        "tab_import_url": "Link importieren",
        "tab_video_search": "🎬 Video-Suche",
        "import_label": "Rezept-Link hier ablegen",
        "import_sub": "URL hineinziehen oder direkt einfügen",
        "import_btn": "Importieren",
        "import_placeholder": "https://…",
        "video_label": "Video-Rezeptsuche",
        "video_sub": "Suche nach bis zu 5 Rezept-Videos auf YouTube",
        "video_placeholder": "z.B. Lasagne Henssler…",
        "video_search_btn": "Suchen",
        "provider_label": "Provider",
        "model_label": "Modell",
        "model_name_label": "Modellname",
        "custom_model_placeholder": "z. B. llama3.2",
        "server_url_label": "Server-URL",
        "api_key_label": "API-Key",
        "target_lang_label": "Zielsprache für Rezepte",
        "use_ai_label": "Mit KI übersetzen",
        "import_without_ai_notice": "– Import ohne KI möglich",
        "connected": "verbunden",
        "offline": "offline",
        "active_online": "aktiv (Online API)",
        "model_active": "aktiv",
        "provider_ready": "bereit",
        "provider_not_installed": "nicht installiert",
        "provider_not_configured": "nicht eingerichtet",
        "provider_not_logged_in": "nicht angemeldet",
        "provider_not_installed_tip": "Dieser lokale Provider ist nicht installiert oder läuft nicht.",
        "provider_not_configured_tip": "API-Schlüssel erforderlich. Auswählen, um Schlüssel einzugeben.",
        "provider_not_logged_in_tip": "Führe 'codex login' im Terminal aus, um dich anzumelden.",
        
        # Toolbar & Filters
        "recipes_count": "Rezepte",
        "view_flat": "Liste",
        "view_grouped": "Gruppiert",
        "favorites": "Favoriten",
        "search_placeholder": "Rezepte durchsuchen …",
        "sort_newest": "Neueste zuerst",
        "sort_oldest": "Älteste zuerst",
        "sort_title": "Name A–Z",
        "sort_duration": "Kürzeste Dauer",
        "sort_calories": "Wenigste Kalorien",
        "sort_tried": "Ausprobierte zuerst",
        
        # Recipe Card & List
        "min": "Min.",
        "status_tried": "ausprobiert",
        "status_untried": "noch nicht ausprobiert",
        "no_recipes_title": "Keine Rezepte gefunden.",
        "no_recipes_sub": "Wähle eine andere Kategorie oder importiere ein neues Rezept.",
        
        # Recipe Detail
        "back_to_recipes": "← Alle Rezepte",
        "ingredients": "Zutaten",
        "instructions": "Zubereitung",
        "duration": "Dauer",
        "servings": "Portionen",
        "calories": "Kalorien",
        "cal_per_serving": "kcal / Portion",
        "action_start_cooking": "👨‍🍳 Kochmodus",
        "action_reprocess_ai": "✨ Mit KI neu aufbereiten",
        "action_share": "Teilen",
        "action_share_whatsapp": "Per WhatsApp teilen",
        "action_delete": "Rezept löschen",
        "action_delete_confirm": "Möchtest du dieses Rezept wirklich löschen?",
        "share_modal_title": "Rezept teilen",
        "share_modal_sub": "Wähle aus, wie du das Rezept teilen möchtest:",
        "share_all": "Ganzes Rezept senden",
        "share_ingredients": "Nur Zutatenliste senden",
        "source_original": "Original-Rezept:",
        "category_label": "Kategorie",
        "category_new": "+ Neue Kategorie",
        
        # Cooking Mode
        "cooking_mode_title": "Kochmodus",
        "cooking_step": "Schritt",
        "cooking_of": "von",
        "cooking_prev": "← Zurück",
        "cooking_next": "Weiter →",
        "cooking_done": "✓ Fertig",
        "cooking_close": "Kochmodus beenden",
        "timer_start": "Timer starten",
        
        # Processing Overlay
        "processing_eyebrow": "REZEPT WIRD VERARBEITET",
        "processing_title": "Die KI kocht die Daten auf",
        "processing_subtitle": "Extrahieren · Übersetzen · Einheiten umrechnen",
        "processing_cancel": "Abbrechen",
        "processing_cancel_sub": "Die laufende Anfrage wird beendet.",
        
        # Settings
        "settings_title": "Einstellungen · Simple Recipes",
        "settings_heading": "Einstellungen",
        "lang_eyebrow": "LOKALISIERUNG",
        "lang_heading": "🌐 Spracheinstellungen",
        "lang_desc": "Wähle deine bevorzugte Sprache für die Benutzeroberfläche und die Ziel-Übersetzungssprache für Rezepte.",
        "lang_layout_label": "Sprache der Benutzeroberfläche",
        "lang_recipe_label": "Zielsprache für Rezepte",
        "lang_save_btn": "Spracheinstellungen speichern",
        
        "ai_eyebrow": "KÜNSTLICHE INTELLIGENZ",
        "ai_heading": "🤖 KI-Provider & Modelle",
        "ai_desc": "Wähle, welche KI deine Rezepte aufbereitet, übersetzt und Zutaten in metrische Einheiten umrechnet. Du kannst deine lokale GPU (llama.cpp ROCm, LM Studio) oder schnelle Online-Dienste (Google Gemini, OpenAI, Groq, OpenRouter etc.) nutzen.",
        "ai_provider_label": "KI-Provider",
        "ai_custom_url_label": "Server-URL (OpenAI-kompatibel)",
        "ai_api_key_label": "API-Key / Token",
        "ai_recommended_model_label": "Empfohlenes Modell",
        "ai_custom_model_option": "✏️ Anderes Modell manuell eingeben…",
        "ai_model_name_label": "Modellname",
        "ai_model_name_help": "Wird direkt an den /v1/chat/completions Endpunkt übergeben.",
        "ai_test_btn": "Verbindung testen",
        "ai_save_btn": "KI-Einstellungen speichern",
        "ai_reset_btn": "🔄 Rezepte und Einstellungen zurücksetzen",
        "ai_reset_confirm": "Alle Rezepte, Kategorien, die Telefonnummer, API-Keys und Einstellungen löschen? Dies kann nicht rückgängig gemacht werden.",
        "key_saved": "Gespeichert",
        "key_not_saved": "Kein API-Key hinterlegt",
        "key_leave_empty_hint": "(Feld leer lassen, um beizubehalten)",
        
        "notifications_eyebrow": "BENACHRICHTIGUNGEN",
        "whatsapp_heading": "📱 WhatsApp-Zutatenliste",
        "whatsapp_desc": "Diese Nummer wird als Standard-Empfänger beim Teilen der Zutatenliste vorausgefüllt.",
        "phone_label": "WhatsApp-Telefonnummer",
        "phone_save_btn": "Telefonnummer speichern",
        "phone_help": "Deutsche Nummern dürfen mit 0 beginnen; internationale Nummern mit + oder 00.",
    }
}

from .ui_locales import UI_TRANSLATIONS, UI_EXTRA
TRANSLATIONS.update(UI_TRANSLATIONS)
for language, strings in UI_EXTRA.items():
    TRANSLATIONS[language].update(strings)
CATEGORY_TRANSLATIONS.update({
    "fr": dict(zip(CATEGORY_TRANSLATIONS["en"], ["Pâtes", "Pizza", "Soupe", "Salade", "Pâtisserie", "Dessert", "Petit-déjeuner", "Viande", "Poisson", "Végétarien", "Autres"])),
    "it": dict(zip(CATEGORY_TRANSLATIONS["en"], ["Pasta", "Pizza", "Zuppa", "Insalata", "Prodotti da forno", "Dessert", "Colazione", "Carne", "Pesce", "Vegetariano", "Altro"])),
    "es": dict(zip(CATEGORY_TRANSLATIONS["en"], ["Pasta", "Pizza", "Sopa", "Ensalada", "Horneado", "Postre", "Desayuno", "Carne", "Pescado", "Vegetariano", "Otros"])),
})
DURATION_CLASS_TRANSLATIONS.update({
    "fr": {"kurz": "Rapide", "mittel": "Moyen", "lang": "Long", "unbekannt": "Inconnue"},
    "it": {"kurz": "Breve", "mittel": "Media", "lang": "Lunga", "unbekannt": "Sconosciuta"},
    "es": {"kurz": "Corta", "mittel": "Media", "lang": "Larga", "unbekannt": "Desconocida"},
})

def t(key: str, lang: str = "en") -> str:
    """Translate a key into the requested language, with English fallback."""
    table = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    return table.get(key, TRANSLATIONS["en"].get(key, key))

def localize_category(category_name: str, lang: str = "en") -> str:
    """Return localized display name for a recipe category."""
    cats = CATEGORY_TRANSLATIONS.get(lang, CATEGORY_TRANSLATIONS["en"])
    return cats.get(category_name, category_name)

def localize_duration(dur_class: str, lang: str = "en") -> str:
    """Return localized duration description."""
    durs = DURATION_CLASS_TRANSLATIONS.get(lang, DURATION_CLASS_TRANSLATIONS["en"])
    return durs.get(dur_class, dur_class)
