"""Every filesystem location AiTutor uses, resolved on the machine it runs on.

Nothing in the repository stores a machine-specific path. There are three kinds
of location, and each is found at run time:

1. Bundled data (courses, prompts, example source-root layout) ships inside the
   ``aitutor`` package and is found with ``importlib.resources`` wherever the
   package is installed (a git checkout, a venv, site-packages; Windows or Linux).

2. User data (courses you import, an optional personal ``roots.json``) lives in
   ``AITUTOR_HOME``. Default: ``%APPDATA%\\aitutor`` on Windows,
   ``~/.aitutor`` elsewhere.

3. Your source material (books, manuals, notes) lives under a *source root* on
   your own disk. Course files refer to it as ``${SOURCE_ROOT}/relative/path``.
   The root is chosen per run: ``--source-root`` flag, then the
   ``AITUTOR_SOURCE_ROOT`` environment variable, then the current directory.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

HOME_ENV = "AITUTOR_HOME"
SOURCE_ROOT_ENV = "AITUTOR_SOURCE_ROOT"
SOURCE_ROOT_TOKEN = "${SOURCE_ROOT}"
_TOKENS = ("${SOURCE_ROOT}", "$SOURCE_ROOT", "%SOURCE_ROOT%")
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")

# --------------------------------------------------------------------------
# 1. Bundled, read-only package data


def package_dir() -> Path:
    """Directory of the installed ``aitutor`` package (any OS, any install)."""
    return Path(str(files("aitutor")))


def bundled_content_dir() -> Path:
    return package_dir() / "content"


def bundled_courses_dir() -> Path:
    return bundled_content_dir() / "courses"


def bundled_built_dir() -> Path:
    return bundled_courses_dir() / "built"


def bundled_source_roots_dir() -> Path:
    return bundled_content_dir() / "source_roots"


def prompts_dir() -> Path:
    return package_dir() / "prompts"


# --------------------------------------------------------------------------
# 2. Per-user data directory (AITUTOR_HOME)


def aitutor_home(
    environ: Mapping[str, str] | None = None, os_name: str | None = None
) -> Path:
    """User data dir: ``$AITUTOR_HOME``, else the OS default.

    ``environ``/``os_name`` exist so tests can simulate Windows on Linux and
    vice versa.
    """
    env = os.environ if environ is None else environ
    name = os.name if os_name is None else os_name
    override = env.get(HOME_ENV)
    if override:
        return Path(os.path.expanduser(override))
    if name == "nt":
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "aitutor"
    return Path.home() / ".aitutor"


def user_built_dir(home: Path | None = None) -> Path:
    return (home or aitutor_home()) / "courses" / "built"


def user_roots_file(home: Path | None = None) -> Path:
    return (home or aitutor_home()) / "roots.json"


# --------------------------------------------------------------------------
# 3. Source root and locators

_source_root_override: Path | None = None


def set_source_root(path: str | os.PathLike[str] | None) -> None:
    """Set the source root for this process (used by ``--source-root``)."""
    global _source_root_override
    _source_root_override = (
        None if path is None else Path(os.path.expanduser(os.fspath(path)))
    )


def source_root(environ: Mapping[str, str] | None = None) -> tuple[Path, str]:
    """Return ``(root, origin)``. ``origin`` is ``flag``, ``env`` or ``cwd``."""
    if _source_root_override is not None:
        return _source_root_override, "flag"
    env = os.environ if environ is None else environ
    value = env.get(SOURCE_ROOT_ENV)
    if value:
        return Path(os.path.expanduser(value)), "env"
    return Path.cwd(), "cwd"


def course_roots_file(home: Path | None = None) -> Path:
    """Per-machine memory of which folder each built course came from."""
    return (home or aitutor_home()) / "course_roots.json"


def _load_course_roots() -> dict[str, str]:
    import json

    try:
        data = json.loads(course_roots_file().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_course_root(course_id: str, root: Path) -> None:
    """Record where ``${SOURCE_ROOT}`` pointed when a course was built here.

    Stored in AITUTOR_HOME (this machine only), never in the course file, so
    the course itself stays portable.
    """
    import json

    data = _load_course_roots()
    data[course_id] = str(Path(root).expanduser().resolve())
    f = course_roots_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def course_source_root(course_id: str | None) -> tuple[Path, str]:
    """Source root for one course: flag > env > remembered for this course > cwd."""
    root, origin = source_root()
    if origin != "cwd" or not course_id:
        return root, origin
    remembered = _load_course_roots().get(course_id)
    if remembered:
        return Path(remembered), "course"
    return root, origin


def source_root_note(origin: str, root: Path) -> str:
    if origin == "cwd":
        return (
            f"note: {SOURCE_ROOT_ENV} is not set and --source-root was not given; "
            f"using the current directory as the source root: {root}"
        )
    if origin == "course":
        return f"source root (remembered for this course on this machine): {root}"
    return f"source root ({origin}): {root}"


def _split_parts(rest: str) -> list[str]:
    return [p for p in re.split(r"[\\/]+", rest) if p and p != "."]


def resolve_locator(locator: str | None, root: Path | None = None) -> Path | None:
    """Turn a stored locator into a path on *this* machine.

    - ``${SOURCE_ROOT}/a/b.pdf`` (also ``$SOURCE_ROOT``, ``%SOURCE_ROOT%``) ->
      ``<source root>/a/b.pdf``. Forward or back slashes both work.
    - ``paste://...``, ``http(s)://...`` and other URLs -> ``None`` (not a file).
    - A relative path -> resolved against the source root.
    - An absolute path -> used as-is after ``~`` / env-var expansion.
    """
    if not locator:
        return None
    loc = str(locator).strip()
    if _URL_RE.match(loc):
        return None
    base = root if root is not None else source_root()[0]
    for tok in _TOKENS:
        if loc.startswith(tok):
            return base.joinpath(*_split_parts(loc[len(tok):]))
    expanded = os.path.expandvars(os.path.expanduser(loc))
    p = Path(expanded)
    if p.is_absolute():
        return p
    return base.joinpath(*_split_parts(expanded))


def _input_candidates(text: str, base: Path) -> list[Path]:
    if any(text.startswith(tok) for tok in _TOKENS):
        cand = resolve_locator(text, base)
        return [cand] if cand is not None else []
    expanded = os.path.expandvars(os.path.expanduser(text))
    p = Path(expanded)
    if p.is_absolute():
        return [p]
    tried = [Path.cwd().joinpath(*_split_parts(expanded))]
    under_root = base.joinpath(*_split_parts(expanded))
    if under_root not in tried:
        tried.append(under_root)
    return tried


def resolve_input_file(arg: str | os.PathLike[str], root: Path | None = None) -> Path:
    """Find a source file named on the command line (``build --file/--paste``).

    Accepts an absolute path, a ``${SOURCE_ROOT}/...`` locator, or a relative
    path. A relative path is tried against the current directory first, then
    under the source root, so ``--source-root ~/Books --file Physics/ch1.txt``
    works from any directory. ``/`` and ``\\`` are both accepted.
    Raises ``FileNotFoundError`` naming every place that was tried.
    """
    text = str(arg).strip()
    tried = _input_candidates(text, root if root is not None else source_root()[0])
    for cand in tried:
        if cand.is_file():
            return cand
    where = " or ".join(str(c) for c in tried)
    raise FileNotFoundError(f"No such file: {text} (looked for {where})")


def resolve_input_path(arg: str | os.PathLike[str], root: Path | None = None) -> Path:
    """Like :func:`resolve_input_file` but a folder is accepted too (``--source``)."""
    text = str(arg).strip()
    tried = _input_candidates(text, root if root is not None else source_root()[0])
    for cand in tried:
        if cand.exists():
            return cand
    where = " or ".join(str(c) for c in tried)
    raise FileNotFoundError(f"No such file or folder: {text} (looked for {where})")


def portable_locator(path: str | os.PathLike[str], root: Path | None = None) -> str:
    """Store a file path portably: ``${SOURCE_ROOT}/rel`` when under the root.

    Files outside the source root keep their absolute path (POSIX-style
    slashes). That path is only meaningful on this machine, so set a source
    root to make courses portable.
    """
    p = Path(path).expanduser().resolve()
    base = (root if root is not None else source_root()[0]).expanduser().resolve()
    try:
        rel = p.relative_to(base)
    except ValueError:
        return p.as_posix()
    rel_posix = rel.as_posix()
    return SOURCE_ROOT_TOKEN if rel_posix in ("", ".") else f"{SOURCE_ROOT_TOKEN}/{rel_posix}"


def describe() -> dict[str, str]:
    """Resolved locations for ``aitutor paths`` (diagnostics)."""
    root, origin = source_root()
    home = aitutor_home()
    roots_file = user_roots_file(home)
    return {
        "package_dir": str(package_dir()),
        "bundled_courses": str(bundled_courses_dir()),
        "prompts": str(prompts_dir()),
        "aitutor_home": str(home),
        "aitutor_home_source": "env" if os.environ.get(HOME_ENV) else "default",
        "user_built_courses": str(user_built_dir(home)),
        "source_root": str(root),
        "source_root_source": origin,
        "course_roots_file": str(course_roots_file(home)),
        "config_file": str(home / "config.json"),
        "roots_file": str(
            roots_file if roots_file.is_file() else bundled_source_roots_dir() / "roots.json"
        ),
    }
