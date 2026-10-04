"""Providers that run through a locally signed-in CLI instead of an HTTP API."""
from . import claude_provider, codex_provider

BACKENDS = {codex_provider.BASE_URL: codex_provider, claude_provider.BASE_URL: claude_provider}
NAMES = {"codex": codex_provider, "claude": claude_provider}


def backend(base_url):
    return BACKENDS.get(base_url)


def detected():
    """Signed-in CLI providers, in order of preference."""
    return [name for name in ("claude", "codex") if NAMES[name].available()]
