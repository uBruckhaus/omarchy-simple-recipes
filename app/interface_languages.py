"""Model-translated desktop labels, generated on demand and cached in SQLite."""
import json

from . import recipe_store as store
from .i18n import TRANSLATIONS, CATEGORY_TRANSLATIONS, DURATION_CLASS_TRANSLATIONS
from .native_locales import TEXT
from .recipe_languages import RECIPE_LANGUAGES


def source_strings():
    return {**{'ui.' + key: value for key, value in TRANSLATIONS['en'].items()},
            **{'native.' + key: value for key, value in TEXT['en'].items()},
            **{'category.' + key: value for key, value in CATEGORY_TRANSLATIONS['en'].items()},
            **{'duration.' + key: value for key, value in DURATION_CLASS_TRANSLATIONS['en'].items()}}


def apply(language, values):
    source = source_strings()
    if not isinstance(values, dict) or any(not isinstance(values.get(key), str) or not values[key].strip() for key in source):
        raise ValueError('Incomplete interface translation')
    TRANSLATIONS[language] = {key[3:]: values[key] for key in source if key.startswith('ui.')}
    TEXT[language] = {key[7:]: values[key] for key in source if key.startswith('native.')}
    CATEGORY_TRANSLATIONS[language] = {key[9:]: values[key] for key in source if key.startswith('category.')}
    DURATION_CLASS_TRANSLATIONS[language] = {key[9:]: values[key] for key in source if key.startswith('duration.')}


def load(language):
    if language in ('en', 'de', 'fr', 'it', 'es'):
        return True
    try:
        values = json.loads(store.setting('interface_translation_' + language, '{}'))
        if not isinstance(values, dict) or not values.get('native.import_tab') or not values.get('ui.ingredients'):
            return False
        # New labels introduced by an update may use English until refreshed;
        # the user's existing translated interface must remain usable.
        apply(language, {**source_strings(), **values})
    except (ValueError, TypeError):
        return False
    return True


def generate(language):
    if language not in {row['code'] for row in store.targets()}:
        raise ValueError('Verify model language support first')
    source = source_strings(); cfg = store.configuration()
    prompt = ('Translate every value of this desktop recipe application interface into ' + RECIPE_LANGUAGES[language]['prompt_name'] +
              '. Keep all property names unchanged. Preserve HTML tags, placeholders, arrows and numeric ranges. '
              'Use clear, concise interface labels. Return the complete JSON object only.\n' + json.dumps(source, ensure_ascii=False))
    schema = {'type': 'object', 'properties': {key: {'type': 'string'} for key in source}, 'required': list(source), 'additionalProperties': False}
    from .codex_provider import BASE_URL, complete
    if cfg['base_url'] == BASE_URL:
        values = complete(prompt, cfg['model'], schema, timeout=300)
    else:
        import httpx
        headers = {'Authorization': 'Bearer ' + cfg['api_key']} if cfg['api_key'] else {}
        payload = {'model': cfg['model'], 'messages': [{'role': 'user', 'content': prompt}], 'temperature': .1, 'max_tokens': 16000, 'reasoning_effort': 'none',
                   'response_format': {'type': 'json_schema', 'json_schema': {'name': 'interface_labels', 'strict': True, 'schema': schema}}}
        with httpx.Client(timeout=300) as client:
            response = client.post(cfg['base_url'].rstrip('/') + '/chat/completions', headers=headers, json=payload)
            if response.status_code in (400, 422):
                payload.pop('reasoning_effort', None)
                payload['response_format'] = {'type': 'json_object'}
                response = client.post(cfg['base_url'].rstrip('/') + '/chat/completions', headers=headers, json=payload)
            response.raise_for_status()
        text = response.json()['choices'][0]['message']['content'].strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        values = json.loads(text)
    # Validate before caching; apply on the GUI thread after completion.
    if not isinstance(values, dict) or any(not isinstance(values.get(key), str) or not values[key].strip() for key in source):
        raise ValueError('Incomplete interface translation')
    store.save_settings({'interface_translation_' + language: json.dumps(values, ensure_ascii=False)})
    return language
