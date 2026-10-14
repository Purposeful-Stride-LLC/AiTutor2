"""Lesson plan parsing from syllabus text or built course JSON."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aitutor.catalog import CourseCatalog, CourseMeta


@dataclass
class WeekUnit:
    week: int | str
    title: str
    objective: str = ""
    topics: list[str] = field(default_factory=list)
    activity: str = ""


@dataclass
class LessonPlan:
    course: CourseMeta
    overview: str
    weeks: list[WeekUnit]
    raw_syllabus: str

    def week(self, n: int | str) -> WeekUnit | None:
        key = str(n)
        for w in self.weeks:
            if str(w.week) == key:
                return w
        for w in self.weeks:
            if key in str(w.week):
                return w
        return None


_WEEK_RE = re.compile(
    r"(?mi)^(?:Week|Module|Part)\s+([\d\-–]+)\s*[:.\-–]\s*(.+)$"
)
_OBJ_RE = re.compile(r"(?mi)^\s*Objective:\s*(.+)$")
_ACT_RE = re.compile(r"(?mi)^\s*Activity:\s*(.+)$")


def parse_lesson_plan(course_id: str, catalog: CourseCatalog | None = None) -> LessonPlan:
    cat = catalog or CourseCatalog()
    meta = cat.get(course_id)
    if meta.kind == "built":
        from aitutor.lesson_from_built import plan_from_built

        return plan_from_built(course_id)

    raw = cat.raw_text(course_id)
    lines = raw.splitlines()

    overview_parts: list[str] = []
    weeks: list[WeekUnit] = []
    current: WeekUnit | None = None
    in_overview = False

    for line in lines:
        if re.search(r"(?i)^Course Overview", line):
            in_overview = True
            continue
        if re.search(r"(?i)^Syllabus Breakdown|^How This Course|^Part \d", line):
            in_overview = False

        wm = _WEEK_RE.match(line.strip())
        if wm:
            if current:
                weeks.append(current)
            current = WeekUnit(week=wm.group(1).strip(), title=wm.group(2).strip())
            in_overview = False
            continue

        if in_overview and line.strip():
            overview_parts.append(line.strip())
            continue

        if current is None:
            continue

        om = _OBJ_RE.match(line)
        if om:
            current.objective = om.group(1).strip()
            continue
        am = _ACT_RE.match(line)
        if am:
            current.activity = am.group(1).strip()
            continue
        if re.match(r"(?i)^\s*(Topics?|Focus|Activities?):\s*$", line):
            continue
        if re.match(r"^\s*[-•*]\s+", line) and current:
            topic = re.sub(r"^\s*[-•*]\s+", "", line).strip()
            if topic and not current.activity:
                current.topics.append(topic)

    if current:
        weeks.append(current)

    if not weeks:
        weeks.append(
            WeekUnit(
                week="1",
                title=meta.title,
                objective="Work through the syllabus with your tutor.",
                topics=[],
                activity="Open the session and ask questions.",
            )
        )

    overview = " ".join(overview_parts)[:1200]
    return LessonPlan(
        course=meta, overview=overview, weeks=weeks, raw_syllabus=raw
    )