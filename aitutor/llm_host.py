"""Local model host adapter (stdlib only). Talks to Ollama over HTTP.

Default server: http://127.0.0.1:11434, default model qwen3:8b, num_ctx 8192
(see ``aitutor.settings``). Every failure becomes one of the exceptions below
with a plain-language message, so callers can fall back instead of crashing.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable

from aitutor.settings import Settings, resolve


class HostError(RuntimeError):
    """The model host answered, but with an error."""


class HostUnavailable(HostError):
    """Nothing is listening at the configured Ollama URL."""


class ModelMissing(HostError):
    """Ollama is running but the configured model has not been pulled."""


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


class ThinkFilter:
    """Streaming filter that hides ``<think>...</think>`` even when tags are split."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._in = False

    def feed(self, piece: str) -> str:
        self._buf += piece
        out: list[str] = []
        while self._buf:
            tag = self.CLOSE if self._in else self.OPEN
            i = self._buf.find(tag)
            if i >= 0:
                if not self._in:
                    out.append(self._buf[:i])
                self._buf = self._buf[i + len(tag):]
                self._in = not self._in
                continue
            # Keep a possible partial tag at the end for the next piece.
            keep = 0
            for k in range(min(len(tag) - 1, len(self._buf)), 0, -1):
                if tag.startswith(self._buf[-k:]):
                    keep = k
                    break
            emit, self._buf = self._buf[: len(self._buf) - keep], self._buf[len(self._buf) - keep:]
            if not self._in:
                out.append(emit)
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = ("" if self._in else self._buf), ""
        return rest


def _open(settings: Settings, path: str, body: dict[str, Any] | None, timeout: float):
    url = f"{settings.url}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error", "")
        except (ValueError, OSError, AttributeError):
            pass
        if exc.code == 404 and "not found" in detail.lower():
            raise ModelMissing(
                f"Model '{body.get('model') if body else settings.model}' is not installed in Ollama. "
                f"Run: ollama pull {body.get('model') if body else settings.model}"
            ) from exc
        raise HostError(f"Ollama returned HTTP {exc.code} for {path}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise HostUnavailable(
            f"Ollama is not reachable at {settings.url} ({reason}). "
            "Start Ollama, or run `aitutor setup` for help."
        ) from exc


def _get_json(settings: Settings, path: str, timeout: float = 5.0) -> dict[str, Any]:
    with _open(settings, path, None, timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def server_version(settings: Settings | None = None, timeout: float = 3.0) -> str:
    s = settings or resolve()
    return str(_get_json(s, "/api/version", timeout).get("version", "unknown"))


def _norm(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def list_models(settings: Settings | None = None, timeout: float = 5.0) -> list[str]:
    s = settings or resolve()
    data = _get_json(s, "/api/tags", timeout)
    return sorted({str(m.get("name") or m.get("model")) for m in data.get("models", [])})


def has_model(settings: Settings | None = None, model: str | None = None) -> bool:
    s = settings or resolve()
    want = _norm(model or s.model)
    return want in {_norm(m) for m in list_models(s)}


def _iter_lines(resp) -> Iterable[dict[str, Any]]:
    for raw in resp:
        raw = raw.strip()
        if not raw:
            continue
        msg = json.loads(raw.decode("utf-8"))
        if msg.get("error"):
            raise HostError(f"Ollama error: {msg['error']}")
        yield msg


def chat(
    messages: list[dict[str, str]],
    settings: Settings | None = None,
    *,
    on_token: Callable[[str], None] | None = None,
    fmt: str | dict[str, Any] | None = None,
    temperature: float | None = None,
    timeout: float = 600.0,
) -> str:
    """One chat completion. Streams internally; ``on_token`` sees each piece.

    ``fmt`` is Ollama's ``format`` (``"json"`` or a JSON schema). Thinking is
    turned off (``think: false``) so qwen3-style models answer directly.
    """
    s = settings or resolve()
    options: dict[str, Any] = {"num_ctx": s.num_ctx}
    if temperature is not None:
        options["temperature"] = temperature
    body: dict[str, Any] = {
        "model": s.model,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": options,
    }
    if fmt is not None:
        body["format"] = fmt
    try:
        resp = _open(s, "/api/chat", body, timeout)
    except HostError as exc:
        # Older servers / non-thinking models may reject the think flag.
        if "think" not in str(exc).lower():
            raise
        body.pop("think")
        resp = _open(s, "/api/chat", body, timeout)
    parts: list[str] = []
    visible = ThinkFilter()
    started = False
    with resp:
        for msg in _iter_lines(resp):
            piece = (msg.get("message") or {}).get("content") or ""
            if piece:
                parts.append(piece)
                shown = visible.feed(piece)
                if not started:
                    shown = shown.lstrip()
                    started = bool(shown)
                if on_token and shown:
                    on_token(shown)
            if msg.get("done"):
                break
    tail = visible.flush()
    if on_token and tail:
        on_token(tail)
    return strip_thinking("".join(parts))


def pull(
    model: str,
    settings: Settings | None = None,
    *,
    on_progress: Callable[[str, int | None, int | None], None] | None = None,
    timeout: float = 3600.0,
) -> None:
    """Download a model through the Ollama API (same as ``ollama pull``)."""
    s = settings or resolve()
    with _open(s, "/api/pull", {"model": model, "stream": True}, timeout) as resp:
        for msg in _iter_lines(resp):
            if on_progress:
                on_progress(str(msg.get("status", "")), msg.get("completed"), msg.get("total"))


def bundle_to_messages(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """TutorSession.prompt_bundle() -> Ollama chat messages."""
    msgs = [{"role": "system", "content": bundle["system"]}]
    for t in bundle.get("history", []):
        role = "assistant" if t["role"] == "tutor" else "user"
        msgs.append({"role": role, "content": t["content"]})
    return msgs


def ollama_reply(
    bundle: dict[str, Any],
    settings: Settings | None = None,
    *,
    on_token: Callable[[str], None] | None = None,
) -> str:
    return chat(bundle_to_messages(bundle), settings, on_token=on_token)
