"""On-demand lifecycle for the user's local AI servers (llama.cpp router, LM Studio, Ollama).

GPU memory rules (one 24 GB card shared by every local runtime):
- Before a local model loads, every *other* local runtime is released and VRAM is
  confirmed to have dropped, so two runtimes never hold models at the same time.
- Switching to an online/CLI provider releases the local runtimes this app loaded.
- Hiding, minimizing, toggling or quitting releases everything this app used.
"""
import glob
import os
from pathlib import Path
import subprocess
import time
import httpx

from . import recipe_store as store
from .lmstudio import load_model

UNIT = 'llama-server.service'
OLLAMA_UNIT = 'ollama.service'
LOCAL = ('llamacpp', 'lmstudio', 'ollama')
_used = set()
_ollama_started = False
_lmstudio_server_started = False


# --- GPU memory -------------------------------------------------------------

def _vram_file():
    """sysfs counter of the largest (discrete) GPU; the iGPU's small carve-out is ignored."""
    best = None
    for total in glob.glob('/sys/class/drm/card*/device/mem_info_vram_total'):
        try:
            size = int(Path(total).read_text())
        except (OSError, ValueError):
            continue
        if best is None or size > best[0]:
            best = (size, total.removesuffix('total') + 'used')
    return best


def vram():
    """(used, total) in bytes, or None when the driver does not report it."""
    found = _vram_file()
    if not found:
        return None
    try:
        return int(Path(found[1]).read_text()), found[0]
    except (OSError, ValueError):
        return None


def wait_for_vram_release(timeout=20.0, settle=1.0):
    """Wait until GPU memory stops dropping, i.e. the released model is really gone."""
    reading = vram()
    if reading is None:
        time.sleep(.5)
        return
    lowest, stable_since = reading[0], time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(.25)
        current = (vram() or (lowest, 0))[0]
        if current < lowest - 64 * 1024 * 1024:
            lowest, stable_since = current, time.monotonic()
        elif time.monotonic() - stable_since >= settle:
            return


def require_vram(size_bytes):
    """Refuse to load weights that cannot fit: a full GPU can crash the driver or the desktop."""
    reading = vram()
    if not reading or not size_bytes:
        return
    used, total = reading
    free = total - used
    if free < size_bytes:
        raise store.TranslationUnavailable(
            f'Not enough free GPU memory: {free / 2**30:.1f} GiB free, the model needs about {size_bytes / 2**30:.1f} GiB. '
            'Close other programs that use the GPU or choose a smaller model.')


# --- llama.cpp router --------------------------------------------------------

def llama_router():
    from .ai_config import PROVIDERS
    return (PROVIDERS.get('llamacpp', {}).get('base_url') or 'http://127.0.0.1:8080/v1').rstrip('/').removesuffix('/v1')


def llama_models():
    try:
        response = httpx.get(llama_router() + '/models', timeout=3)
        response.raise_for_status()
        return response.json().get('data', [])
    except (httpx.HTTPError, ValueError):
        return None


def _service_active(unit):
    try:
        return subprocess.run(['systemctl', '--user', 'is-active', '--quiet', unit], timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def release_llamacpp():
    """Unload router models, then stop the service; KillMode=control-group ends every model worker with it."""
    for row in llama_models() or []:
        if row.get('status', {}).get('value') in ('loaded', 'sleeping', 'loading'):
            try:
                httpx.post(llama_router() + '/models/unload', json={'model': row.get('id')}, timeout=10)
            except httpx.HTTPError:
                pass
    try:
        subprocess.run(['systemctl', '--user', 'stop', UNIT], check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    _used.discard('llamacpp')


def _llama_size(model):
    models_dir = Path(os.getenv('LLAMA_MODELS_DIR', '/mnt/ai/Models/llama.cpp-router'))
    try:
        return (models_dir / f'{model}.gguf').resolve().stat().st_size
    except OSError:
        return 0


def ensure_llamacpp(model=None):
    if llama_models() is None:
        try:
            subprocess.run(['systemctl', '--user', 'start', UNIT], check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise store.TranslationUnavailable('Local AI server could not be started') from exc
        deadline = time.monotonic() + 30
        while llama_models() is None:
            if time.monotonic() >= deadline:
                raise store.TranslationUnavailable('Local AI server did not become ready')
            time.sleep(.2)
    if model:
        rows = llama_models() or []
        loaded = [row.get('id') for row in rows if row.get('status', {}).get('value') in ('loaded', 'sleeping')]
        if model not in loaded:
            # The router keeps one model; the old one is unloaded before the new one loads.
            require_vram(_llama_size(model) - sum(_llama_size(name) for name in loaded))
        load_model(model, 'llamacpp')


# --- LM Studio ---------------------------------------------------------------

def _lmstudio_native():
    from .lmstudio import BASE_URL
    return BASE_URL.rstrip('/').removesuffix('/v1')


def _lmstudio_catalog():
    try:
        return httpx.get(_lmstudio_native() + '/api/v1/models', timeout=1.5).json().get('models', [])
    except (httpx.HTTPError, ValueError):
        return None


def release_lmstudio(model=None):
    """Unload LM Studio models (all of them, or only `model`) and stop a server this app started."""
    global _lmstudio_server_started
    catalog = _lmstudio_catalog()
    for row in catalog or []:
        if model is None or row.get('key') == model:
            for instance in row.get('loaded_instances', []):
                if instance.get('id'):
                    try:
                        httpx.post(_lmstudio_native() + '/api/v1/models/unload', json={'instance_id': instance['id']}, timeout=30)
                    except httpx.HTTPError:
                        pass
    if model is None and _lmstudio_server_started:
        from .ai_config import lmstudio_cli
        cli = lmstudio_cli()
        if cli:
            try:
                subprocess.run([cli, 'server', 'stop'], capture_output=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        _lmstudio_server_started = False
    if model is None:
        _used.discard('lmstudio')


def ensure_lmstudio(model=None):
    global _lmstudio_server_started
    from .ai_config import lmstudio_cli, lmstudio_running
    if not lmstudio_running():
        cli = lmstudio_cli()
        if not cli:
            raise store.TranslationUnavailable('LM Studio is not installed or running')
        try:
            subprocess.run([cli, 'server', 'start'], check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise store.TranslationUnavailable('LM Studio server could not be started') from exc
        _lmstudio_server_started = True
        deadline = time.monotonic() + 30
        while not lmstudio_running():
            if time.monotonic() >= deadline:
                raise store.TranslationUnavailable('LM Studio server did not become ready')
            time.sleep(.2)
    if model:
        catalog = _lmstudio_catalog() or []
        row = next((row for row in catalog if row.get('key') == model), {})
        if not row.get('loaded_instances'):
            # load_model unloads LM Studio's other instances first, so only count this model.
            loaded = [other.get('key') for other in catalog if other.get('loaded_instances')]
            if loaded:
                for key in loaded:
                    release_lmstudio(key)
                wait_for_vram_release()
            require_vram(row.get('size_bytes', 0))
        load_model(model, 'lmstudio')


# --- Ollama ------------------------------------------------------------------

def ollama_root():
    return os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/').removesuffix('/v1')


def ollama_running():
    try:
        return httpx.get(ollama_root() + '/api/version', timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def ollama_unit_installed():
    return (Path.home() / '.config/systemd/user' / OLLAMA_UNIT).is_file()


def _ollama_loaded():
    try:
        return [row['name'] for row in httpx.get(ollama_root() + '/api/ps', timeout=2).json().get('models', [])]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def _ollama_size(model):
    try:
        for row in httpx.get(ollama_root() + '/api/tags', timeout=2).json().get('models', []):
            if row.get('name', '').removesuffix(':latest') == model.removesuffix(':latest'):
                return int(row.get('size', 0))
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return 0


def release_ollama(model=None, stop_service=True):
    """Unload models (frees VRAM immediately) and stop the service like llama-server."""
    global _ollama_started
    if ollama_running():
        for name in ([model] if model else _ollama_loaded()):
            try:
                httpx.post(ollama_root() + '/api/generate', json={'model': name, 'keep_alive': 0}, timeout=30)
            except httpx.HTTPError:
                pass
    if stop_service and ollama_unit_installed():
        try:
            subprocess.run(['systemctl', '--user', 'stop', OLLAMA_UNIT], check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
        _ollama_started = False
        _used.discard('ollama')


def ensure_ollama(model=None):
    """Start the user's ollama.service when needed, then load the model onto the GPU."""
    global _ollama_started
    if not ollama_running():
        if not ollama_unit_installed():
            raise store.TranslationUnavailable('Ollama is not running')
        try:
            # The unit's ExecStartPost registers new GGUFs, so this can take a moment.
            subprocess.run(['systemctl', '--user', 'start', OLLAMA_UNIT], check=True, capture_output=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as exc:
            raise store.TranslationUnavailable('Ollama could not be started') from exc
        _ollama_started = True
        deadline = time.monotonic() + 60
        while not ollama_running():
            if time.monotonic() >= deadline:
                raise store.TranslationUnavailable('Ollama did not become ready')
            time.sleep(.2)
    if model:
        loaded = _ollama_loaded()
        if model not in loaded and model + ':latest' not in loaded:
            if loaded:
                # Make the swap explicit instead of relying on Ollama's scheduler.
                for name in loaded:
                    release_ollama(name, stop_service=False)
                wait_for_vram_release()
            require_vram(_ollama_size(model))
        try:
            response = httpx.post(ollama_root() + '/api/generate', json={'model': model, 'keep_alive': '10m'}, timeout=300)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise store.TranslationUnavailable('Ollama could not load the model') from exc


# --- Orchestration -----------------------------------------------------------

def _holds_gpu(provider):
    if provider == 'llamacpp':
        return _service_active(UNIT) or llama_models() is not None
    if provider == 'lmstudio':
        return any(row.get('loaded_instances') for row in (_lmstudio_catalog() or [])) or _lmstudio_server_started
    if provider == 'ollama':
        return ollama_running()
    return False


RELEASE = {'llamacpp': release_llamacpp, 'lmstudio': release_lmstudio, 'ollama': release_ollama}


def release_all(keep=None, only=None):
    """Release local runtimes (except `keep`; limited to `only` when given) and wait for VRAM to drop."""
    released = False
    for provider in LOCAL:
        if provider == keep or (only is not None and provider not in only):
            continue
        if _holds_gpu(provider):
            RELEASE[provider]()
            released = True
        _used.discard(provider)
    if released:
        wait_for_vram_release()
    return released


def ensure(provider: str | None = None, model: str | None = None):
    cfg = store.configuration()
    target = provider or cfg.get('provider')
    if target not in LOCAL:
        # Online and CLI providers need no GPU: give back what this app loaded.
        release_all(only=set(_used))
        return
    # Never let two runtimes hold models at once; this also covers runtimes started elsewhere.
    release_all(keep=target)
    target_model = model or (cfg.get('model') if cfg.get('provider') == target else None)
    _used.add(target)
    {'llamacpp': ensure_llamacpp, 'lmstudio': ensure_lmstudio, 'ollama': ensure_ollama}[target](target_model)


def release_unselected(provider):
    """Settings switched provider: free the runtimes this app loaded for the previous choice."""
    release_all(keep=provider if provider in LOCAL else None, only=set(_used))


def stop():
    """Window hidden, minimized, toggled or app quitting: free all GPU memory this app may hold."""
    try:
        cfg = store.configuration()
        selected = {cfg.get('provider')} & set(LOCAL)
    except Exception:
        selected = set()
    # llama-server is always stopped (as before); the others only when this app used them.
    release_all(only=set(_used) | selected | {'llamacpp'} | ({'ollama'} if _ollama_started else set()))
