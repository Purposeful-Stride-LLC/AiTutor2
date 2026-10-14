"""Cite + content hash + optional WHI header for built courses (NOVA paper shape)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aitutor.paths import resolve_locator


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        if max_bytes is None:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        else:
            remaining = max_bytes
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                h.update(chunk)
                remaining -= len(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cite_record(
    *,
    source_id: str,
    title: str,
    locator: str,
    authority: str = "primary",
    note: str = "",
    content_sha256: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    digest = content_sha256
    if digest is None and path is not None and path.is_file():
        digest = sha256_file(path)
    return {
        "id": source_id,
        "title": title,
        "locator": locator,
        "authority": authority,
        "note": note,
        "sha256": digest,
    }


def whi_header(
    *,
    course_id: str,
    title: str,
    kind: str = "0x-DOC",
    cites: list[str] | None = None,
) -> dict[str, Any]:
    """Optional WHI-shaped stamp — thin, not a palace join."""
    return {
        "kind": kind,
        "code_hint": "0x-DOC",
        "course_id": course_id,
        "title": title,
        "cites": cites or [],
        "stamped_zulu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Optional WHI header for NOVA ingest; AiTutor stays standalone.",
    }


def course_content_hash(course: dict[str, Any]) -> str:
    """SHA-256 of the canonical course body (everything except provenance/WHI)."""
    body = {k: v for k, v in course.items() if k not in ("provenance", "WHI")}
    return sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))


def attach_provenance(course: dict[str, Any], *, with_whi: bool = True) -> dict[str, Any]:
    """Ensure sources have sha256; add course content hash + optional WHI."""
    data = dict(course)
    sources = list(data.get("sources") or [])
    normalized = []
    for i, s in enumerate(sources, start=1):
        s = dict(s)
        sid = s.get("id") or f"S{i}"
        s["id"] = sid
        loc = s.get("locator") or ""
        if not s.get("sha256") and loc:
            p = resolve_locator(str(loc))
            if p is not None and p.is_file():
                s["sha256"] = sha256_file(p)
        normalized.append(s)
    data["sources"] = normalized

    # Stable body hash over canonical JSON without provenance block
    course_hash = course_content_hash(data)
    data["provenance"] = {
        "schema": "aitutor.course.v1",
        "content_sha256": course_hash,
        "cite_count": len(normalized),
        "hashed_zulu": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if with_whi:
        data["WHI"] = whi_header(
            course_id=str(data.get("course_id") or "untitled"),
            title=str(data.get("title") or ""),
            cites=[s["id"] for s in normalized],
        )
    return data