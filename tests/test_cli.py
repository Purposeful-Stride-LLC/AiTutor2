"""CLI behaviour a fresh user depends on."""

import json

from aitutor import paths
from aitutor.__main__ import main
from aitutor.pipeline.course_store import list_built


def test_list_shows_bundled_courses(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    for cid in ("geology-aerospace", "military-working-dog-fm3-19-17"):
        assert cid in out


def test_start_prints_valid_json(capsys):
    assert main(["start", "military-working-dog-fm3-19-17", "--week", "1"]) == 0
    out = capsys.readouterr().out
    bundle = json.loads(out.split("--- prompt bundle (for host LLM) ---", 1)[1])
    assert bundle["course_id"] == "military-working-dog-fm3-19-17"


def test_unknown_course_is_a_clean_error(capsys):
    assert main(["show", "no-such-course"]) == 2
    assert "Unknown course_id" in capsys.readouterr().err


def test_import_goes_to_user_home_and_never_overwrites(tmp_path, capsys):
    reply = tmp_path / "reply.txt"
    reply.write_text(json.dumps({"course_id": "my-course", "title": "Mine",
                                 "weeks": [{"week": "1", "title": "a"}]}))
    assert main(["import-course", "--file", str(reply)]) == 0
    saved = paths.user_built_dir() / "my-course.json"
    assert saved.is_file()
    assert main(["import-course", "--file", str(reply)]) == 2  # exists
    assert main(["import-course", "--file", str(reply), "--force"]) == 0
    assert list(saved.parent.glob("my-course.json.bak-*"))
    assert {c.course_id: c.origin for c in list_built()}["my-course"] == "user"


def test_import_refuses_bundled_id(tmp_path):
    reply = tmp_path / "r.txt"
    reply.write_text(json.dumps({"course_id": "military-working-dog-fm3-19-17", "title": "X",
                                 "weeks": [{"week": "1", "title": "a"}]}))
    assert main(["import-course", "--file", str(reply)]) == 2
    assert not (paths.user_built_dir() / "military-working-dog-fm3-19-17.json").exists()


def test_build_stores_portable_locator(tmp_path):
    src = tmp_path / "src" / "notes"
    src.mkdir(parents=True)
    (src / "a.txt").write_text("Week 1: Intro")
    out = tmp_path / "pack.json"
    rc = main(["build", "--source-root", str(tmp_path / "src"), "--subject", "X",
               "--file", str(src / "a.txt"), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text())["sources"][0]["locator"] == "${SOURCE_ROOT}/notes/a.txt"


def test_verify_bundled_hashes_ok(capsys, tmp_path):
    assert main(["verify", "--source-root", str(tmp_path)]) == 0
    assert "MISMATCH" not in capsys.readouterr().out


def test_paths_command(capsys):
    assert main(["paths"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["source_root_source"] in {"cwd", "env", "flag"}
    assert info["user_built_courses"].endswith("built")


def test_build_with_source_root_from_another_dir(tmp_path, monkeypatch):
    shelf = tmp_path / "shelf"
    (shelf / "Unit 1").mkdir(parents=True)
    (shelf / "Unit 1" / "notes.txt").write_text("Week 1: pipes.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # not the shelf
    out = tmp_path / "pack.json"
    rc = main(["build", "--source-root", str(shelf), "--subject", "Shell",
               "--file", "Unit 1\\notes.txt", "--out", str(out)])
    assert rc == 0
    assert "${SOURCE_ROOT}/Unit 1/notes.txt" in out.read_text(encoding="utf-8")
