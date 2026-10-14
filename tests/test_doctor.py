"""Requirements check and guided setup."""

import json

from aitutor import doctor, settings
from aitutor.__main__ import main


def test_doctor_ready_with_model(fake_ollama, capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "[ok]  Ollama running: version 0.0.0-fake" in out
    assert "[ok]  Model qwen3:8b" in out and "Ready:" in out


def test_doctor_json_reports_missing_model(fake_ollama, capsys):
    assert main(["doctor", "--json", "--model", "llama3.2:3b"]) == 1
    data = json.loads(capsys.readouterr().out)
    model = next(c for c in data["checks"] if c["key"] == "model")
    assert model["status"] == "missing"
    assert model["fix"][0] == "ollama pull llama3.2:3b"
    assert "aitutor setup --model qwen3:8b" in model["fix"][1]  # suggests what's installed


def test_doctor_when_ollama_down_gives_os_commands(monkeypatch):
    monkeypatch.setattr(doctor, "find_ollama_binary", lambda: None)
    win = doctor.run_checks(os_name="Windows", gpu=False)
    inst = win.get("ollama_installed")
    assert inst.status == "missing" and inst.fix[0].startswith("winget install --id Ollama.Ollama")
    lin = doctor.run_checks(os_name="Linux", gpu=False)
    assert "install.sh" in lin.get("ollama_installed").fix[0]
    assert not lin.ready


def test_installed_but_stopped_offers_start(monkeypatch, tmp_path, capsys):
    fake_bin = tmp_path / "ollama"
    fake_bin.write_text("")
    monkeypatch.setattr(doctor, "find_ollama_binary", lambda: fake_bin)
    assert main(["setup"]) == 1  # no terminal in tests: offer is shown, not taken
    out = capsys.readouterr().out
    assert "Start it now?" in out and "skipped" in out
    assert "ollama serve" in out


def test_setup_yes_pulls_missing_model_and_saves_choice(fake_ollama, capsys):
    rc = main(["setup", "--yes", "--model", "tiny:1b"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Download the model tiny:1b now?" in out and "success" in out
    assert "tiny:1b" in fake_ollama.models
    assert settings.load_config()["model"] == "tiny:1b"
    assert settings.resolve().model == "tiny:1b"  # remembered for next runs
