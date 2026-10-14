"""Human tutoring session — lesson plan + professor prompt + turn log."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aitutor.catalog import CourseCatalog
from aitutor.lesson import LessonPlan, parse_lesson_plan
from aitutor.professor import opening_message, system_prompt


@dataclass
class Turn:
    role: str  # "tutor" | "human" | "system"
    content: str
    at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class TutorSession:
    plan: LessonPlan
    week: int | str | None = None
    learner_name: str = "learner"
    turns: list[Turn] = field(default_factory=list)

    @classmethod
    def start(
        cls,
        course_id: str,
        week: int | str | None = None,
        *,
        learner_name: str = "learner",
        catalog: CourseCatalog | None = None,
    ) -> "TutorSession":
        plan = parse_lesson_plan(course_id, catalog)
        session = cls(plan=plan, week=week, learner_name=learner_name)
        unit = plan.week(week) if week is not None else None
        session.turns.append(Turn(role="system", content=system_prompt(plan, unit)))
        session.turns.append(Turn(role="tutor", content=opening_message(plan, unit)))
        return session

    @property
    def active_unit(self):
        if self.week is None:
            return None
        return self.plan.week(self.week)

    def set_week(self, week: int | str) -> str:
        self.week = week
        unit = self.plan.week(week)
        if unit is None:
            msg = f"I couldn't find week {week} in the syllabus. Available: " + ", ".join(
                str(w.week) for w in self.plan.weeks
            )
            self.turns.append(Turn(role="tutor", content=msg))
            return msg
        # refresh system context
        self.turns.append(Turn(role="system", content=system_prompt(self.plan, unit)))
        msg = opening_message(self.plan, unit)
        self.turns.append(Turn(role="tutor", content=msg))
        return msg

    def human_say(self, text: str) -> None:
        self.turns.append(Turn(role="human", content=text.strip()))

    def tutor_say(self, text: str) -> str:
        self.turns.append(Turn(role="tutor", content=text.strip()))
        return text.strip()

    def prompt_bundle(self) -> dict[str, Any]:
        """Payload a host LLM (NOVA / OpenClaw / local) can feed to the model."""
        unit = self.active_unit
        return {
            "course_id": self.plan.course.course_id,
            "title": self.plan.course.title,
            "week": self.week,
            "system": system_prompt(self.plan, unit),
            "history": [
                {"role": t.role, "content": t.content}
                for t in self.turns
                if t.role != "system"
            ],
            "syllabus_excerpt": self.plan.raw_syllabus[:4000],
        }

    def last_tutor(self) -> str:
        for t in reversed(self.turns):
            if t.role == "tutor":
                return t.content
        return ""
