"""Guided line-mode UI: check → pick source → build → learn.

Stdlib only. Works in PowerShell, cmd, bash, Windows Terminal, and plain
consoles. Every prompt accepts a blank line for the sensible default.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aitutor import doctor, llm_host, paths, settings
from aitutor.pipeline.autobuild import WeakSourceError, build_course, source_root_for
from aitutor.pipeline.builder import BuildRequest
from aitutor.pipeline.course_store import list_built
from aitutor.pipeline.ingest import explain_unusable, ingest_source, scan_folder
from aitutor.pedagogy import LearnSession


def _say(text: str = "") -> None:
    print(text, flush=True)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        _say()
        raise SystemExit(0)
    return answer or (default or "")


def _pick(prompt: str, choices: list[tuple[str, str]], *, allow_quit: bool = True) -> str:
    """Numbered menu. Returns the chosen key. ``choices`` is [(key, label)]."""
    _say()
    _say(prompt)
    for i, (_k, label) in enumerate(choices, 1):
        _say(f"  {i}. {label}")
    if allow_quit:
        _say("  q. Quit")
    while True:
        ans = _ask("Choice").lower()
        if allow_quit and ans in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if ans.isdigit() and 1 <= int(ans) <= len(choices):
            return choices[int(ans) - 1][0]
        _say(f"Enter a number 1–{len(choices)}" + (" or q" if allow_quit else ""))


def _stream(piece: str) -> None:
    sys.stdout.write(piece)
    sys.stdout.flush()


def _ensure_ready() -> int:
    report = doctor.run_checks()
    _say(doctor.format_report(report))
    if report.ready:
        return 0
    _say()
    go = _ask("Run guided setup now? (Y/n)", "Y").lower()
    if go not in {"", "y", "yes"}:
        _say("Come back when Ollama and the model are ready: aitutor setup")
        return 1
    return doctor.interactive_setup(assume_yes=False)


def _pick_source() -> Path:
    while True:
        raw = _ask("Path to a source file or folder (drag-and-drop works in most terminals)")
        if not raw:
            continue
        # Strip quotes that Windows drag-and-drop adds.
        raw = raw.strip().strip('"').strip("'")
        try:
            p = paths.resolve_input_path(raw)
        except FileNotFoundError as exc:
            _say(f"  {exc}")
            continue
        if p.is_dir():
            scan = scan_folder(p)
            _say(f"  Folder: {p}")
            _say(f"  Usable files: {len(scan.files)}" + (f"  (skipped {len(scan.skipped)})" if scan.skipped else ""))
            for f in scan.files[:12]:
                _say(f"    - {f.relative_to(p)}")
            if len(scan.files) > 12:
                _say(f"    ... and {len(scan.files) - 12} more")
            if not scan.files:
                _say("  No usable text/Markdown/HTML/PDF files here. Try another path.")
                continue
        else:
            _say(f"  File: {p}  ({p.stat().st_size:,} bytes)")
        ok = _ask("Use this? (Y/n)", "Y").lower()
        if ok in {"", "y", "yes"}:
            return p


def _build_from(source: Path) -> str | None:
    default_subject = source.stem.replace("_", " ").replace("-", " ").title()
    subject = _ask("Course subject", default_subject)
    audience = _pick("Audience", [("adult", "Adult"), ("child", "Child (K–12)"), ("mixed", "Mixed")])
    goal = _ask("Goal (one sentence)", "increase practical self-sufficiency")
    paths.set_source_root(source_root_for(source))
    materials, skipped = ingest_source(source)
    for f, why in skipped:
        _say(f"  skipped {f.name}: {why}")
    if not materials:
        _say(f"Cannot build: {explain_unusable(source, skipped)}")
        return None
    cfg = settings.resolve()
    _say(f"Building with {cfg.model} (num_ctx {cfg.num_ctx}) from {len(materials)} source(s)...")
    req = BuildRequest(subject=subject, audience=audience, goal=goal, materials=materials,
                       subject_given=subject.strip() != default_subject)
    received = [0]
    live = sys.stderr.isatty()

    def progress(piece: str) -> None:
        received[0] += len(piece)
        if live:
            print(f"\r  receiving course JSON: {received[0]} chars", end="", file=sys.stderr, flush=True)

    anyway = False
    while True:
        try:
            result = build_course(req, cfg, on_token=progress, save=True, anyway=anyway)
            break
        except WeakSourceError as exc:
            _say(f"Warning: {exc}")
            if _ask("Build anyway? (y/N)", "n").lower() not in ("y", "yes"):
                _say("Not building. Add better material and try again.")
                return None
            anyway = True
        except (llm_host.HostError, ValueError) as exc:
            if live:
                print(file=sys.stderr)
            _say(f"Build failed: {exc}")
            return None
        except Exception as exc:  # a model glitch must never kill the session
            _say(f"Build failed (unexpected {type(exc).__name__}): {exc}")
            return None
    if live:
        print(f"\r  received course JSON: {received[0]} chars", file=sys.stderr)
    for w in result.warnings:
        _say(f"  warning: {w}")
    c = result.stored.data
    _say(f"Saved {result.stored.course_id}")
    _say(f"  {c['title']}  —  {len(c['weeks'])} units, {len(c['sources'])} sources")
    for w in c["weeks"]:
        _say(f"    {w['week']}. {w['title']}")
    return result.stored.course_id


def _teach(course_id: str) -> None:
    try:
        session = LearnSession.start(course_id)
    except (KeyError, ValueError) as exc:
        _say(f"Cannot open course: {exc}")
        return
    cfg = settings.resolve()
    _say(f"Teaching with {cfg.model}")
    _say("Sources on this computer:")
    _say(session.source_report())
    _say()
    _say(session.opening())
    _say()
    try:
        print("tutor> ", end="", flush=True)
        session.ask(on_token=_stream)
        print()
    except llm_host.HostError as exc:
        _say(f"\nModel error: {exc}")
        return

    while True:
        try:
            line = _ask(f"you [{session.phase}] (/next /prev /sources /quit)")
        except SystemExit:
            return
        if line.lower() in {"/quit", "quit", "exit", "q"}:
            return
        if line.lower() in {"/next", "/skip"}:
            _say(session.advance())
            _say(session.opening())
            if session.phase in ("lesson", "practice", "review"):
                print("tutor> ", end="", flush=True)
                session.ask(on_token=_stream)
                print()
            continue
        if line.lower() == "/prev":
            _say(session.set_unit(-1))
            _say(session.opening())
            continue
        if line.lower() == "/sources":
            _say(session.source_report())
            continue
        try:
            if session.phase == "practice":
                print("tutor> ", end="", flush=True)
                session.submit_practice(line, on_token=_stream)
                print()
            else:
                print("tutor> ", end="", flush=True)
                session.ask(line, on_token=_stream)
                print()
        except llm_host.HostError as exc:
            _say(f"\nModel error: {exc}")
            return
        except Exception as exc:  # keep the session alive on an unexpected reply
            _say(f"\nSomething went wrong ({type(exc).__name__}: {exc}). Try again or type /next.")


def run() -> int:
    try:
        return _run()
    except SystemExit as exc:  # q / Ctrl-D / Ctrl-C at any prompt
        return int(exc.code or 0)
    finally:
        paths.set_source_root(None)


def _run() -> int:
    _say("=" * 60)
    _say("  AiTutor — build a course from your material, then learn it")
    _say("=" * 60)
    if _ensure_ready() != 0:
        return 1

    while True:
        existing = list_built()
        choices: list[tuple[str, str]] = [
            ("new", "Build a new course from a file or folder"),
        ]
        for c in existing[:20]:
            title = str(c.data.get("title") or c.course_id)
            choices.append((f"open:{c.course_id}", f"Learn: {title}  [{c.origin}]"))
        choices.append(("doctor", "Re-check requirements"))
        action = _pick("What would you like to do?", choices)
        if action == "doctor":
            _say(doctor.format_report(doctor.run_checks()))
            continue
        if action == "new":
            source = _pick_source()
            cid = _build_from(source)
            if cid and _ask("Start learning it now? (Y/n)", "Y").lower() in {"", "y", "yes"}:
                _teach(cid)
            continue
        if action.startswith("open:"):
            _teach(action.split(":", 1)[1])
            continue
    return 0
