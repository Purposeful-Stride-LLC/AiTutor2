"""Test isolation: private AITUTOR_HOME, and never a real Ollama server."""

import pytest

from aitutor import paths, settings
from fake_ollama import FakeOllama


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path / "home"))
    monkeypatch.delenv(paths.SOURCE_ROOT_ENV, raising=False)
    monkeypatch.delenv(settings.MODEL_ENV, raising=False)
    monkeypatch.delenv(settings.NUM_CTX_ENV, raising=False)
    # Port 9 (discard) is closed: any accidental model call fails fast.
    monkeypatch.setenv(settings.URL_ENV, "http://127.0.0.1:9")
    paths.set_source_root(None)
    settings.clear_overrides()
    yield
    paths.set_source_root(None)
    settings.clear_overrides()


@pytest.fixture
def fake_ollama(monkeypatch):
    server = FakeOllama(models=["qwen3:8b"])
    server.start()
    monkeypatch.setenv(settings.URL_ENV, server.url)
    yield server
    server.stop()
