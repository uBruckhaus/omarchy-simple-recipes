/* Discover model languages and discard replies belonging to older selections. */
(() => {
  const start = () => {
    const importForm = document.querySelector('#import-form');
    const provider = document.querySelector('#provider') || document.querySelector('#ai_provider');
    if (!provider) return;
    const form = importForm || provider.closest('form');
    const target = document.querySelector('#target-lang') || document.querySelector('#recipe_target_language');
    const model = form.querySelector('[name="llm_model"]') || form.querySelector('[name="ai_model"]');
    const customModel = form.querySelector('[name="custom_model"]');
    const key = form.querySelector('[name="provider_token"]') || form.querySelector('[name="api_key"]');
    const url = form.querySelector('[name="custom_url"]');
    const ai = form.querySelector('[name="use_ai"]');
    const tr = window.recipeT || (key => key);
    const box = document.createElement('div');
    box.className = 'translation-check';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const hint = document.createElement('small');
    hint.textContent = tr('languages_hint');
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = tr('languages_retry');
    box.append(status, hint, retry);
    form.append(box);
    let layout = document.querySelector('#ui_language');
    if (!layout) {
      const label = document.createElement('label');
      label.textContent = tr('lang_layout_label');
      layout = document.createElement('select');
      layout.id = 'layout-language';
      label.append(layout);
      box.append(label);
      layout.addEventListener('change', () => {
        const location = new URL(window.location.href);
        location.searchParams.set('lang', layout.value);
        window.location.href = location.toString();
      });
    }
    const fill = (select, languages, selected, empty) => {
      select.replaceChildren();
      for (const language of languages) {
        const option = document.createElement('option');
        option.value = language.code;
        option.textContent = language.name;
        select.append(option);
      }
      if (!languages.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = empty;
        select.append(option);
      }
      select.value = languages.some(language => language.code === selected) ? selected : languages[0]?.code || '';
    };
    // Layout translations are available even when the model is unreachable.
    const layouts = Object.entries(window.recipeLayouts || {en: 'English', de: 'Deutsch', fr: 'Français', it: 'Italiano', es: 'Español'}).map(([code, name]) => ({code, name}));
    fill(layout, layouts, layout.value || document.documentElement.lang, '');
    let timer, controller, generation = 0, verified = false, languages = [];
    let requestedLanguage = target?.value || 'en';
    const updateSelectedLanguage = () => {
      requestedLanguage = target?.value || requestedLanguage;
      verified = languages.some(language => language.code === target?.value);
    };
    const check = async (version) => {
      controller = new AbortController();
      const data = new FormData();
      data.set('provider', provider.value);
      data.set('ai_model', ['custom', 'ollama'].includes(provider.value) && customModel ? customModel.value.trim() : model?.value.trim() || '');
      data.set('api_key', key?.value.trim() || '');
      data.set('custom_url', url?.value.trim() || '');
      retry.disabled = true;
      try {
        status.textContent = tr('model_loading');
        const selection = await fetch('/api/ai/select', {method: 'POST', body: data, signal: controller.signal});
        if (version !== generation) return;
        if (!selection.ok) {
          status.textContent = tr('model_failed');
          box.dataset.state = 'unverified';
          return;
        }
        if (form.dispatchEvent) form.dispatchEvent(new CustomEvent('recipe-model-selected'));
        status.textContent = tr('languages_checking');
        const response = await fetch('/api/ai/languages', {method: 'POST', body: data, signal: controller.signal});
        if (!response.ok) throw new Error('Language check failed');
        const result = await response.json();
        if (version !== generation) return;
        languages = result.target_languages || [];
        if (target) {
          fill(target, languages, requestedLanguage, tr('languages_empty'));
          target.disabled = !languages.length;
        }
        fill(layout, result.layout_languages || layouts, layout.value, '');
        verified = languages.some(language => language.code === target?.value);
        status.textContent = languages.length
          ? `✓ ${tr('languages_verified')}: ${languages.map(language => language.name).join(', ')}`
          : (tr('languages_failed'));
        box.dataset.state = verified ? 'verified' : 'unverified';
      } catch (error) {
        if (version !== generation || error.name === 'AbortError') return;
        status.textContent = tr('languages_failed');
        if (target) fill(target, [], '', tr('languages_empty'));
        box.dataset.state = 'unverified';
      } finally {
        if (version === generation) retry.disabled = false;
      }
    };
    const schedule = () => {
      clearTimeout(timer);
      controller?.abort();
      const version = ++generation;
      verified = false;
      languages = [];
      retry.disabled = false;
      if (target?.value) requestedLanguage = target.value;
      if (target) target.disabled = true;
      status.textContent = tr('languages_checking');
      box.dataset.state = 'checking';
      timer = setTimeout(() => check(version), 600);
    };
    [provider, model, customModel, key, url, ai, document.querySelector('#model_preset_select')].filter(Boolean).forEach(el => {
      el.addEventListener('change', schedule);
      if (el.tagName === 'INPUT') el.addEventListener('input', schedule);
    });
    target?.addEventListener('change', updateSelectedLanguage);
    retry.addEventListener('click', schedule);
    if (importForm) importForm.addEventListener('submit', event => {
      if (ai?.checked && !verified) {
        event.preventDefault();
        event.stopImmediatePropagation();
        status.textContent = tr('languages_wait');
        status.scrollIntoView({block: 'nearest'});
      }
    }, true);
    schedule();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
