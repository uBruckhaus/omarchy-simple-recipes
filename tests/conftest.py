"""Keep tests independent of installed models and running AI services."""
import pytest
from unittest.mock import patch

@pytest.fixture(autouse=True)
def offline_provider_discovery():
    with patch("app.ai_config.get_local_llama_models", return_value=["gemma-4-12B-it-QAT-Q4_0"]), \
         patch("app.main.require_translation"), \
         patch("app.main.available", return_value={"online": False, "active": "", "models": []}), \
         patch("app.main.lcpp_available", return_value={"online": False, "active": "", "models": []}):
        yield
