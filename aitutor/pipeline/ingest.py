"""Bring raw materials into AiTutor without copying giant corpora."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from aitutor.paths import portable_locator, resolve_input_file


@dataclass
class IngestedMaterial:
    material_id: str
    title: str
    locator: str
    kind: str  # file | paste | url | shard
    text: str
    authority_hint: str = "secondary"  # primary|secondary
    meta: dict = field(default_factory=dict)

    @property
    def excerpt(self) -> str:
        return self.text[:6000]


def _sid(locator: str) -> str:
    h = hashlib.sha1(locator.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"M-{h}"


def ingest_text(
    text: str,
    *,
    title: str = "parent-syllabus",
    authority_hint: str = "primary",
    kind: str = "paste",
) -> IngestedMaterial:
    locator = f"paste://{title}"
    return IngestedMaterial(
        material_id=_sid(locator),
        title=title,
        locator=locator,
        kind=kind,
        text=text,
        authority_hint=authority_hint,
        meta={"chars": len(text)},
    )


def ingest_path(
    path: Path | str,
    *,
    max_chars: int = 120_000,
    authority_hint: str | None = None,
) -> IngestedMaterial:
    # Absolute, ${SOURCE_ROOT}/..., or relative (cwd first, then source root).
    p = resolve_input_file(path)
    raw = read_source_text(p)
    if len(raw) > max_chars:
        raw = raw[:max_chars] + "\n\n[truncated for token budget]\n"
    hint = authority_hint or _guess_authority(p)
    # Stored as ${SOURCE_ROOT}/relative/path when the file is under the source
    # root, so the course stays valid on any machine with the same layout.
    locator = portable_locator(p)
    return IngestedMaterial(
        material_id=_sid(locator),
        title=p.stem,
        locator=locator,
        kind="file",
        text=raw,
        authority_hint=hint,
        meta={"suffix": p.suffix, "bytes": p.stat().st_size},
    )


def ingest_paths(paths: list[Path | str], **kwargs) -> list[IngestedMaterial]:
    return [ingest_path(p, **kwargs) for p in paths]


# --- reading many formats -------------------------------------------------

SCANNED_PDF = ("has no text layer: it looks like a scanned PDF (pictures of pages). AiTutor can't read "
               "images yet; run OCR on it first (for example: ocrmypdf input.pdf output.pdf) or export it as text")

TEXT_SUFFIXES = {".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tex", ".org"}
HTML_SUFFIXES = {".html", ".htm"}
PDF_SUFFIXES = {".pdf"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".aitutor"}


def pdf_supported() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def supported_suffixes() -> set[str]:
    out = TEXT_SUFFIXES | HTML_SUFFIXES
    if pdf_supported():
        out |= PDF_SUFFIXES
    return out


_TAG_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>|<[^>]+>")


def read_source_text(p: Path) -> str:
    """Plain text from a source file. PDF needs the optional ``pypdf`` package."""
    suffix = p.suffix.lower()
    if suffix in PDF_SUFFIXES:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError(
                f"{p.name} is a PDF. Install PDF support with: pip install \"aitutor[pdf]\""
            ) from exc
        try:
            reader = PdfReader(str(p))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:  # pypdf raises many types on damaged files
            raise ValueError(f"Could not read PDF {p.name}: {exc}") from exc
        text = "\n\n".join(f"[page {i}]\n{t}" for i, t in enumerate(pages, 1) if t)
        if not text.strip():
            raise ValueError(f"{p.name} {SCANNED_PDF}")
        return text
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    if suffix in HTML_SUFFIXES:
        import html

        raw = html.unescape(_TAG_RE.sub(" ", raw))
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
    return raw


@dataclass
class FolderScan:
    files: list[Path]
    skipped: list[tuple[Path, str]]


def scan_folder(folder: Path | str, *, max_files: int = 40) -> FolderScan:
    """List usable source files under a folder (recursive, sorted, hidden dirs skipped)."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"No such folder: {root}")
    ok = supported_suffixes()
    files: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for p in sorted(root.rglob("*"), key=lambda q: str(q).lower()):
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") or part in SKIP_DIRS for part in rel_parts[:-1]):
            continue
        if not p.is_file() or p.name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf in ok:
            if len(files) < max_files:
                files.append(p)
            else:
                skipped.append((p, f"over the {max_files}-file limit"))
        elif suf in PDF_SUFFIXES:
            skipped.append((p, "PDF support not installed (pip install \"aitutor[pdf]\")"))
        elif suf in {".epub", ".docx", ".doc", ".odt", ".pptx"}:
            skipped.append((p, f"{suf} not supported yet; export to PDF or text"))
    return FolderScan(files=files, skipped=skipped)


def ingest_source(path: Path | str, **kwargs) -> tuple[list[IngestedMaterial], list[tuple[Path, str]]]:
    """A file or a folder -> materials (+ files skipped with reasons)."""
    p = Path(path).expanduser()
    if p.is_dir():
        scan = scan_folder(p)
        mats: list[IngestedMaterial] = []
        skipped = list(scan.skipped)
        for f in scan.files:
            try:
                mats.append(ingest_path(f, **kwargs))
            except (ValueError, OSError) as exc:
                skipped.append((f, str(exc)))
        return mats, skipped
    return [ingest_path(p, **kwargs)], []


# --- fitting material into a small context window --------------------------

_HEADING_RE = re.compile(
    r"^(?:#{1,4}\s+\S.*|(?:chapter|part|section|unit|module|week|lesson)\s+[\divxlc]+\b.*"
    r"|\d{1,2}(?:\.\d{1,2}){0,2}\s+[A-Z][^.!?]{2,80}|[A-Z][A-Z0-9 ,:'&-]{5,70})$",
    re.IGNORECASE,
)


def headings(text: str, limit: int = 60) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if 4 <= len(line) <= 90 and _HEADING_RE.match(line) and line.lower() not in seen:
            seen.add(line.lower())
            out.append(line)
            if len(out) >= limit:
                break
    return out


def smart_excerpt(text: str, budget: int) -> str:
    """Fit ``text`` into ``budget`` characters, keeping its structure visible.

    Short texts are returned whole. Long ones keep the opening (often a table of
    contents or overview), the outline of headings found anywhere in the text,
    and evenly spaced samples from the rest.
    """
    text = text.strip()
    if len(text) <= budget:
        return text
    budget = max(budget, 600)
    outline = headings(text)
    outline_block = ""
    if outline:
        outline_block = "\n[outline found in this source]\n" + "\n".join(f"- {h}" for h in outline)
        outline_block = outline_block[: int(budget * 0.3)]
    remaining = budget - len(outline_block)
    head_len = int(remaining * 0.5)
    parts = [text[:head_len].rstrip() + "\n[...]"]
    samples = 3
    sample_len = max(150, (remaining - head_len) // samples - 20)
    span = len(text) - head_len
    for i in range(samples):
        start = head_len + int(span * (i + 1) / (samples + 1))
        parts.append(text[start : start + sample_len].strip() + "\n[...]")
    return ("\n".join(parts) + outline_block)[: budget + 40]


_PRIMARY_NAME = re.compile(
    r"(?i)(syllabus|standard|fm[\s_-]?\d|manual|nasa|doe|curriculum|regulation)"
)


def _guess_authority(path: Path) -> str:
    blob = f"{path.name} {path.parent.name}"
    if _PRIMARY_NAME.search(blob):
        return "primary"
    if path.suffix.lower() in {".pdf", ".txt", ".odt"} and "manual" in blob.lower():
        return "primary"
    return "secondary"

def explain_unusable(source: Path | str, skipped: list[tuple[Path, str]]) -> str:
    """Why nothing in ``source`` could be used, in words a learner can act on."""
    scanned = [f.name for f, why in skipped if "no text layer" in why]
    if scanned:
        names = ", ".join(scanned[:5]) + (f" and {len(scanned) - 5} more" if len(scanned) > 5 else "")
        return (f"no usable source text in {source}: {names} {'is a' if len(scanned) == 1 else 'are'} scanned "
                "PDF(s) with no text layer. AiTutor can't read images yet; run OCR first "
                "(for example: ocrmypdf input.pdf output.pdf) or export the document as text.")
    if skipped:
        reasons = sorted({why for _f, why in skipped})
        return f"no usable source files in {source} (skipped {len(skipped)}: " + "; ".join(reasons[:3]) + ")"
    return f"no usable source files in {source} (supported: .txt .md .html .pdf and similar text files)"
