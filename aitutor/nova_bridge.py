"""Optional thin bridge so NOVA can plug AiTutor without owning its corpus."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aitutor import __version__
from aitutor.catalog import CourseCatalog, default_content_dir
from aitutor.paths import user_built_dir
from aitutor.lesson import LessonPlan, parse_lesson_plan
from aitutor.session import TutorSession
from aitutor.pipeline.lecture import lecture_payload
from aitutor.pipeline.builder import BuildRequest, build_prompt_pack


class TutorModule:
    """NOVA-facing façade. Import this; do not copy courses into fieldkit."""

    MODULE_ID = "aitutor"
    DISPLAY_NAME = "AiTutor"

    def __init__(self, content_dir: Path | None = None) -> None:
        self.catalog = CourseCatalog(content_dir or default_content_dir())

    @classmethod
    def from_content_dir(cls, path: Path | None = None) -> "TutorModule":
        return cls(path)

    def list_courses(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.course_id,
                "title": c.title,
                "audience": c.audience,
                "tags": c.tags,
                "duration": c.duration_hint,
            }
            for c in self.catalog.list()
        ]

    def lesson_plan(self, course_id: str) -> LessonPlan:
        return parse_lesson_plan(course_id, self.catalog)

    def start_session(
        self,
        course_id: str,
        week: int | str | None = None,
        learner_name: str = "learner",
    ) -> TutorSession:
        return TutorSession.start(
            course_id,
            week=week,
            learner_name=learner_name,
            catalog=self.catalog,
        )


    def lecture(self, course_id: str, week: int | str | None = None) -> dict:
        plan = self.lesson_plan(course_id)
        return lecture_payload(plan, week=week)

    def build_pack(self, request: BuildRequest) -> dict:
        return build_prompt_pack(request)
    def nova_manifest(self) -> dict[str, Any]:
        return {
            "module": self.MODULE_ID,
            "name": self.DISPLAY_NAME,
            "version": __version__,
            "kind": "education",
            "entry": "aitutor.nova_bridge:TutorModule",
            "content_dir": str(self.catalog.content_dir),
            "user_courses_dir": str(user_built_dir()),
            "courses": self.list_courses(),
            "notes": (
                "Standalone Projects module. Optional NOVA dependency. "
                "Keeps syllabus corpus out of the fieldkit tree."
            ),
        }
