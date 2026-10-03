"""On-demand lifecycle for the user's configured llama.cpp server."""
import subprocess
import time
import httpx

from . import recipe_store as store
from .lmstudio import load_model

UNIT = 'llama-server.service'


def ensure():
    cfg = store.configuration()
    if cfg['provider'] != 'llamacpp':
        return
    router = cfg['base_url'].rstrip('/').removesuffix('/v1')
    try:
        response = httpx.get(router + '/models', timeout=3)
        response.raise_for_status()
    except httpx.HTTPError:
        pass
    else:
        load_model(cfg['model'], 'llamacpp')
        return
    try:
        subprocess.run(['systemctl', '--user', 'start', UNIT], check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise store.TranslationUnavailable('Local AI server could not be started') from exc
    deadline = time.monotonic() + 30
    while True:
        try:
            response = httpx.get(router + '/models', timeout=3)
            response.raise_for_status()
            break
        except httpx.HTTPError:
            if time.monotonic() >= deadline:
                raise store.TranslationUnavailable('Local AI server did not become ready')
            time.sleep(.2)
    load_model(cfg['model'], 'llamacpp')


def stop():
    subprocess.run(['systemctl', '--user', 'stop', UNIT], check=True, capture_output=True, timeout=60)
