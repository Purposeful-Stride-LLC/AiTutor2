"""Smoke tests for AiTutor catalog + lesson parse + session."""

from aitutor.catalog import CourseCatalog
from aitutor.lesson import parse_lesson_plan
from aitutor.nova_bridge import TutorModule
from aitutor.session import TutorSession


def test_list_includes_core_courses():
    ids = {c.course_id for c in CourseCatalog().list()}
    assert "geology-aerospace" in ids
    assert "nasa-modeling" in ids
    assert "little-explorers" in ids


def test_parse_geology_weeks():
    plan = parse_lesson_plan("geology-aerospace")
    assert plan.course.title
    assert len(plan.weeks) >= 4
    w1 = plan.week(1)
    assert w1 is not None
    assert "Geology" in w1.title or "Mapping" in w1.title or w1.title


def test_session_opening():
    s = TutorSession.start("nasa-modeling", week=1)
    assert s.last_tutor()
    bundle = s.prompt_bundle()
    assert bundle["course_id"] == "nasa-modeling"
    assert "Professor" in bundle["system"] or "AiTutor" in bundle["system"]


def test_nova_manifest():
    m = TutorModule().nova_manifest()
    assert m["module"] == "aitutor"
    assert len(m["courses"]) >= 3
