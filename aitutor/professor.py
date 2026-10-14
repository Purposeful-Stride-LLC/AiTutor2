"""Professor persona — tutoring style distilled from GZU / Professor Grok shards."""

from __future__ import annotations

from aitutor.lesson import LessonPlan, WeekUnit


PROFESSOR_CORE = """You are Professor Grok (AiTutor), an AI educator for Ad Astra / Grok XZone University.

Mission:
- Teach a human learner from real course materials (syllabus + week unit).
- Personalize: build on prior knowledge; skip what they already know; dig into gaps.
- Be rigorous but encouraging. Prefer concrete activities over lectures alone.
- For child audiences: shorter sentences, praise effort, keep it playful and safe.
- For adult retraining: dignity of prior career, map old skills to new domain.
- Never invent credentials or fake NASA/SpaceX certification; cite the syllabus.

Session contract:
1. Confirm the course and week.
2. State the week's objective in plain language.
3. Teach one concept, then check understanding with a short question or mini-activity.
4. End with a clear next step the human can do offline or next session.
"""


def system_prompt(plan: LessonPlan, unit: WeekUnit | None = None) -> str:
    parts = [PROFESSOR_CORE, "", f"Course: {plan.course.title} ({plan.course.course_id})"]
    parts.append(f"Audience: {plan.course.audience}")
    if plan.overview:
        parts.append(f"Overview: {plan.overview}")
    if unit:
        parts.append("")
        parts.append(f"Active week/module: {unit.week} — {unit.title}")
        if unit.objective:
            parts.append(f"Objective: {unit.objective}")
        if unit.topics:
            parts.append("Topics:")
            parts.extend(f"  - {t}" for t in unit.topics[:12])
        if unit.activity:
            parts.append(f"Activity: {unit.activity}")
    else:
        parts.append("No week selected yet — help the learner pick a starting week.")
    return "\n".join(parts)


def opening_message(plan: LessonPlan, unit: WeekUnit | None = None) -> str:
    if unit is None:
        return (
            f"Welcome. I'm your AiTutor for **{plan.course.title}**. "
            f"This course has {len(plan.weeks)} units in the syllabus. "
            "Which week or module should we start with?"
        )
    bits = [
        f"Week {unit.week}: {unit.title}.",
    ]
    if unit.objective:
        bits.append(f"Today's aim: {unit.objective}")
    if unit.activity:
        bits.append(f"We'll work toward: {unit.activity}")
    bits.append("What do you already know about this, and where do you want to start?")
    return " ".join(bits)
