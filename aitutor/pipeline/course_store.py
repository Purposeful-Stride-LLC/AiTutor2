"""Persist model-built course JSON and load it for tutor/lecture.

Two locations, both resolved at run time (see ``aitutor.paths``):
- bundled courses shipped inside the package (read-only), and
- your imported courses in ``AITUTOR_HOME/courses/built`` (read-write).
Imports never write into the package or the repository checkout.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aitutor.paths import bundled_built_dir, user_built_dir
from aitutor.pipeline.provenance import attach_provenance


def built_dir() -> Path:
    """Where ``import-course`` writes: the per-user built-course directory."""
    return user_built_dir()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_course_json(text: str) -> dict[str, Any]:
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        return json.loads(m.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found in builder output")


def _slug(course_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", course_id.strip()).strip("-").lower()
    return s or "untitled"


def _read_json(path: Path) -> dict[str, Any]:
    # utf-8-sig tolerates a BOM added by Windows editors.
    return json.loads(path.read_text(encoding="utf-8-sig"))


@dataclass
class StoredCourse:
    path: Path
    data: dict[str, Any]
    origin: str = "user"  # bundled | user

    @property
    def course_id(self) -> str:
        return str(self.data.get("course_id") or self.path.stem)


def save_course(
    data: dict[str, Any],
    *,
    directory: Path | None = None,
    with_whi: bool = True,
    force: bool = False,
) -> StoredCourse:
    required = ("course_id", "title", "weeks")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Course JSON missing keys: {missing}")
    if not isinstance(data["weeks"], list) or not data["weeks"]:
        raise ValueError("Course JSON weeks must be a non-empty list")

    cid = _slug(str(data["course_id"]))
    data = dict(data)
    data["course_id"] = cid
    data = attach_provenance(data, with_whi=with_whi)

    if directory is None and not force and (bundled_built_dir() / f"{cid}.json").is_file():
        raise FileExistsError(
            f"'{cid}' is a bundled course id. Rename course_id, or pass --force "
            "to keep a personal copy that takes precedence."
        )
    d = directory or built_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{cid}.json"
    if path.exists():
        if not force:
            raise FileExistsError(
                f"{path} already exists. Pass --force to replace it (a backup is kept)."
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{stamp}"))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return StoredCourse(path=path, data=data, origin="user")


def save_from_llm_text(
    text: str,
    *,
    directory: Path | None = None,
    with_whi: bool = True,
    force: bool = False,
) -> StoredCourse:
    return save_course(
        extract_course_json(text), directory=directory, with_whi=with_whi, force=force
    )


def _search_dirs(directory: Path | None) -> list[tuple[Path, str]]:
    if directory is not None:
        return [(directory, "user")]
    # User copies first so a forced personal copy wins over the bundled one.
    return [(user_built_dir(), "user"), (bundled_built_dir(), "bundled")]


def load_course(course_id: str, *, directory: Path | None = None) -> StoredCourse:
    for d, origin in _search_dirs(directory):
        for name in (f"{_slug(course_id)}.json", f"{course_id}.json"):
            path = d / name
            if path.is_file():
                return StoredCourse(path=path, data=_read_json(path), origin=origin)
    raise KeyError(f"Unknown course_id: {course_id}")


def list_built(*, directory: Path | None = None) -> list[StoredCourse]:
    out: list[StoredCourse] = []
    seen: set[str] = set()
    for d, origin in _search_dirs(directory):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                stored = StoredCourse(path=p, data=_read_json(p), origin=origin)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if stored.course_id in seen:
                continue
            seen.add(stored.course_id)
            out.append(stored)
    return out
