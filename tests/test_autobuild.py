"""Build a course from a folder of material with the (fake) local model."""

import json

from aitutor import paths
from aitutor.__main__ import main
from aitutor.pipeline.course_store import load_course
from aitutor.pipeline.ingest import scan_folder, smart_excerpt
from material import SHELL_TEXT


def _shelf(tmp_path):
    shelf = tmp_path / "My Shelf"
    (shelf / "notes").mkdir(parents=True)
    (shelf / "notes" / "pipes.md").write_text(SHELL_TEXT, encoding="utf-8")
    (shelf / "syllabus.txt").write_text("Week 1: Pipes\nWeek 2: grep\n", encoding="utf-8")
    (shelf / "image.png").write_bytes(b"\x89PNG")
    (shelf / ".hidden").mkdir()
    (shelf / ".hidden" / "x.txt").write_text("secret", encoding="utf-8")
    return shelf


def test_scan_folder_picks_text_and_skips_hidden(tmp_path):
    scan = scan_folder(_shelf(tmp_path))
    names = [p.name for p in scan.files]
    assert names == ["pipes.md", "syllabus.txt"]


def test_smart_excerpt_fits_budget_and_keeps_outline():
    text = "Chapter 1 Start\n" + "a " * 5000 + "\nChapter 9 End\n" + "b " * 5000
    out = smart_excerpt(text, 1500)
    assert len(out) <= 1540 and "Chapter 9 End" in out


def test_build_folder_with_model_and_import(tmp_path, fake_ollama, monkeypatch, capsys):
    shelf = _shelf(tmp_path)
    monkeypatch.chdir(tmp_path)  # cwd is not the shelf
    rc = main(["build", "--source", str(shelf), "--host", "ollama", "--import", "--subject", "Shell"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "saved fake-course" in out
    c = load_course("fake-course").data
    # Sources come from what was ingested, never from the model.
    assert [s["locator"] for s in c["sources"]] == [
        "${SOURCE_ROOT}/notes/pipes.md", "${SOURCE_ROOT}/syllabus.txt"]
    assert all("S99" not in w["source_ids"] for w in c["weeks"])
    assert any("Invented Manual" in g for g in c["gaps"])
    assert c["built_with"]["model"] == "qwen3:8b"
    # The folder is remembered for this course on this machine only.
    root, origin = paths.course_source_root("fake-course")
    assert (root, origin) == (shelf.resolve(), "course")
    assert str(shelf) not in json.dumps(c)
    # Schema-constrained request
    assert isinstance(fake_ollama.chats()[-1]["format"], dict)
    # A second build gets a fresh id instead of overwriting.
    assert main(["build", "--source", str(shelf), "--host", "ollama", "--import"]) == 0
    assert "saved fake-course-2" in capsys.readouterr().out


def test_build_without_import_prints_json(tmp_path, fake_ollama, capsys):
    shelf = _shelf(tmp_path)
    assert main(["build", "--source", str(shelf), "--host", "ollama"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["course_id"] == "fake-course"
    assert not (paths.user_built_dir() / "fake-course.json").exists()


def test_build_when_ollama_down_is_clean(tmp_path, capsys):
    shelf = _shelf(tmp_path)
    assert main(["build", "--source", str(shelf), "--host", "ollama", "--import"]) == 3
    assert "not reachable" in capsys.readouterr().err


def test_import_flag_requires_model_host(capsys):
    assert main(["build", "--subject", "x", "--import"]) == 2
