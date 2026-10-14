"""CLI: python -m aitutor …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aitutor import __version__, llm_host, paths, settings
from aitutor.catalog import CourseCatalog
from aitutor.lesson import parse_lesson_plan
from aitutor.nova_bridge import TutorModule
from aitutor.pipeline.builder import BuildRequest, build_prompt_pack
from aitutor.pipeline.course_store import list_built, save_from_llm_text
from aitutor.pipeline.ingest import ingest_path, ingest_text
from aitutor.pipeline.lecture import lecture_payload
from aitutor.pipeline.provenance import course_content_hash, sha256_file
from aitutor.pipeline.sources import resolved_source_roots
from aitutor.session import TutorSession


def cmd_list(_: argparse.Namespace) -> int:
    for c in CourseCatalog().list():
        tags = ",".join(c.tags)
        print(f"{c.course_id:32}  {c.kind:5}  {c.title}  [{c.audience}]  {tags}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    plan = parse_lesson_plan(args.course_id)
    print(f"# {plan.course.title}")
    print(plan.overview[:500] or "(no overview parsed)")
    print()
    for w in plan.weeks:
        print(f"  Week {w.week}: {w.title}")
        if w.objective:
            print(f"    Objective: {w.objective}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    session = TutorSession.start(args.course_id, week=args.week)
    print(session.last_tutor())
    print()
    print("--- prompt bundle (for host LLM) ---")
    print(json.dumps(session.prompt_bundle(), indent=2, ensure_ascii=False))
    return 0


def _stream_to_stdout(piece: str) -> None:
    sys.stdout.write(piece)
    sys.stdout.flush()


def _pick_host(requested: str) -> tuple[str, str | None]:
    """'auto'|'ollama'|'none' -> ('ollama'|'none', note-for-user)."""
    if requested == "none":
        return "none", None
    cfg = settings.resolve()
    try:
        if llm_host.has_model(cfg):
            return "ollama", None
        problem = f"model '{cfg.model}' is not pulled (run: ollama pull {cfg.model})"
    except llm_host.HostError as exc:
        problem = str(exc)
    return "none", f"[AiTutor] Local model unavailable: {problem}. Using offline replies; run `aitutor setup` for help."


def cmd_session(args: argparse.Namespace) -> int:
    session = TutorSession.start(
        args.course_id, week=args.week, learner_name=args.name or "learner"
    )
    host, note = _pick_host(args.host)
    if note:
        print(note, file=sys.stderr)
    elif host == "ollama":
        cfg = settings.resolve()
        print(f"[AiTutor] Tutor replies from local model {cfg.model} at {cfg.url}", file=sys.stderr)
    print(session.last_tutor())
    print("(type a reply, or /week N, /prompt, /quit)")
    while True:
        try:
            line = input(f"{session.learner_name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in {"/quit", "/exit", "quit", "exit"}:
            break
        if line.startswith("/week"):
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                print("usage: /week 1")
                continue
            print(session.set_week(parts[1].strip()))
            continue
        if line == "/prompt":
            print(json.dumps(session.prompt_bundle(), indent=2, ensure_ascii=False))
            continue
        session.human_say(line)
        reply = None
        if host == "ollama":
            try:
                print("tutor> ", end="", flush=True)
                reply = llm_host.ollama_reply(session.prompt_bundle(), on_token=_stream_to_stdout)
                print()
                session.tutor_say(reply)
                continue
            except llm_host.HostError as exc:
                print(f"\n[AiTutor] {exc} Falling back to offline replies.", file=sys.stderr)
                host = "none"
        reply = (
            f"[AiTutor offline stub] Noted. Start Ollama (see `aitutor setup`) for real "
            f"tutor replies. You said: {line[:200]}"
        )
        print(session.tutor_say(reply))
    return 0


def _stream_reply(piece: str) -> None:
    sys.stdout.write(piece)
    sys.stdout.flush()


def cmd_learn(args: argparse.Namespace) -> int:
    """Pedagogy cycle: lesson → practice → check → review, grounded in sources."""
    from aitutor.pedagogy import LearnSession

    session = LearnSession.start(args.course_id, week=args.week)
    cfg = settings.resolve()
    print(f"[AiTutor] Teaching with {cfg.model}  |  sources:", file=sys.stderr)
    print(session.source_report(), file=sys.stderr)
    print(session.opening())
    print()
    # Auto-start the lesson phase.
    try:
        print("tutor> ", end="", flush=True)
        session.ask(on_token=_stream_reply)
        print()
    except llm_host.HostError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        print("Run `aitutor setup` first.", file=sys.stderr)
        return 3

    while True:
        try:
            line = input(f"{args.name or 'learner'} [{session.phase}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in {"/quit", "/exit", "quit", "exit"}:
            break
        if line in {"/next", "/skip"}:
            print(session.advance())
            print(session.opening())
            if session.phase in ("lesson", "practice", "review"):
                print("tutor> ", end="", flush=True)
                session.ask(on_token=_stream_reply)
                print()
            continue
        if line == "/prev":
            print(session.set_unit(-1))
            print(session.opening())
            continue
        if line.startswith("/phase"):
            parts = line.split(maxsplit=1)
            print(session.set_phase(parts[1] if len(parts) > 1 else ""))
            continue
        if line == "/sources":
            print(session.source_report())
            continue
        if line == "/opening":
            print(session.opening())
            continue
        # Free text: during practice/check this is the learner's work; otherwise a question.
        try:
            if session.phase == "practice":
                # Submitting practice → graded against the task that was set.
                print("tutor> ", end="", flush=True)
                session.submit_practice(line, on_token=_stream_reply)
                print()
                if session.last_score is not None:
                    print(f"(score recorded: {session.last_score}/10)", file=sys.stderr)
            else:
                print("tutor> ", end="", flush=True)
                session.ask(line, on_token=_stream_reply)
                print()
        except llm_host.HostError as exc:
            print(f"\nerror: {exc}", file=sys.stderr)
            return 3
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from aitutor.tui import launch

    return launch(full=args.full, plain=args.plain)


def cmd_doctor(args: argparse.Namespace) -> int:
    from aitutor import doctor

    report = doctor.run_checks()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(doctor.format_report(report))
    return 0 if report.ready else 1


def cmd_setup(args: argparse.Namespace) -> int:
    from aitutor import doctor

    if getattr(args, "model", None) or getattr(args, "ollama_url", None) or getattr(args, "num_ctx", None):
        saved = settings.save_config({
            "model": getattr(args, "model", None),
            "url": getattr(args, "ollama_url", None),
            "num_ctx": getattr(args, "num_ctx", None),
        })
        print(f"saved settings -> {saved}")
    return doctor.interactive_setup(assume_yes=args.yes)


def cmd_manifest(_: argparse.Namespace) -> int:
    print(json.dumps(TutorModule().nova_manifest(), indent=2))
    return 0


def cmd_roots(_: argparse.Namespace) -> int:
    doc = resolved_source_roots()
    root, origin = paths.source_root()
    if origin == "cwd":
        print(paths.source_root_note(origin, root), file=sys.stderr)
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def cmd_paths(_: argparse.Namespace) -> int:
    print(json.dumps(paths.describe(), indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Check built-course hashes and whether each source resolves on this machine."""
    courses = list_built()
    if args.course_id:
        courses = [c for c in courses if c.course_id == args.course_id]
        if not courses:
            raise KeyError(f"Unknown built course_id: {args.course_id}")
    failures = 0
    for c in courses:
        stored = (c.data.get("provenance") or {}).get("content_sha256")
        ok = stored == course_content_hash(c.data)
        failures += 0 if ok else 1
        print(f"{c.course_id} [{c.origin}]  content hash: {'ok' if ok else 'MISMATCH'}")
        root, origin = paths.course_source_root(c.course_id)
        print(f"    {paths.source_root_note(origin, root)}")
        for s in c.data.get("sources") or []:
            p = paths.resolve_locator(s.get("locator"), root)
            if p is None:
                state = "not a file (paste/URL)"
            elif not p.is_file():
                state = f"missing on this machine: {p}"
            elif s.get("sha256") and sha256_file(p) != s["sha256"]:
                state = f"CHANGED (sha256 differs): {p}"
                failures += 1
            else:
                state = f"found: {p}"
            print(f"    {s.get('id')}: {state}")
    return 1 if failures else 0


def cmd_build(args: argparse.Namespace) -> int:
    from aitutor.pipeline.autobuild import WeakSourceError, build_course, source_root_for
    from aitutor.pipeline.ingest import explain_unusable, ingest_source

    if args.do_import and args.host != "ollama":
        print("error: --import needs --host ollama (the local model writes the course).", file=sys.stderr)
        return 2
    root, origin = paths.source_root()
    if args.source and origin == "cwd":
        # A picked file/folder becomes ${SOURCE_ROOT} unless one was set explicitly.
        paths.set_source_root(source_root_for(Path(args.source)))
        root, origin = paths.source_root()
    if (args.file or args.source) and origin == "cwd":
        print(paths.source_root_note(origin, root), file=sys.stderr)
    materials = []
    if args.source:
        found, skipped = ingest_source(paths.resolve_input_path(args.source))
        materials.extend(found)
        for f, why in skipped:
            print(f"skipped {f.name}: {why}", file=sys.stderr)
        if not found:
            print(f"error: {explain_unusable(args.source, skipped)}", file=sys.stderr)
            return 2
    for path in args.file or []:
        materials.append(ingest_path(path))
    if args.paste:
        paste = paths.resolve_input_file(args.paste).read_text(encoding="utf-8-sig", errors="replace")
        materials.append(
            ingest_text(
                paste,
                title=args.paste_title or "parent-syllabus",
                authority_hint="primary",
            )
        )
    if args.stdin_paste:
        materials.append(
            ingest_text(sys.stdin.read(), title="stdin-syllabus", authority_hint="primary")
        )
    if not materials and not args.subject:
        print(
            "Need --source, or --subject and at least one --file / --paste / --stdin-paste",
            file=sys.stderr,
        )
        return 2
    req = BuildRequest(
        subject=args.subject or (materials[0].title if materials else "untitled"),
        learner=args.learner,
        goal=args.goal,
        audience=args.audience,
        materials=materials,
        extra_notes=args.notes or "",
        subject_given=bool(args.subject),
    )
    if args.host == "ollama":
        cfg = settings.resolve()
        print(
            f"building from {len(materials)} source(s) with {cfg.model} (num_ctx {cfg.num_ctx}) ...",
            file=sys.stderr,
        )
        received = [0]
        live = sys.stderr.isatty()

        def progress(piece: str) -> None:
            received[0] += len(piece)
            if live:
                print(f"\r  receiving course JSON: {received[0]} chars", end="", file=sys.stderr, flush=True)

        anyway = args.anyway
        while True:
            try:
                result = build_course(req, cfg, on_token=progress, force=args.force, course_id=args.course_id,
                                      save=args.do_import, anyway=anyway)
                break
            except WeakSourceError as exc:
                print(f"warning: {exc}", file=sys.stderr)
                if anyway or not (sys.stdin.isatty() and sys.stdout.isatty()):
                    print("Not building. Add better material, or re-run with --anyway to build from it anyway.",
                          file=sys.stderr)
                    return 4
                try:
                    ok = input("Build anyway? [y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ok = ""
                if ok not in ("y", "yes"):
                    print("Not building.", file=sys.stderr)
                    return 4
                anyway = True
        print(f"{chr(13) if live else ''}  received course JSON: {received[0]} chars", file=sys.stderr)
        for w in result.warnings:
            print(f"warning: {w}", file=sys.stderr)
        c = result.stored.data
        if not args.do_import:
            text = json.dumps(c, indent=2, ensure_ascii=False)
            if args.out:
                Path(args.out).expanduser().write_text(text + "\n", encoding="utf-8")
                print(f"wrote course JSON -> {args.out} (not imported; add --import to save it)")
            else:
                print(text)
            return 0
        print(f"saved {result.stored.course_id} -> {result.stored.path}")
        print(f"title: {c['title']}  ({len(c['weeks'])} units, {len(c['sources'])} sources)")
        for w in c["weeks"]:
            print(f"  {w['week']}. {w['title']}  [{', '.join(w['source_ids'])}]")
        print(f"next: aitutor learn {result.stored.course_id}")
        return 0

    pack = build_prompt_pack(req)
    out = args.out
    text = json.dumps(pack, indent=2)
    if out:
        Path(out).expanduser().write_text(text, encoding="utf-8")
        print(f"wrote build prompt pack -> {out}")
    else:
        print(
            json.dumps(
                {
                    "phase": pack["phase"],
                    "expect": pack["expect"],
                    "sources": pack["sources"],
                    "system_chars": len(pack["system"]),
                    "user_chars": len(pack["user"]),
                    "user_preview": pack["user"][:1500],
                },
                indent=2,
            )
        )
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    if args.file:
        text = Path(args.file).expanduser().read_text(encoding="utf-8-sig", errors="replace")
    else:
        text = sys.stdin.read()
    stored = save_from_llm_text(text, force=args.force)
    print(f"saved {stored.course_id} -> {stored.path}")
    return 0


def cmd_built(_: argparse.Namespace) -> int:
    for s in list_built():
        print(f"{s.course_id:32}  {s.origin:7}  {s.path}")
    return 0


def cmd_lecture(args: argparse.Namespace) -> int:
    plan = parse_lesson_plan(args.course_id)
    payload = lecture_payload(plan, week=args.week)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _safe_console() -> None:
    """Never crash on a character the console/pipe encoding can't show (Windows cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_console()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--source-root",
        default=argparse.SUPPRESS,
        help="Folder that ${SOURCE_ROOT} in course files points to on this machine "
        "(overrides the AITUTOR_SOURCE_ROOT environment variable).",
    )
    common.add_argument("--model", default=argparse.SUPPRESS,
                        help=f"Ollama model (env {settings.MODEL_ENV}; default {settings.DEFAULT_MODEL})")
    common.add_argument("--ollama-url", default=argparse.SUPPRESS,
                        help=f"Ollama server URL (env {settings.URL_ENV}; default {settings.DEFAULT_URL})")
    common.add_argument("--num-ctx", type=int, default=argparse.SUPPRESS,
                        help=f"Model context window in tokens (env {settings.NUM_CTX_ENV}; default {settings.DEFAULT_NUM_CTX})")
    p = argparse.ArgumentParser(
        prog="aitutor", description="AiTutor: build courses from your own material and learn them with a local model",
        parents=[common],
    )
    p.add_argument("--version", action="version", version=f"aitutor {__version__}")
    subparsers = p.add_subparsers(dest="cmd", required=False)

    def add_command(name: str, **kw) -> argparse.ArgumentParser:
        # Every command also accepts --source-root, before or after its name.
        return subparsers.add_parser(name, parents=[common], **kw)

    s = add_command("list", help="List baked + built course ids")
    s.set_defaults(func=cmd_list)

    s = add_command("show", help="Show parsed lesson plan")
    s.add_argument("course_id")
    s.set_defaults(func=cmd_show)

    s = add_command("start", help="Open a session and print opening + prompt bundle")
    s.add_argument("course_id")
    s.add_argument("--week", default=None)
    s.set_defaults(func=cmd_start)

    s = add_command("session", help="Free-form tutoring chat for a course (local model if available)")
    s.add_argument("course_id")
    s.add_argument("--week", default=None)
    s.add_argument("--name", default="learner")
    s.add_argument("--host", default="auto", choices=["auto", "ollama", "none"],
                   help="auto: use Ollama when ready, else offline replies (default)")
    s.set_defaults(func=cmd_session)

    s = add_command("tui", help="Standalone app: check → pick source → build → learn")
    s.add_argument("--full", action="store_true",
                   help="Force the full-screen UI (needs: pip install \"aitutor[tui]\")")
    s.add_argument("--plain", action="store_true", help="Force the guided line-mode UI")
    s.set_defaults(func=cmd_tui)

    s = add_command("learn", help="Interactive lesson/practice/check/review for a built course")
    s.add_argument("course_id")
    s.add_argument("--week", default=None, help="Start at this unit (number or title substring)")
    s.add_argument("--name", default="learner")
    s.set_defaults(func=cmd_learn)

    s = add_command("doctor", help="Check this computer meets the requirements (no changes)")
    s.add_argument("--json", action="store_true", help="Machine-readable output")
    s.set_defaults(func=cmd_doctor)

    s = add_command("setup", help="Guided first-run setup: check, start Ollama, download the model")
    s.add_argument("--yes", "-y", action="store_true", help="Accept the offered fixes without asking")
    s.set_defaults(func=cmd_setup)

    s = add_command("manifest", help="NOVA module manifest JSON")
    s.set_defaults(func=cmd_manifest)

    s = add_command("roots", help="Show source roots resolved on this machine")
    s.set_defaults(func=cmd_roots)

    s = add_command("paths", help="Show where AiTutor finds and stores files on this machine")
    s.set_defaults(func=cmd_paths)

    s = add_command("verify", help="Check built-course hashes and source files on this machine")
    s.add_argument("course_id", nargs="?", default=None)
    s.set_defaults(func=cmd_verify)

    s = add_command(
        "build",
        help="Assemble course-builder prompt pack from subject + raw materials",
    )
    s.add_argument("--subject", default=None)
    s.add_argument("--learner", default="adult professional")
    s.add_argument("--goal", default="increase practical self-sufficiency")
    s.add_argument("--audience", default="adult", choices=["adult", "child", "mixed"])
    s.add_argument("--file", action="append", default=[])
    s.add_argument("--paste", default=None)
    s.add_argument("--paste-title", default=None)
    s.add_argument("--stdin-paste", action="store_true")
    s.add_argument("--notes", default=None)
    s.add_argument("--out", default=None)
    s.add_argument("--source", default=None, help="A file or folder of source material")
    s.add_argument("--host", default="none", choices=["none", "ollama"],
                   help="none: write a prompt pack (default); ollama: build the course with the local model")
    s.add_argument("--import", dest="do_import", action="store_true",
                   help="With --host ollama: save the built course into AITUTOR_HOME")
    s.add_argument("--force", action="store_true", help="Replace a course with the same id (keeps a backup)")
    s.add_argument("--course-id", default=None, help="Course id to use instead of the model's")
    s.add_argument("--anyway", action="store_true",
                   help="Build even if the material looks too thin, unreadable or off-subject")
    s.set_defaults(func=cmd_build)

    s = add_command(
        "import-course",
        help="Save a model's course JSON (file or stdin) into AITUTOR_HOME/courses/built/",
    )
    s.add_argument("--file", default=None)
    s.add_argument("--force", action="store_true", help="Replace an existing course (keeps a .bak copy)")
    s.set_defaults(func=cmd_import)

    s = add_command("built", help="List model-built courses (bundled and yours)")
    s.set_defaults(func=cmd_built)

    s = add_command("lecture", help="NOVA lecture payload for a baked or built course week")
    s.add_argument("course_id")
    s.add_argument("--week", default=None)
    s.set_defaults(func=cmd_lecture)

    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        print(
            "AiTutor — build a course from your own material, then learn it with a local model.\n\n"
            "  aitutor setup          check Ollama + download the model\n"
            "  aitutor doctor         re-check requirements (no changes)\n"
            "  aitutor build --source <file-or-folder> --host ollama --import\n"
            "  aitutor learn <course>  lesson → practice → check → review\n"
            "  aitutor tui            the standalone app (full-screen with aitutor[tui])\n"
            "  aitutor session <id>    free-form tutoring chat\n\n"
            "Run aitutor --help for every command."
        )
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                go = input("\nOpen the AiTutor interface now? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return 0
            if go in ("", "y", "yes"):
                from aitutor.tui import launch

                return launch()
        return 0
    if getattr(args, "source_root", None):
        paths.set_source_root(args.source_root)
    settings.set_overrides(
        model=getattr(args, "model", None),
        url=getattr(args, "ollama_url", None),
        num_ctx=getattr(args, "num_ctx", None),
    )
    try:
        return int(args.func(args))
    except llm_host.HostError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except KeyError as exc:
        print(f"error: {exc.args[0]}. Run `aitutor list` to see course ids.", file=sys.stderr)
        return 2
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        # main() is also called in-process (tests, the TUI): don't leak flags.
        paths.set_source_root(None)
        settings.clear_overrides()


if __name__ == "__main__":
    sys.exit(main())