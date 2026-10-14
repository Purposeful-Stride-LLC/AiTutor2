"""Ollama host adapter and settings, against a fake server (no network)."""

import pytest

from aitutor import llm_host, settings


def test_settings_precedence(monkeypatch, tmp_path):
    assert settings.resolve().model == settings.DEFAULT_MODEL
    settings.save_config({"model": "from-config"})
    assert settings.resolve().model == "from-config"
    monkeypatch.setenv(settings.MODEL_ENV, "from-env")
    assert settings.resolve().model == "from-env"
    settings.set_overrides(model="from-flag")
    s = settings.resolve()
    assert (s.model, s.origin["model"]) == ("from-flag", "flag")
    assert s.num_ctx == 8192


def test_url_without_scheme_is_accepted(monkeypatch):
    monkeypatch.setenv(settings.URL_ENV, "localhost:11434/")
    assert settings.resolve().url == "http://localhost:11434"


def test_unreachable_host_is_a_clean_error():
    with pytest.raises(llm_host.HostUnavailable) as e:
        llm_host.server_version(timeout=1)
    assert "aitutor setup" in str(e.value)


def test_chat_streams_hides_thinking_and_sends_ctx(fake_ollama):
    seen = []
    out = llm_host.chat([{"role": "user", "content": "hello"}], on_token=seen.append)
    assert out.startswith("Tutor says: hello") and "<think>" not in out
    body = fake_ollama.chats()[-1]
    assert body["think"] is False and body["options"]["num_ctx"] == 8192
    assert body["model"] == "qwen3:8b"


def test_missing_model_and_pull(fake_ollama):
    settings.set_overrides(model="tiny:1b")
    assert not llm_host.has_model()
    with pytest.raises(llm_host.ModelMissing):
        llm_host.chat([{"role": "user", "content": "x"}])
    events = []
    llm_host.pull("tiny:1b", on_progress=lambda st, c, t: events.append(st))
    assert events[-1] == "success" and llm_host.has_model()


def test_bundle_to_messages_maps_roles():
    msgs = llm_host.bundle_to_messages({"system": "S", "history": [
        {"role": "tutor", "content": "hi"}, {"role": "human", "content": "yo"}]})
    assert [m["role"] for m in msgs] == ["system", "assistant", "user"]


def test_think_filter_handles_split_tags():
    f = llm_host.ThinkFilter()
    pieces = ["Hi <th", "ink>secret</thi", "nk> there <", "b>"]
    shown = "".join(f.feed(p) for p in pieces) + f.flush()
    assert shown == "Hi  there <b>"
