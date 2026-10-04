"""Maintainer tool: pre-translate the interface into every supported target language.

Run from the repository root with a signed-in Claude Code CLI:
    python -m scripts.generate_locales [--missing] [codes...]
The results are shipped in app/locales and need no model at runtime.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import claude_provider
from app.i18n import TARGET_LANGUAGES
from app.interface_languages import BUILT_IN, source_strings
from app.recipe_languages import RECIPE_LANGUAGES

LOCALES = Path(__file__).resolve().parent.parent / "app/locales"
MARKUP = re.compile(r"\{[^}]*\}|</?\w+[^>]*>")


def problems(source, values):
    errors = [key for key in source if not isinstance(values.get(key), str) or not values[key].strip()]
    errors += [key for key in source if key not in errors and sorted(MARKUP.findall(source[key])) != sorted(MARKUP.findall(values[key]))]
    return errors


def generate(code, attempts=3):
    existing = {}
    if "--missing" in sys.argv:
        try:
            existing = json.loads((LOCALES / f"{code}.json").read_text())
        except (OSError, ValueError):
            existing = {}
    # With --missing only labels added since the last run are translated and merged in.
    source = {key: value for key, value in source_strings().items() if key not in existing}
    if not source:
        return code, "up to date"
    language = RECIPE_LANGUAGES[code]["prompt_name"]
    schema = {"type": "object", "properties": {key: {"type": "string"} for key in source}, "required": list(source), "additionalProperties": False}
    prompt = ("Translate every value of this desktop recipe application's interface into " + language + ". "
              "Keys starting with 'category.' are recipe category names; keys starting with 'duration.' are recipe length classes. "
              "Keep all property names unchanged. Preserve HTML tags such as <em> and <br>, the {model} placeholder, emoji, arrows, "
              "keyboard shortcuts, product names (Simple Recipes, Codex, Claude, ChatGPT, YouTube, WhatsApp, llama.cpp, LM Studio, Ollama) "
              "and numeric ranges exactly. Use natural, concise interface wording that a native speaker expects in desktop software. "
              "Return the complete JSON object.\n" + json.dumps(source, ensure_ascii=False))
    for attempt in range(attempts):
        values = claude_provider.complete(prompt, "sonnet", schema, timeout=600)
        bad = problems(source, values)
        if not bad:
            (LOCALES / f"{code}.json").write_text(json.dumps({**existing, **values}, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
            return code, "ok"
        print(code, "retry", attempt + 1, bad[:5], flush=True)
    return code, f"failed: {bad[:5]}"


if __name__ == "__main__":
    codes = [arg for arg in sys.argv[1:] if not arg.startswith("--")] or [code for code in TARGET_LANGUAGES if code not in BUILT_IN]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code, result in pool.map(generate, codes):
            print(code, result, flush=True)
