"""Model-host settings: which Ollama server and model AiTutor talks to.

Precedence (highest first): command-line flag (``--model``, ``--ollama-url``),
environment (``AITUTOR_MODEL``, ``AITUTOR_OLLAMA_URL``, ``AITUTOR_NUM_CTX``),
``AITUTOR_HOME/config.json`` (written by ``aitutor setup --model ...``),
then the defaults below. Nothing here is machine-specific.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from aitutor.paths import aitutor_home

DEFAULT_URL = "http://127.0.0.1:11434"
# Fits an 8 GB GPU with num_ctx 8192 (about 4.9 GB weights + ~1.2 GB KV cache).
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_NUM_CTX = 8192

MODEL_ENV = "AITUTOR_MODEL"
URL_ENV = "AITUTOR_OLLAMA_URL"
NUM_CTX_ENV = "AITUTOR_NUM_CTX"

_overrides: dict[str, Any] = {}


@dataclass(frozen=True)
class Settings:
    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    num_ctx: int = DEFAULT_NUM_CTX
    origin: Mapping[str, str] = field(default_factory=dict)  # field -> flag|env|config|default


def config_file(home: Path | None = None) -> Path:
    return (home or aitutor_home()) / "config.json"


def load_config(home: Path | None = None) -> dict[str, Any]:
    p = config_file(home)
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(updates: Mapping[str, Any], home: Path | None = None) -> Path:
    data = load_config(home)
    data.update({k: v for k, v in updates.items() if v is not None})
    p = config_file(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def set_overrides(*, model: str | None = None, url: str | None = None, num_ctx: int | None = None) -> None:
    """Called by the CLI for ``--model`` / ``--ollama-url`` / ``--num-ctx``."""
    for key, val in (("model", model), ("url", url), ("num_ctx", num_ctx)):
        if val:
            _overrides[key] = val
        else:
            _overrides.pop(key, None)


def clear_overrides() -> None:
    _overrides.clear()


def resolve(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    cfg = load_config()
    values: dict[str, Any] = {}
    origin: dict[str, str] = {}
    for key, env_name, default in (
        ("url", URL_ENV, DEFAULT_URL),
        ("model", MODEL_ENV, DEFAULT_MODEL),
        ("num_ctx", NUM_CTX_ENV, DEFAULT_NUM_CTX),
    ):
        if _overrides.get(key):
            values[key], origin[key] = _overrides[key], "flag"
        elif env.get(env_name):
            values[key], origin[key] = env[env_name], "env"
        elif cfg.get(key):
            values[key], origin[key] = cfg[key], "config"
        else:
            values[key], origin[key] = default, "default"
    url = str(values["url"]).strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    try:
        num_ctx = max(2048, int(values["num_ctx"]))
    except (TypeError, ValueError):
        num_ctx, origin["num_ctx"] = DEFAULT_NUM_CTX, "default"
    return Settings(url=url, model=str(values["model"]).strip(), num_ctx=num_ctx, origin=origin)
