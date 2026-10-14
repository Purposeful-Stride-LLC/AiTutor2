"""AiTutor: turn source material into cited courses and tutoring sessions."""

__version__ = "0.4.0"

from aitutor.catalog import CourseCatalog, list_courses
from aitutor.lesson import LessonPlan, WeekUnit
from aitutor.session import TutorSession

__all__ = [
    "CourseCatalog",
    "LessonPlan",
    "TutorSession",
    "WeekUnit",
    "list_courses",
    "__version__",
]
