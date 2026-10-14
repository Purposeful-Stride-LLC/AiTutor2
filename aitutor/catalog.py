"""Course catalog: baked AD_ASTRA texts + LLM-built JSON courses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from aitutor.paths import bundled_courses_dir
from aitutor.pipeline.course_store import list_built


def default_content_dir() -> Path:
    """Bundled baked-course texts, found wherever the package is installed."""
    return bundled_courses_dir()


@dataclass
class CourseMeta:
    course_id: str
    title: str
    source_file: Path
    tags: list[str] = field(default_factory=list)
    audience: str = "adult"
    duration_hint: str = ""
    kind: str = "baked"  # baked | built


COURSE_INDEX: dict[str, dict] = {
    "geology-aerospace": {
        "file": "GZU_sample_syll.txt",
        "title": "From Geology to Aerospace",
        "tags": ["gzu", "aerospace", "adult", "retraining"],
        "audience": "adult",
    },
    "nasa-modeling": {
        "file": "GZsyllabus_NASA_modeling.txt",
        "title": "NASA Modeling Standards and APIs",
        "tags": ["nasa", "modeling", "apis", "adult"],
        "audience": "adult",
    },
    "little-explorers": {
        "file": "lil_explorers_syllabus.txt",
        "title": "Little Explorers (ages 5–6)",
        "tags": ["k12", "voice", "norwegian"],
        "audience": "child",
    },
    "ad-astra-series": {
        "file": "ad_astra_series.txt",
        "title": "Ad Astra Series",
        "tags": ["media", "series"],
        "audience": "mixed",
    },
    "ad-astra-kids-tosca": {
        "file": "ad_astra_kids_tosca.txt",
        "title": "Ad Astra Kids / Tosca",
        "tags": ["k12", "series"],
        "audience": "child",
    },
    "xtv-little-explorers": {
        "file": "xtv_little_explorers_series.txt",
        "title": "XTV Little Explorers Series",
        "tags": ["k12", "media"],
        "audience": "child",
    },
    "gzu-system-awareness": {
        "file": "gzu_systemawareness.txt",
        "title": "GZU System Awareness",
        "tags": ["gzu", "systems"],
        "audience": "adult",
    },
    "xzone-online-offline": {
        "file": "grokXzoneuni_ol_ofl.txt",
        "title": "XZone University Online + Offline",
        "tags": ["gzu", "makerspace"],
        "audience": "adult",
    },
}


@dataclass
class CourseCatalog:
    content_dir: Path = field(default_factory=default_content_dir)

    def list(self) -> list[CourseMeta]:
        out: list[CourseMeta] = []
        for cid, info in COURSE_INDEX.items():
            path = self.content_dir / info["file"]
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            dur = ""
            m = re.search(r"Duration:\s*(.+)", text)
            if m:
                dur = m.group(1).strip()
            out.append(
                CourseMeta(
                    course_id=cid,
                    title=info["title"],
                    source_file=path,
                    tags=list(info["tags"]),
                    audience=info["audience"],
                    duration_hint=dur,
                    kind="baked",
                )
            )
        for stored in list_built():
            data = stored.data
            out.append(
                CourseMeta(
                    course_id=stored.course_id,
                    title=str(data.get("title") or stored.course_id),
                    source_file=stored.path,
                    tags=list(data.get("tags") or ["built"]),
                    audience=str(data.get("audience") or "adult"),
                    duration_hint=str(data.get("duration_hint") or ""),
                    kind="built",
                )
            )
        return out

    def get(self, course_id: str) -> CourseMeta:
        for c in self.list():
            if c.course_id == course_id:
                return c
        raise KeyError(f"Unknown course_id: {course_id}")

    def raw_text(self, course_id: str) -> str:
        meta = self.get(course_id)
        return meta.source_file.read_text(encoding="utf-8-sig", errors="replace")

    def is_built(self, course_id: str) -> bool:
        try:
            return self.get(course_id).kind == "built"
        except KeyError:
            return False


def list_courses(content_dir: Path | None = None) -> list[CourseMeta]:
    cat = CourseCatalog(content_dir or default_content_dir())
    return cat.list()