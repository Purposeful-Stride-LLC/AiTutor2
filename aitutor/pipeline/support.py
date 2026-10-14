"""How much does the learner's material actually support a course?

Deterministic, stdlib-only checks used around the model call:

* ``assess_sources`` before building: is there enough readable text, and is it about the subject?
* ``unit_budget``: how many units the material can carry.
* ``unsupported_units`` after building: units whose topics do not appear in the sources they cite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORD = re.compile(r"[a-z][a-z'\-]{3,}")
# Words that say nothing about a unit's content (pedagogy and course-structure words).
GENERIC = set("""
about above after again against also among another around because been before being below between both could
does doing down during each either every from further have having here into itself just like make many more
most must other over same should some such than that their them then there these they this those through under
until very what when where which while will with within without would your yours able used using
learn learner learners learning lesson lessons unit units week weeks module modules session sessions part parts
student students know identify explain describe apply applying application applications understand understanding
basic basics introduction introductory overview practice practical practicing skill skills concept concepts key
important including various different activity activities assessment assessments write writing short simple common
example examples final review recap preparation prepare prepared test tests testing exam exams certification
certified knowledge challenge challenges structure structures fundamental fundamentals foundation foundations
principle principles requirement requirements exercise exercises career careers mastery demonstrate complete
completion strategies strategy readiness ready summary summarize core essential essentials advanced topic topics
study studying develop developing development plan planning real-world world scenario scenarios case cases project
projects work working role roles importance purpose purposes process processes method methods technique techniques
type types definition definitions term terms terminology main course courses goal goals level levels guide
""".split())
SCAFFOLD = re.compile(
    r"\b(review|final|recap|capstone|assessment|test prep|exam prep|practice test|wrap[- ]up|"
    r"putting it (all )?together|preparing for|source material needed)\b",
    re.I,
)
_FUNCTION = set("the of and to in is that for it as with was on are be by this which or from at an have not "
                "they their has its can one but were".split())
# Readable prose in another language is still material (the course is written in English).
# Each language is scored on its own, so a mix of stray short words (lorem ipsum) doesn't add up.
_FUNCTION_OTHER = [
    set("el la los las de que y en un una es por con para del se al lo como mas más su sus no".split()),   # es
    set("le la les de des et est un une du en que qui dans pour pas sur au aux il elle ne se".split()),    # fr
    set("der die das und ist ein eine zu den von mit sich des auf für nicht im dem als auch es".split()),  # de
    set("o a os as de que e em um uma do da dos das para com por não se no na ao".split()),               # pt
]
_TOKEN = re.compile(r"[A-Za-zÀ-ÿ']+")

CHARS_PER_UNIT = 2500
MIN_WORDS = 150


def content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in GENERIC and w[:6] not in _GENERIC6]


_GENERIC6 = {g[:6] for g in GENERIC}


def prefixes(text: str, n: int = 6) -> set[str]:
    return {w[:n] for w in _WORD.findall(text.lower())}


def unit_budget(total_chars: int) -> int:
    """About one unit per 2,500 characters of material, between 1 and 8."""
    return max(1, min(8, round(total_chars / CHARS_PER_UNIT)))


@dataclass
class SourceAssessment:
    words: int
    function_ratio: float
    subject_overlap: float | None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def message(self) -> str:
        return "; ".join(self.problems)


def assess_sources(texts: list[str], subject: str) -> SourceAssessment:
    """Flag material that is too thin, unreadable, or not about ``subject``."""
    text = "\n".join(texts)
    toks = _TOKEN.findall(text)
    n = len(toks)
    low = [t.lower() for t in toks]
    func = (sum(1 for t in low if t in _FUNCTION) / n) if n else 0.0
    other = max((sum(1 for t in low if t in fs) / n for fs in _FUNCTION_OTHER), default=0.0) if n else 0.0
    subj = [w for w in content_words(subject) if not w.startswith("grade")]
    pref = prefixes(text)

    def _hit(w: str) -> bool:  # "pre-algebra" also matches on "algebra"
        return any(f[:6] in pref for f in [w] + [p for p in w.split("-") if len(p) >= 4])

    overlap = (sum(1 for w in subj if _hit(w)) / len(subj)) if subj else None
    problems = []
    if n < MIN_WORDS:
        problems.append(f"only {n} words of text (a course needs more material than that)")
    if n and func < 0.08 and other < 0.08:
        problems.append("the text doesn't read like normal English prose (placeholder, random, "
                        "table-only, garbled, or another language)")
    if overlap == 0:
        problems.append(f"none of the words in the subject \u201c{subject}\u201d appear in the material")
    return SourceAssessment(n, round(func, 3), overlap, problems)


def topic_supported(topic: str, pref: set[str]) -> bool:
    ws = content_words(topic)
    return True if not ws else sum(1 for w in ws if w[:6] in pref) / len(ws) >= 0.5


def unsupported_units(weeks: list[dict], texts_by_id: dict[str, str]) -> list[int]:
    """Indexes of content units whose topics mostly do not appear in the sources they cite.

    Review / test-prep units are scaffolding and are not checked.
    """
    all_text = "\n".join(texts_by_id.values())
    cache: dict[tuple[str, ...], set[str]] = {}
    bad = []
    for i, w in enumerate(weeks):
        if SCAFFOLD.search(str(w.get("title") or "")):
            continue
        ids = tuple(sorted(x for x in w.get("source_ids") or [] if x in texts_by_id))
        if ids not in cache:
            cache[ids] = prefixes("\n".join(texts_by_id[x] for x in ids) if ids else all_text)
        pref = cache[ids]
        # Topics with no checkable words ("1G-4G", "Part 2") are neutral; fall back to the title.
        topics = [t for t in (w.get("topics") or []) if content_words(str(t))]
        if not topics:
            topics = [str(w.get("title") or "")] if content_words(str(w.get("title") or "")) else []
        if not topics:
            continue
        ok = sum(1 for t in topics if topic_supported(t, pref))
        if ok / len(topics) < 0.5:
            bad.append(i)
    return bad


def supporting_sources(week: dict, texts_by_id: dict[str, str]) -> list[str]:
    """Source ids whose text supports this unit's topics (empty when no source does)."""
    probe = [dict(week, source_ids=[sid]) for sid in texts_by_id]
    single = [sid for sid, w in zip(texts_by_id, probe) if not unsupported_units([w], {sid: texts_by_id[sid]})]
    if single:
        return single
    union = dict(week, source_ids=list(texts_by_id))
    return [] if unsupported_units([union], texts_by_id) else list(texts_by_id)
