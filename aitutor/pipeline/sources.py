"""Provenance registry — citations travel with every built course."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aitutor.paths import (
    bundled_source_roots_dir,
    resolve_locator,
    source_root,
    user_roots_file,
)
from aitutor.pipeline.ingest import IngestedMaterial


@dataclass
class SourceRecord:
    id: str
    title: str
    locator: str
    authority: str
    note: str = ""


@dataclass
class SourceRegistry:
    records: list[SourceRecord] = field(default_factory=list)

    def add_material(self, mat: IngestedMaterial, note: str = "") -> SourceRecord:
        # Stable S1, S2, … for prompt readability
        sid = f"S{len(self.records) + 1}"
        rec = SourceRecord(
            id=sid,
            title=mat.title,
            locator=mat.locator,
            authority=mat.authority_hint,
            note=note or mat.kind,
        )
        self.records.append(rec)
        return rec

    def as_prompt_block(self) -> str:
        lines = ["Sources (cite by id):"]
        for r in self.records:
            lines.append(
                f"- {r.id}: {r.title} [{r.authority}] locator={r.locator} ({r.note})"
            )
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps([asdict(r) for r in self.records], indent=2)

    def save(self, path: Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8")


def default_source_roots_file() -> Path:
    """Roots file in use: ``AITUTOR_HOME/roots.json`` if present, else the bundled example."""
    personal = user_roots_file()
    return personal if personal.is_file() else bundled_source_roots_dir() / "roots.json"


def load_source_roots(path: Path | None = None) -> dict:
    """Raw roots document (``{"description": ..., "roots": [...]}``)."""
    p = path or default_source_roots_file()
    if not p.is_file():
        return {"roots": []}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def resolved_source_roots(path: Path | None = None) -> dict:
    """Roots with each ``path`` resolved against this machine's source root."""
    doc = load_source_roots(path)
    root, origin = source_root()
    out = []
    for r in doc.get("roots", []):
        resolved = resolve_locator(r.get("path"), root)
        out.append(
            {
                **r,
                "resolved_path": str(resolved) if resolved else None,
                "exists": bool(resolved and resolved.exists()),
            }
        )
    return {
        "roots_file": str(path or default_source_roots_file()),
        "source_root": str(root),
        "source_root_source": origin,
        "roots": out,
    }
