const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag, value = '') { this.tagName = tag.toUpperCase(); this.value = value; this.children = []; this.events = {}; this.dataset = {}; this.disabled = false; }
  append(...elements) { this.children.push(...elements); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  scrollIntoView() {}
  addEventListener(event, callback) { (this.events[event] ||= []).push(callback); }
  fire(event, payload = {}) { for (const callback of this.events[event] || []) callback(payload); }
  querySelector(selector) { return fields[selector] || null; }
}
const provider = new Element('select', 'custom');
const model = new Element('input', 'model-A');
const target = new Element('select', 'de');
const layout = new Element('select', 'de');
const ai = new Element('input'); ai.checked = true;
const form = new Element('form');
const fields = { '[name="llm_model"]': model, '[name="use_ai"]': ai };
const selectors = { '#import-form': form, '#provider': provider, '#target-lang': target, '#ui_language': layout };
let timers = [], requests = [], selections = [];
const document = { readyState: 'complete', documentElement: {lang: 'de'}, querySelector: selector => selectors[selector] || null, createElement: tag => new Element(tag) };
const context = { document, window: {location: {href: 'http://localhost/'}}, FormData, AbortController, URL,
  setTimeout: callback => { const entry = {callback}; timers.push(entry); return entry; },
  clearTimeout: entry => { if (entry) entry.cancelled = true; },
  fetch: (url, options) => {
    if (url === '/api/ai/select') { selections.push(options.body.get('ai_model')); return Promise.resolve({ok: true}); }
    return new Promise((resolve, reject) => requests.push({url, options, resolve, reject}));
  } };
vm.runInNewContext(fs.readFileSync('app/static/translation-check.js', 'utf8'), context);
const runTimers = () => { const pending = timers; timers = []; for (const entry of pending) if (!entry.cancelled) entry.callback(); };
const tick = () => new Promise(resolve => setImmediate(resolve));
const result = languages => ({ok: true, json: async () => ({target_languages: languages, layout_languages: [{code: 'en', name: 'English'}, {code: 'de', name: 'Deutsch'}, {code: 'fr', name: 'Français'}, {code: 'it', name: 'Italiano'}, {code: 'es', name: 'Español'}]})});
const submit = () => { let blocked = false; form.fire('submit', {preventDefault: () => blocked = true, stopImmediatePropagation() {}}); return blocked; };
(async () => {
  runTimers(); await tick();
  assert.equal(requests[0].options.body.get('ai_model'), 'model-A');
  model.value = 'model-B'; model.fire('change'); runTimers(); await tick();
  assert.equal(requests[1].options.body.get('ai_model'), 'model-B');
  assert.equal(submit(), true);
  requests[1].resolve(result([{code: 'en', name: 'English'}, {code: 'it', name: 'Italiano'}])); await tick();
  assert.deepEqual(target.children.map(option => option.value), ['en', 'it']);
  assert.equal(target.disabled, false);
  assert.deepEqual(layout.children.map(option => option.value), ['en', 'de', 'fr', 'it', 'es']);
  assert.equal(layout.value, 'de');
  requests[0].resolve(result([{code: 'de', name: 'Deutsch'}])); await tick();
  assert.deepEqual(target.children.map(option => option.value), ['en', 'it']);
  target.value = 'it'; target.fire('change'); assert.equal(submit(), false);
  model.value = 'model-C'; model.fire('input'); runTimers(); await tick(); assert.equal(submit(), true);
  requests[2].reject(new Error('offline')); await tick();
  assert.equal(target.value, ''); assert.equal(submit(), true);
  ai.checked = false; assert.equal(submit(), false);
  assert.deepEqual(selections, ['model-A', 'model-B', 'model-C']);
  console.log('Language selector: verified options, independent layouts, stale response protection and import gating passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
