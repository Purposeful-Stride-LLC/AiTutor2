"""Ground tutoring in the learner's own sources.

Resolves a course's source locators on this machine, splits the text into
passages and picks the passages most relevant to the current unit. Stdlib
only: a small keyword/IDF ranker is plenty for a handful of documents.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aitutor import paths
from aitutor.pipeline.ingest import read_source_text
from aitutor.pipeline.provenance import sha256_file

_WORD = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")
_STOP = set("""the and for are but not you all any can had her was one our out has have his how its may new now
old see two who did get let put say she too use that this with from they will would there their what about
which when your than then them these some into more most other such only also been were each just over very
""".split())


def _terms(text: str) -> list[str]:
    return [w for w in (m.group(0).lower().strip("'-") for m in _WORD.finditer(text)) if w not in _STOP]


@dataclass
class Passage:
    source_id: str
    title: str
    text: str
    terms: Counter = field(default_factory=Counter)


@dataclass
class SourceStatus:
    source_id: str
    title: str
    locator: str
    path: Path | None
    found: bool
    note: str = ""


def chunk(text: str, size: int = 1100, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
            continue
        if cur:
            out.append(cur)
            cur = cur[-overlap:] + "\n\n" if overlap else ""
        while len(p) > size:
            out.append((cur + p[:size]).strip())
            p, cur = p[size - overlap:], ""
        cur = (cur + p).strip()
    if cur:
        out.append(cur)
    return out


def _cached_text(path: Path, digest: str | None) -> str:
    """PDF extraction is slow; cache plain text in AITUTOR_HOME/cache by content hash."""
    if path.suffix.lower() != ".pdf":
        return read_source_text(path)
    digest = digest or sha256_file(path)
    cache = paths.aitutor_home() / "cache" / "text" / f"{digest}.txt"
    if cache.is_file():
        return cache.read_text(encoding="utf-8")
    text = read_source_text(path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


class Grounding:
    def __init__(self, passages: list[Passage], status: list[SourceStatus]):
        self.passages = passages
        self.status = status
        n = max(1, len(passages))
        df: Counter = Counter()
        for p in passages:
            df.update(set(p.terms))
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}

    @property
    def available(self) -> bool:
        return bool(self.passages)

    @classmethod
    def for_course(cls, course_id: str, sources: list[dict[str, Any]], *, extra_text: str = "") -> "Grounding":
        root, _origin = paths.course_source_root(course_id)
        passages: list[Passage] = []
        status: list[SourceStatus] = []
        for s in sources:
            sid, title, loc = str(s.get("id")), str(s.get("title") or s.get("id")), str(s.get("locator") or "")
            p = paths.resolve_locator(loc, root)
            if p is None:
                status.append(SourceStatus(sid, title, loc, None, False, "not a file (paste/URL)"))
                continue
            if not p.is_file():
                status.append(SourceStatus(sid, title, loc, p, False, "not found on this computer"))
                continue
            try:
                text = _cached_text(p, s.get("sha256"))
            except (ValueError, OSError) as exc:
                status.append(SourceStatus(sid, title, loc, p, False, str(exc)))
                continue
            status.append(SourceStatus(sid, title, loc, p, True))
            for c in chunk(text):
                passages.append(Passage(sid, title, c, Counter(_terms(c))))
        if extra_text.strip():
            for c in chunk(extra_text):
                passages.append(Passage("SYL", "course syllabus", c, Counter(_terms(c))))
        return cls(passages, status)

    def top(self, query: str, *, prefer: list[str] | None = None, budget: int = 3200, k: int = 6) -> list[Passage]:
        q = Counter(_terms(query))
        if not q or not self.passages:
            return []
        prefer_set = set(prefer or [])
        scored = []
        for i, p in enumerate(self.passages):
            score = sum(self.idf.get(t, 0) * (1 + math.log(p.terms[t])) * qn for t, qn in q.items() if t in p.terms)
            if p.source_id in prefer_set:
                score *= 1.5
            if score > 0:
                scored.append((score, -i, p))
        scored.sort(reverse=True)
        out: list[Passage] = []
        used = 0
        for _s, _i, p in scored[: k * 3]:
            if used + len(p.text) > budget and out:
                continue
            out.append(p)
            used += len(p.text)
            if len(out) >= k or used >= budget:
                break
        return out
