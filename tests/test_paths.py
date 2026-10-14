"""Portability: every location is resolved on the running machine."""

from pathlib import Path, PureWindowsPath

from aitutor import paths


def test_bundled_data_found_via_package():
    assert (paths.bundled_courses_dir() / "GZU_sample_syll.txt").is_file()
    assert (paths.bundled_built_dir() / "military-working-dog-fm3-19-17.json").is_file()
    assert (paths.prompts_dir() / "course_builder.md").is_file()
    assert (paths.bundled_source_roots_dir() / "roots.json").is_file()
    assert paths.bundled_courses_dir().is_relative_to(paths.package_dir())


def test_home_env_override(tmp_path):
    env = {"AITUTOR_HOME": str(tmp_path / "x")}
    assert paths.aitutor_home(env, "posix") == tmp_path / "x"
    assert paths.aitutor_home(env, "nt") == tmp_path / "x"


def test_home_default_windows_uses_appdata():
    home = paths.aitutor_home({"APPDATA": "E:\\Profiles\\someone\\AppData\\Roaming"}, "nt")
    assert home.name == "aitutor"
    assert "Roaming" in str(home)


def test_home_default_windows_without_appdata():
    home = paths.aitutor_home({}, "nt")
    assert home == Path.home() / "AppData" / "Roaming" / "aitutor"


def test_home_default_posix():
    assert paths.aitutor_home({}, "posix") == Path.home() / ".aitutor"


def test_source_root_precedence(tmp_path, monkeypatch):
    root, origin = paths.source_root()
    assert origin == "cwd" and root == Path.cwd()
    monkeypatch.setenv(paths.SOURCE_ROOT_ENV, str(tmp_path / "env"))
    assert paths.source_root() == (tmp_path / "env", "env")
    paths.set_source_root(tmp_path / "flag")
    assert paths.source_root() == (tmp_path / "flag", "flag")


def test_resolve_locator_token_forms(tmp_path):
    for loc in (
        "${SOURCE_ROOT}/Ebooks/a b.pdf",
        "$SOURCE_ROOT/Ebooks/a b.pdf",
        "%SOURCE_ROOT%\\Ebooks\\a b.pdf",
        "${SOURCE_ROOT}\\Ebooks/a b.pdf",
        "Ebooks/a b.pdf",
    ):
        assert paths.resolve_locator(loc, tmp_path) == tmp_path / "Ebooks" / "a b.pdf", loc


def test_resolve_locator_non_files(tmp_path):
    assert paths.resolve_locator("paste://parent-syllabus", tmp_path) is None
    assert paths.resolve_locator("https://example.org/x.pdf", tmp_path) is None
    assert paths.resolve_locator("", tmp_path) is None


def test_resolve_locator_absolute_kept(tmp_path):
    f = tmp_path / "abs.txt"
    assert paths.resolve_locator(str(f), Path("/elsewhere")) == f


def test_portable_locator(tmp_path):
    (tmp_path / "sub").mkdir()
    f = tmp_path / "sub" / "n.txt"
    f.write_text("x")
    assert paths.portable_locator(f, tmp_path) == "${SOURCE_ROOT}/sub/n.txt"
    other = tmp_path.parent / "outside.txt"
    assert paths.portable_locator(other, tmp_path) == other.resolve().as_posix()


def test_windows_style_locator_parts_are_split():
    # A locator authored on Windows resolves to the same parts on any OS.
    parts = paths._split_parts("\\Ebooks\\Sub\\b.pdf")
    assert parts == ["Ebooks", "Sub", "b.pdf"]
    assert PureWindowsPath("C:/root").joinpath(*parts) == PureWindowsPath("C:/root/Ebooks/Sub/b.pdf")


def test_input_file_relative_to_source_root_from_any_cwd(tmp_path, monkeypatch):
    shelf = tmp_path / "shelf"
    (shelf / "Sub Dir").mkdir(parents=True)
    f = shelf / "Sub Dir" / "notes-ü.txt"
    f.write_text("x", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for arg in ("Sub Dir/notes-ü.txt", "Sub Dir\\notes-ü.txt", "${SOURCE_ROOT}/Sub Dir/notes-ü.txt",
                "%SOURCE_ROOT%\\Sub Dir\\notes-ü.txt", str(f)):
        assert paths.resolve_input_file(arg, shelf) == f


def test_input_file_prefers_cwd_then_reports_both(tmp_path, monkeypatch):
    shelf = tmp_path / "shelf"
    shelf.mkdir()
    (shelf / "a.txt").write_text("root", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("cwd", encoding="utf-8")
    assert paths.resolve_input_file("a.txt", shelf) == tmp_path / "a.txt"
    try:
        paths.resolve_input_file("missing.txt", shelf)
    except FileNotFoundError as e:
        assert str(tmp_path / "missing.txt") in str(e) and str(shelf / "missing.txt") in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")
