"""Optional NOVA lecture adapter — same plan, speakable delivery."""

from __future__ import annotations

from typing import Any

from aitutor.paths import prompts_dir

from aitutor.lesson import LessonPlan
from aitutor.professor import opening_message, system_prompt


def load_tutor_delivery_prompt() -> str:
    path = prompts_dir() / "tutor_delivery.md"
    return path.read_text(encoding="utf-8")


def lecture_payload(plan: LessonPlan, week: int | str | None = None) -> dict[str, Any]:
    """
    Bundle for NOVA (or any TTS/GUI lecturer):
    - system/delivery prompt
    - opening speakable lines
    - week unit fields
    """
    unit = plan.week(week) if week is not None else None
    speak = opening_message(plan, unit)
    return {
        "phase": "lecture",
        "module": "aitutor",
        "course_id": plan.course.course_id,
        "title": plan.course.title,
        "week": week,
        "system": load_tutor_delivery_prompt() + "\n\n" + system_prompt(plan, unit),
        "speak": speak,
        "unit": None
        if unit is None
        else {
            "week": unit.week,
            "title": unit.title,
            "objective": unit.objective,
            "topics": unit.topics,
            "activity": unit.activity,
        },
        "notes": (
            "NOVA should lecture from `speak` and `unit`, citing plan sources when present. "
            "Do not embed the full corpus in fieldkit — call AiTutor."
        ),
    }