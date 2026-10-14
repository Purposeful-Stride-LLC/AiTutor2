"""Adapt stored built-course JSON into LessonPlan / CourseMeta for session + lecture."""

from __future__ import annotations

from pathlib import Path

from aitutor.catalog import CourseMeta
from aitutor.lesson import LessonPlan, WeekUnit
from aitutor.pipeline.course_store import StoredCourse, load_course


def stored_to_plan(stored: StoredCourse) -> LessonPlan:
    data = stored.data
    meta = CourseMeta(
        course_id=str(data["course_id"]),
        title=str(data.get("title") or data["course_id"]),
        source_file=stored.path,
        tags=list(data.get("tags") or ["built"]),
        audience=str(data.get("audience") or "adult"),
        duration_hint=str(data.get("duration_hint") or ""),
    )
    weeks: list[WeekUnit] = []
    for w in data.get("weeks") or []:
        weeks.append(
            WeekUnit(
                week=str(w.get("week", len(weeks) + 1)),
                title=str(w.get("title") or f"Week {len(weeks)+1}"),
                objective=str(w.get("objective") or ""),
                topics=list(w.get("topics") or []),
                activity=str(w.get("activity") or ""),
            )
        )
    overview = str(data.get("goal") or data.get("tutor_notes") or "")
    # Keep source citations in raw_syllabus for prompt context
    sources = data.get("sources") or []
    src_lines = ["Sources:"] + [
        f"- {s.get('id')}: {s.get('title')} ({s.get('locator')})" for s in sources
    ]
    raw = overview + "\n\n" + "\n".join(src_lines) + "\n\n" + stored.path.read_text(
        encoding="utf-8-sig"
    )
    return LessonPlan(course=meta, overview=overview, weeks=weeks, raw_syllabus=raw)


def plan_from_built(course_id: str, *, directory: Path | None = None) -> LessonPlan:
    return stored_to_plan(load_course(course_id, directory=directory))