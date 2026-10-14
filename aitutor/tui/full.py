"""Full-screen terminal UI (optional extra: ``pip install "aitutor[tui]"``).

Same flow as the guided UI, in one window:
requirements check → pick a file/folder → build with the local model →
lesson / practice / check / review, streaming from Ollama.
"""

from __future__ import annotations

import time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    OptionList,
    ProgressBar,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from aitutor import doctor, llm_host, paths, settings
from aitutor.pedagogy import PHASES, LearnSession
from aitutor.pipeline.autobuild import WeakSourceError, build_course, source_root_for
from aitutor.pipeline.builder import BuildRequest
from aitutor.pipeline.course_store import list_built
from aitutor.pipeline.ingest import explain_unusable, ingest_source, scan_folder

CSS = """
Screen { background: $surface; }
#title { padding: 1 2; text-style: bold; color: $accent; }
#report { padding: 0 2; height: auto; }
.buttons { height: auto; padding: 1 2; }
.buttons Button { margin-right: 2; }
#pullbar { margin: 0 2; }
#home-list { margin: 1 2; height: 1fr; }
#pick-left { width: 2fr; }
#pick-right { width: 1fr; padding: 0 1; }
#tree { height: 1fr; border: round $primary; }
#selection { padding: 1 0; height: auto; max-height: 8; }
#build { margin: 1 0 0 0; }
#buildlog { padding: 1 2; height: 1fr; }
#units { width: 40; border: round $primary; }
#chat { height: 1fr; border: round $primary; padding: 0 1; }
#phase { padding: 0 1; height: auto; color: $accent; text-style: bold; }
.tutor { margin: 0 0 1 0; }
.learner { margin: 0 0 1 0; color: $text-muted; }
"""

MARK = {doctor.OK: "[green]✔[/]", doctor.MISSING: "[red]✘[/]", doctor.INFO: "[yellow]•[/]"}


class CheckScreen(Screen):
    """Startup: does this computer meet the requirements?"""

    BINDINGS = [Binding("r", "recheck", "Re-check")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Requirements check", id="title")
        yield Static("Checking…", id="report")
        with Horizontal(classes="buttons"):
            yield Button("Continue", id="continue", variant="primary", disabled=True)
            yield Button("Download model", id="pull", disabled=True)
            yield Button("Start Ollama", id="start", disabled=True)
            yield Button("Re-check", id="recheck")
        yield ProgressBar(id="pullbar", total=100, show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#pullbar").display = False
        self.action_recheck()

    def action_recheck(self) -> None:
        self.query_one("#report", Static).update("Checking…")
        self._check()

    @work(thread=True, exclusive=True)
    def _check(self) -> None:
        report = doctor.run_checks()
        self.app.call_from_thread(self._show, report)

    def _show(self, report: doctor.Report) -> None:
        self.app.report = report
        lines = []
        for c in report.checks:
            lines.append(f"{MARK[c.status]} [b]{c.label}[/b]: {c.detail}")
            for f in c.fix:
                lines.append(f"     [dim]{f}[/]")
        lines.append("")
        lines.append("[green b]Ready.[/] Press Continue." if report.ready
                     else "[red b]Not ready.[/] Use the buttons, or follow the steps above, then Re-check.")
        self.query_one("#report", Static).update("\n".join(lines))
        running = report.get("ollama_running")
        model = report.get("model")
        self.query_one("#continue", Button).disabled = not report.ready
        self.query_one("#pull", Button).disabled = not (
            running and running.status == doctor.OK and model and model.status == doctor.MISSING
        )
        self.query_one("#pull", Button).label = f"Download {report.settings.model}"
        self.query_one("#start", Button).disabled = not (
            running and running.status == doctor.MISSING and report.ollama_binary
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "continue":
            self.app.push_screen(HomeScreen())
        elif bid == "recheck":
            self.action_recheck()
        elif bid == "pull":
            event.button.disabled = True
            bar = self.query_one("#pullbar", ProgressBar)
            bar.display = True
            self._pull()
        elif bid == "start":
            event.button.disabled = True
            self._start()

    @work(thread=True, exclusive=True)
    def _pull(self) -> None:
        s = self.app.report.settings
        bar = self.query_one("#pullbar", ProgressBar)

        def progress(status: str, done: int | None, total: int | None) -> None:
            if total:
                self.app.call_from_thread(bar.update, total=total, progress=done or 0)
            self.app.call_from_thread(
                self.query_one("#title", Static).update, f"Downloading {s.model}: {status}"
            )

        try:
            llm_host.pull(s.model, s, on_progress=progress)
        except llm_host.HostError as exc:
            self.app.call_from_thread(self.app.notify, str(exc), severity="error")
        self.app.call_from_thread(self.query_one("#title", Static).update, "Requirements check")
        self.app.call_from_thread(self.action_recheck)

    @work(thread=True, exclusive=True)
    def _start(self) -> None:
        r = self.app.report
        ok = doctor.start_ollama(r.ollama_binary, r.settings)
        if not ok:
            self.app.call_from_thread(self.app.notify, "Ollama did not start in 20 s.", severity="error")
        self.app.call_from_thread(self.action_recheck)


class HomeScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("What would you like to do?", id="title")
        yield OptionList(id="home-list")
        yield Footer()

    def on_screen_resume(self) -> None:
        self._fill()

    def on_mount(self) -> None:
        self._fill()

    def _fill(self) -> None:
        ol = self.query_one(OptionList)
        ol.clear_options()
        ol.add_option(Option("➕  Build a new course from a file or folder", id="new"))
        for c in list_built():
            title = str(c.data.get("title") or c.course_id)
            units = len(c.data.get("weeks") or [])
            ol.add_option(Option(f"📘  {title}   [{units} units, {c.origin}]", id=f"open:{c.course_id}"))
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        oid = event.option.id or ""
        if oid == "new":
            self.app.push_screen(PickScreen(self.app.start_dir))
        elif oid.startswith("open:"):
            self.app.push_screen(LearnScreen(oid.split(":", 1)[1]))


class PickScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, start: Path) -> None:
        super().__init__()
        self.start = start
        self.selected: Path | None = None
        self.default_subject = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Pick your source material (a file or a whole folder)", id="title")
        with Horizontal():
            with Vertical(id="pick-left"):
                yield Input(placeholder="Type a path and press Enter (any drive or folder)", id="path")
                yield DirectoryTree(str(self.start), id="tree")
            with VerticalScroll(id="pick-right"):
                # Build sits at the top so it stays on screen even in an 80x24 terminal.
                yield Button("Build course", id="build", variant="primary", disabled=True)
                yield Static("Nothing selected yet.", id="selection")
                yield Label("Subject")
                yield Input(id="subject")
                yield Label("Audience")
                yield Select([("Adult", "adult"), ("Child (K–12)", "child"), ("Mixed", "mixed")],
                             value="adult", allow_blank=False, id="audience")
                yield Label("Goal")
                yield Input(value="increase practical self-sufficiency", id="goal")
        yield Footer()

    def _select(self, p: Path) -> None:
        self.selected = p
        if p.is_dir():
            scan = scan_folder(p)
            names = "\n".join(f"  • {f.relative_to(p)}" for f in scan.files[:10])
            more = f"\n  … and {len(scan.files) - 10} more" if len(scan.files) > 10 else ""
            skipped = f"\n[dim]skipped {len(scan.skipped)} unsupported file(s)[/]" if scan.skipped else ""
            self.query_one("#selection", Static).update(
                f"[b]Folder[/b] {p}\n{len(scan.files)} usable file(s)\n{names}{more}{skipped}")
            ok = bool(scan.files)
        else:
            self.query_one("#selection", Static).update(f"[b]File[/b] {p}\n{p.stat().st_size:,} bytes")
            ok = True
        subj = self.query_one("#subject", Input)
        if not subj.value or subj.value == self.default_subject:
            self.default_subject = p.stem.replace("_", " ").replace("-", " ").title()
            subj.value = self.default_subject
        self.query_one("#build", Button).disabled = not ok

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self._select(Path(event.path))

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self._select(Path(event.path))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "path":
            return
        raw = event.value.strip().strip('"').strip("'")
        try:
            p = paths.resolve_input_path(raw)
        except FileNotFoundError as exc:
            self.app.notify(str(exc), severity="error")
            return
        if p.is_dir():
            self.query_one("#tree", DirectoryTree).path = p
        self._select(p)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "build" and self.selected:
            subject = self.query_one("#subject", Input).value.strip()
            self.app.push_screen(BuildScreen(
                self.selected,
                subject or self.selected.stem,
                str(self.query_one("#audience", Select).value),
                self.query_one("#goal", Input).value,
                subject_given=bool(subject) and subject != self.default_subject,
            ))


class BuildScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, source: Path, subject: str, audience: str, goal: str, *, subject_given: bool = True) -> None:
        super().__init__()
        self.source, self.subject, self.audience, self.goal = source, subject, audience, goal
        self.subject_given = subject_given
        self.course_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Building “{self.subject}”", id="title")
        yield Static("", id="buildlog")
        with Horizontal(classes="buttons"):
            yield Button("Start learning", id="learn", variant="primary", disabled=True)
            yield Button("Build anyway", id="anyway", variant="warning")
            yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#anyway", Button).display = False
        self._build()

    def _log(self, text: str) -> None:
        self.query_one("#buildlog", Static).update(text)

    @work(thread=True, exclusive=True)
    def _build(self, anyway: bool = False) -> None:
        cfg = settings.resolve()
        lines = [f"Source: {self.source}", f"Model: {cfg.model}  (num_ctx {cfg.num_ctx})", ""]
        say = lambda extra="": self.app.call_from_thread(self._log, "\n".join(lines + ([extra] if extra else [])))
        paths.set_source_root(source_root_for(self.source))
        try:
            materials, skipped = ingest_source(self.source)
            lines.append(f"Read {len(materials)} source file(s)" + (f", skipped {len(skipped)}" if skipped else ""))
            if not materials:
                lines.append(f"[red]Cannot build:[/] {explain_unusable(self.source, skipped)}")
                say()
                return
            say()
            req = BuildRequest(subject=self.subject, audience=self.audience, goal=self.goal, materials=materials,
                               subject_given=self.subject_given)
            got = [0, time.monotonic()]

            def tick(piece: str) -> None:
                got[0] += len(piece)
                if time.monotonic() - got[1] > 0.2:
                    got[1] = time.monotonic()
                    say(f"Model is writing the course… {got[0]} characters")

            result = build_course(req, cfg, on_token=tick, anyway=anyway)
        except WeakSourceError as exc:
            lines.append(f"[yellow b]Check your material.[/] {exc.assessment.message()}.")
            lines.append("Press [b]Build anyway[/] to build from it, or Back to pick something else.")
            say()
            self.app.call_from_thread(setattr, self.query_one("#anyway", Button), "display", True)
            return
        except (llm_host.HostError, ValueError, OSError) as exc:
            lines.append(f"[red]Build failed:[/] {exc}")
            say()
            return
        except Exception as exc:  # a model glitch must never take the app down
            lines.append(f"[red]Build failed (unexpected {type(exc).__name__}):[/] {exc}")
            say()
            return
        finally:
            paths.set_source_root(None)
        c = result.stored.data
        self.course_id = result.stored.course_id
        lines.append(f"[green]Saved[/] {self.course_id}: [b]{c['title']}[/b]  ({len(c['weeks'])} units)")
        for w in c["weeks"]:
            lines.append(f"  {w['week']}. {w['title']}  [dim]{', '.join(w['source_ids'])}[/]")
        for wmsg in result.warnings:
            lines.append(f"[yellow]note:[/] {wmsg}")
        say()
        self.app.call_from_thread(setattr, self.query_one("#learn", Button), "disabled", False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "learn" and self.course_id:
            self.app.switch_screen(LearnScreen(self.course_id))
        elif event.button.id == "anyway":
            event.button.display = False
            self._build(anyway=True)
        elif event.button.id == "back":
            self.app.pop_screen()


class LearnScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "next_phase", "Next phase", priority=True),
        Binding("ctrl+p", "prev_unit", "Previous unit", priority=True),
        Binding("escape", "home", "Home"),
    ]

    def __init__(self, course_id: str) -> None:
        super().__init__()
        self.course_id = course_id
        self.session: LearnSession | None = None
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="units")
            with Vertical():
                yield Static("Opening course…", id="phase")
                yield VerticalScroll(id="chat")
                yield Input(placeholder="Ask a question, or paste your practice work. Ctrl+N = next phase", id="msg")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.session = LearnSession.start(self.course_id)
        except (KeyError, ValueError) as exc:
            self.app.notify(str(exc), severity="error")
            self.app.pop_screen()
            return
        self.title = self.session.course.title
        self._refresh_side()
        missing = [s for s in self.session.grounding.status if not s.found]
        if missing:
            self._add("learner", f"⚠ {len(missing)} source file(s) not found on this computer — "
                                 "teaching from the course plan for those.")
        self._run()

    def _refresh_side(self) -> None:
        s = self.session
        lv = self.query_one("#units", ListView)
        lv.clear()
        for i, u in enumerate(s.course.units):
            mark = "▶" if i == s.unit_index else ("✔" if i < s.unit_index else " ")
            lv.append(ListItem(Label(f"{mark} {u.week}. {u.title}")))
        steps = "  ›  ".join(f"[reverse] {p} [/]" if p == s.phase else p for p in PHASES)
        score = f"   score {s.last_score}/10" if s.last_score is not None else ""
        self.query_one("#phase", Static).update(
            f"Unit {s.unit.week}: {s.unit.title}\n{steps}{score}")

    def _add(self, who: str, text: str) -> Markdown:
        md = Markdown(text, classes=who)
        self.query_one("#chat", VerticalScroll).mount(md)
        self.query_one("#chat", VerticalScroll).scroll_end(animate=False)
        return md

    @work(thread=True, exclusive=True)
    def _run(self, user_text: str | None = None) -> None:
        self.busy = True
        md = self.app.call_from_thread(self._add, "tutor", "…")
        buf = [""]
        last = [0.0]

        def tok(piece: str) -> None:
            buf[0] += piece
            if time.monotonic() - last[0] > 0.15:
                last[0] = time.monotonic()
                self.app.call_from_thread(md.update, buf[0])
                self.app.call_from_thread(self.query_one("#chat", VerticalScroll).scroll_end, animate=False)

        try:
            if user_text and self.session.phase == "practice":
                self.app.call_from_thread(self._mark_check)
                reply = self.session.submit_practice(user_text, on_token=tok)
            else:
                reply = self.session.ask(user_text, on_token=tok)
        except llm_host.HostError as exc:
            reply = f"**Model error:** {exc}"
        except Exception as exc:  # never let one bad reply kill the app
            reply = f"**Something went wrong** ({type(exc).__name__}: {exc}). Try again or press Ctrl+N."
        self.app.call_from_thread(md.update, reply)
        self.app.call_from_thread(self._refresh_side)
        self.app.call_from_thread(self.query_one("#chat", VerticalScroll).scroll_end, animate=False)
        self.busy = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if self.busy:
            # Keep what they typed; it is sent when they press Enter again.
            self.app.notify("The tutor is still answering. Your text is kept; press Enter again when it's done.")
            return
        event.input.value = ""
        if text in ("/next", "/skip"):
            self.action_next_phase()
            return
        self._add("learner", f"**You:** {text}")
        self._run(text)

    def _mark_check(self) -> None:
        self.query_one("#phase", Static).update(
            f"Unit {self.session.unit.week}: {self.session.unit.title}\nchecking your work…")

    def action_next_phase(self) -> None:
        if self.busy:
            return
        msg = self.session.advance()
        self._add("learner", f"*{msg}*")
        self._refresh_side()
        if self.session.phase in ("lesson", "practice", "review"):
            self._run()

    def action_prev_unit(self) -> None:
        if self.busy:
            return
        if self.session.unit_index == 0:
            self.app.notify("Already at the first unit.")
            return
        self._add("learner", f"*{self.session.set_unit(-1)}*")
        self._refresh_side()
        self._run()

    def action_home(self) -> None:
        # Back to Home, however we got here (Home → Pick → Build → Learn, or Home → Learn).
        stack = self.app.screen_stack
        homes = [i for i, sc in enumerate(stack) if isinstance(sc, HomeScreen)]
        pops = len(stack) - 1 - homes[-1] if homes else 1
        for _ in range(max(1, pops)):
            self.app.pop_screen()


class AiTutorApp(App):
    TITLE = "AiTutor"
    # Textual's command palette also wants ctrl+p; AiTutor uses ctrl+p for "previous unit".
    ENABLE_COMMAND_PALETTE = False
    SUB_TITLE = "your material, your machine"
    CSS = CSS
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, start_dir: Path | None = None) -> None:
        super().__init__()
        self.start_dir = start_dir or Path.home()
        self.report: doctor.Report | None = None

    def on_mount(self) -> None:
        self.push_screen(CheckScreen())


def run() -> int:
    AiTutorApp(start_dir=paths.source_root()[0] if paths.source_root()[1] != "cwd" else Path.home()).run()
    return 0
