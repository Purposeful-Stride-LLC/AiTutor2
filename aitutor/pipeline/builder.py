"""Assemble the prompt pack that makes an LLM *build* a cited course."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from aitutor import safety
from aitutor.paths import prompts_dir
from aitutor.pipeline.ingest import IngestedMaterial, smart_excerpt
from aitutor.pipeline.sources import SourceRegistry


BUILD_INSTRUCTION = (
    "Build the cited course JSON now. Teach ONLY what the material excerpts above actually contain: "
    "every unit's title, objective and topics must come from the excerpts it cites. If the subject or "
    "goal needs anything the excerpts do not contain, list it in gaps[] and do NOT create a unit for it. "
    "Fewer units are better than units the material does not support. If the excerpts contain no usable "
    "teaching material for this subject (placeholder or random text, only a table of contents or a data "
    "table, or a different subject), return exactly one unit titled \"Source material needed\" that "
    "explains what is missing, and say so in gaps[]."
)


def _prompts_dir() -> Path:
    return prompts_dir()


def load_builder_methodology() -> str:
    path = _prompts_dir() / "course_builder.md"
    return path.read_text(encoding="utf-8")


@dataclass
class BuildRequest:
    subject: str
    learner: str = "adult professional"
    goal: str = "increase practical self-sufficiency"
    audience: str = "adult"
    materials: list[IngestedMaterial] = field(default_factory=list)
    extra_notes: str = ""
    # False when the subject is only a default (file or folder name): then it is not
    # checked against the material.
    subject_given: bool = True


def build_prompt_pack(req: BuildRequest, *, excerpt_budget: int | None = None) -> dict:
    """
    Returns a host-ready pack:
      system  — methodology
      user    — subject + learner + source list + excerpts
      registry — SourceRegistry JSON companion
    The host LLM should answer with the course JSON schema from the methodology.
    """
    registry = SourceRegistry()
    excerpt_blocks: list[str] = []
    injection: list[dict[str, str]] = []
    # With a budget (small local models), split it fairly across materials.
    per_material = None
    if excerpt_budget is not None and req.materials:
        per_material = max(600, excerpt_budget // len(req.materials))
    for mat in req.materials:
        rec = registry.add_material(mat)
        clean = safety.neutralize(mat.text)
        for hit in clean.hits:
            injection.append({"source_id": rec.id, "title": mat.title, "text": hit})
        body = clean.text[:6000] if per_material is None else smart_excerpt(clean.text, per_material)
        excerpt_blocks.append(
            f"### [{rec.id}] {mat.title}\n"
            f"locator: {mat.locator}\n"
            f"authority: {mat.authority_hint}\n\n"
            f"{safety.fence(rec.id, mat.title, body)}\n"
        )

    system = load_builder_methodology() + "\n\n## Untrusted material\n\n" + safety.DATA_RULE
    user_parts = [
        f"Subject: {req.subject}",
        f"Learner: {req.learner}",
        f"Audience: {req.audience}",
        f"Goal: {req.goal}",
        "",
        registry.as_prompt_block(),
        "",
        "Material excerpts:",
        *excerpt_blocks,
    ]
    if req.extra_notes:
        user_parts.extend(["", "Builder notes from human:", req.extra_notes])
    user_parts.append("\n" + BUILD_INSTRUCTION)

    return {
        "phase": "build",
        "system": system,
        "user": "\n".join(user_parts),
        "sources": json.loads(registry.to_json()),
        "expect": "course_json",
        "injection": injection,
    }