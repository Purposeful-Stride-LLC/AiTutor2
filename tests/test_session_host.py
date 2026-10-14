"""`aitutor session` with the local model, and its offline fallback."""

import io

from aitutor.__main__ import main


def test_session_uses_ollama(fake_ollama, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("What is a pipe?\n/quit\n"))
    assert main(["session", "military-working-dog-fm3-19-17", "--week", "1", "--host", "ollama"]) == 0
    captured = capsys.readouterr()
    assert "Tutor says: What is a pipe?" in captured.out
    assert "local model qwen3:8b" in captured.err
    chat = fake_ollama.chats()[-1]
    assert chat["messages"][0]["role"] == "system"
    assert chat["messages"][-1] == {"role": "user", "content": "What is a pipe?"}


def test_session_falls_back_when_ollama_down(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("hello\n/quit\n"))
    assert main(["session", "military-working-dog-fm3-19-17", "--host", "ollama"]) == 0
    captured = capsys.readouterr()
    assert "offline" in captured.err.lower()
    assert "[AiTutor offline stub]" in captured.out


def test_session_auto_with_missing_model_explains(fake_ollama, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("/quit\n"))
    assert main(["session", "military-working-dog-fm3-19-17", "--model", "nope:1b"]) == 0
    assert "ollama pull nope:1b" in capsys.readouterr().err
