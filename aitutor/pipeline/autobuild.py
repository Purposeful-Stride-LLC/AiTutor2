"""Build a course from source material with the local model, then save it.

material -> prompt pack -> Ollama (JSON-schema constrained) -> normalized,
cited course JSON in AITUTOR_HOME. The model never invents locators: sources
are always rewritten from what was actually ingested.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aitutor import __version__, llm_host, paths
from aitutor.paths import bundled_built_dir, user_built_dir
from aitutor.pipeline.builder import BuildRequest, build_prompt_pack
from aitutor.pipeline.course_store import StoredCourse, _slug, extract_course_json, save_course
from aitutor.pipeline.support import (
    SourceAssessment, assess_sources, supporting_sources, unit_budget, unsupported_units)
from aitutor.settings import Settings, resolve

COURSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "course_id": {"type": "string"},
        "title": {"type": "string"},
        "audience": {"type": "string", "enum": ["child", "adult", "mixed"]},
        "goal": {"type": "string"},
        "duration_hint": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "authority": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["id", "title"],
            },
        },
        "weeks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "week": {"type": "string"},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "activity": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "assessment": {"type": "string"},
                },
                "required": ["week", "title", "objective", "topics", "activity", "source_ids", "assessment"],
            },
        },
        "gaps": {"type": "array", "items": {"type": "string"}},
        "tutor_notes": {"type": "string"},
    },
    "required": ["course_id", "title", "audience", "goal", "duration_hint", "sources", "weeks", "gaps", "tutor_notes"],
}

# Rough size model: ~3.2 characters per token for English prose and JSON.
CHARS_PER_TOKEN = 3.2
OUTPUT_RESERVE_TOKENS = 2600


def excerpt_budget_for(settings: Settings, system_chars: int, header_chars: int = 1500) -> int:
    usable = (settings.num_ctx - OUTPUT_RESERVE_TOKENS) * CHARS_PER_TOKEN
    return max(1500, int(usable - system_chars - header_chars))


@dataclass
class BuildResult:
    stored: StoredCourse
    raw_reply: str
    warnings: list[str] = field(default_factory=list)
    prompt_chars: int = 0


class WeakSourceError(ValueError):
    """The material looks too thin, unreadable or off-subject; ask before building."""

    def __init__(self, assessment: SourceAssessment):
        self.assessment = assessment
        super().__init__("This material may not support a course: " + assessment.message())


class UnsupportedCourseError(ValueError):
    """Every unit the model planned is missing from the material."""


def check_sources(req: BuildRequest) -> SourceAssessment:
    return assess_sources([m.text for m in req.materials], req.subject if req.subject_given else "")


def _unique_id(cid: str) -> str:
    def taken(c: str) -> bool:
        return (user_built_dir() / f"{c}.json").exists() or (bundled_built_dir() / f"{c}.json").exists()

    if not taken(cid):
        return cid
    n = 2
    while taken(f"{cid}-{n}"):
        n += 1
    return f"{cid}-{n}"


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [x.strip() for x in re.split(r"[;\n]", v) if x.strip()]
    return []


def normalize_course(
    data: dict[str, Any], pack: dict[str, Any], req: BuildRequest, settings: Settings
) -> tuple[dict[str, Any], list[str]]:
    """Make a model's course JSON safe to store: real sources, valid ids, all fields."""
    if not isinstance(data, dict):
        raise ValueError(
            f"The model replied with a JSON {type(data).__name__}, not a course object. "
            "Try again, or use a larger model.")
    warnings: list[str] = []
    registry = {r["id"]: r for r in pack["sources"]}
    raw_sources = data.get("sources")
    model_sources = {str(s.get("id")): s for s in (raw_sources if isinstance(raw_sources, list) else [])
                     if isinstance(s, dict)}
    sources = []
    for sid, rec in registry.items():
        ms = model_sources.get(sid) or {}
        note = str(ms.get("note") or rec.get("note") or "")
        # The model has read the excerpt; trust its primary/secondary call.
        authority = str(ms.get("authority") or "").lower()
        if authority not in ("primary", "secondary"):
            authority = rec.get("authority") or "secondary"
        sources.append(
            {
                "id": sid,
                "title": rec["title"],
                "locator": rec["locator"],
                "authority": authority,
                "note": note,
            }
        )
    gaps = _as_list(data.get("gaps"))
    for sid, s in model_sources.items():
        if sid not in registry and s.get("title"):
            gaps.append(f"Suggested source (not provided): {s.get('title')}")
            warnings.append(f"model cited a source that was not provided: {s.get('title')}")

    weeks = []
    raw_weeks = data.get("weeks")
    for i, w in enumerate(raw_weeks if isinstance(raw_weeks, list) else [], start=1):
        if not isinstance(w, dict):
            continue
        ids = [x for x in _as_list(w.get("source_ids")) if x in registry]
        if not ids and len(registry) == 1:
            ids = list(registry)
        weeks.append(
            {
                "week": str(w.get("week") or i).strip() or str(i),
                "title": str(w.get("title") or f"Unit {i}").strip(),
                "objective": str(w.get("objective") or "").strip(),
                "topics": _as_list(w.get("topics")),
                "activity": str(w.get("activity") or "").strip(),
                "source_ids": ids,
                "assessment": str(w.get("assessment") or "").strip(),
            }
        )
    if not weeks:
        raise ValueError("The model's reply had no usable weeks/units. Try again or use a larger model.")

    # Units the cited material does not support go to gaps, not into the course.
    texts = {r["id"]: m.text for r, m in zip(pack["sources"], req.materials)}
    if texts:
        bad = set()
        recited = []
        for i in unsupported_units(weeks, texts):
            # Supported by another provided file? Then the citation was wrong, not the unit.
            better = supporting_sources(weeks[i], texts) if len(texts) > 1 else []
            if better:
                weeks[i]["source_ids"] = better
                recited.append(f"{weeks[i]['title']} -> {', '.join(better)}")
            else:
                bad.add(i)
        if recited:
            warnings.append("corrected citations for: " + "; ".join(recited))
        for i in sorted(bad):
            w = weeks[i]
            what = f" ({', '.join(w['topics'][:4])})" if w["topics"] else ""
            gaps.append(f"Not in your sources: {w['title']}{what}")
        if bad:
            warnings.append(
                f"moved {len(bad)} unit(s) to gaps because your material does not cover them: "
                + "; ".join(weeks[i]["title"] for i in sorted(bad)))
        weeks = [w for i, w in enumerate(weeks) if i not in bad]
        if not [w for w in weeks if not _is_scaffold(w)]:
            raise UnsupportedCourseError(
                f"Your material does not contain enough about \u201c{req.subject}\u201d to teach from. "
                "Missing: " + ("; ".join(gaps[:6]) or "usable source text") + ". Add better material and build again.")
        for n, w in enumerate(weeks, start=1):
            if w["week"].isdigit():
                w["week"] = str(n)
    for hit in pack.get("injection") or []:
        warnings.append(f"{hit['source_id']} ({hit['title']}): removed instruction-like text aimed at AI tools: "
                        f"\u201c{hit['text'][:100]}\u201d")
    uncited = [w["week"] for w in weeks if not w["source_ids"]]
    if uncited and registry:
        warnings.append(f"units without a valid source citation: {', '.join(uncited)}")

    title = str(data.get("title") or req.subject).strip() or req.subject
    audience = str(data.get("audience") or req.audience)
    if audience not in ("child", "adult", "mixed"):
        audience = req.audience
    course = {
        "course_id": _slug(str(data.get("course_id") or title)).replace("_", "-"),
        "title": title,
        "audience": audience,
        "goal": str(data.get("goal") or req.goal).strip(),
        "duration_hint": str(data.get("duration_hint") or f"{len(weeks)} units, self-paced").strip(),
        "sources": sources,
        "weeks": weeks,
        "gaps": gaps,
        "tutor_notes": str(data.get("tutor_notes") or "").strip(),
        "tags": ["built", "local-model"],
        "built_with": {"host": "ollama", "model": settings.model, "num_ctx": settings.num_ctx, "aitutor": __version__},
    }
    return course, warnings


def _is_scaffold(w: dict) -> bool:
    from aitutor.pipeline.support import SCAFFOLD

    return bool(SCAFFOLD.search(w.get("title") or ""))


def build_course(
    req: BuildRequest,
    settings: Settings | None = None,
    *,
    on_token: Callable[[str], None] | None = None,
    force: bool = False,
    course_id: str | None = None,
    save: bool = True,
    anyway: bool = False,
) -> BuildResult:
    """Ask the local model to build ``req`` into a course (and save it unless ``save=False``).

    Raises ``WeakSourceError`` when the material looks too thin, unreadable or off-subject,
    unless ``anyway=True`` (the user confirmed "build anyway").
    """
    s = settings or resolve()
    if not req.materials:
        raise ValueError("No source material to build from.")
    assessment = check_sources(req)
    if not assessment.ok and not anyway:
        raise WeakSourceError(assessment)
    probe = build_prompt_pack(req, excerpt_budget=2000)
    budget = excerpt_budget_for(s, len(probe["system"]))
    pack = build_prompt_pack(req, excerpt_budget=budget)
    chars = sum(len(m.text) for m in req.materials)
    most = unit_budget(chars)
    units_hint = (
        f"\n\nThe material is about {chars:,} characters, enough for at most {most} unit(s): "
        f"plan between 1 and {most} units. "
        "Every unit must list source_ids from the Sources list. "
        "The learner studies alone with an AI tutor in a text chat: each activity must be "
        "something they can do and paste back as text, and each assessment must be "
        "something the tutor can check from that text (no peers, no instructor grading). "
        "Reply with the JSON object only."
    )
    messages = [
        {"role": "system", "content": pack["system"]},
        {"role": "user", "content": pack["user"] + units_hint},
    ]
    reply = llm_host.chat(messages, s, on_token=on_token, fmt=COURSE_SCHEMA, temperature=0.3)
    try:
        data = json.loads(reply)
    except ValueError:
        data = extract_course_json(reply)
    course, warnings = normalize_course(data, pack, req, s)
    if not assessment.ok:
        warnings.insert(0, "built anyway although: " + assessment.message())
    if course_id:
        course["course_id"] = _slug(course_id)
    if not force:
        course["course_id"] = _unique_id(course["course_id"])
    if not save:
        stored = StoredCourse(path=Path(f"{course['course_id']}.json"), data=course, origin="unsaved")
        return BuildResult(stored=stored, raw_reply=reply, warnings=warnings,
                           prompt_chars=len(pack["system"]) + len(pack["user"]))
    stored = save_course(course, force=force)
    root, origin = paths.source_root()
    if any(str(x["locator"]).startswith(paths.SOURCE_ROOT_TOKEN) for x in course["sources"]):
        paths.remember_course_root(stored.course_id, root)
    return BuildResult(
        stored=stored,
        raw_reply=reply,
        warnings=warnings,
        prompt_chars=len(pack["system"]) + len(pack["user"]),
    )


def source_root_for(path: Path) -> Path:
    """Sensible ${SOURCE_ROOT} when the user picks a file or folder."""
    p = Path(path).expanduser().resolve()
    return p if p.is_dir() else p.parent
