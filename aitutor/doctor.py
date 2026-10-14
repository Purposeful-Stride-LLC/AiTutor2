"""Requirements check and guided setup (``aitutor doctor`` / ``aitutor setup``).

Checks that this computer can run AiTutor with a local model:
Python, the AiTutor data folder, Ollama (installed, running) and the configured
model. Anything missing comes with the exact command to fix it for this OS.
Nothing is installed without asking; Ollama itself is never installed for you.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from aitutor import llm_host
from aitutor.paths import aitutor_home
from aitutor.settings import Settings, resolve

OK, MISSING, INFO = "ok", "missing", "info"


@dataclass
class Check:
    key: str
    label: str
    status: str  # ok | missing | info
    detail: str
    fix: list[str] = field(default_factory=list)


@dataclass
class Report:
    settings: Settings
    checks: list[Check]
    installed_models: list[str] = field(default_factory=list)
    ollama_binary: str | None = None

    @property
    def ready(self) -> bool:
        return all(c.status != MISSING for c in self.checks)

    def get(self, key: str) -> Check | None:
        return next((c for c in self.checks if c.key == key), None)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "model": self.settings.model,
            "url": self.settings.url,
            "num_ctx": self.settings.num_ctx,
            "installed_models": self.installed_models,
            "ollama_binary": self.ollama_binary,
            "checks": [asdict(c) for c in self.checks],
        }


def os_kind(name: str | None = None) -> str:
    n = (name or platform.system()).lower()
    if n.startswith("win") or n == "nt":
        return "windows"
    if n == "darwin":
        return "macos"
    return "linux"


def install_commands(kind: str) -> list[str]:
    if kind == "windows":
        return [
            "winget install --id Ollama.Ollama -e",
            "or download the installer: https://ollama.com/download/windows",
        ]
    if kind == "macos":
        return ["brew install ollama", "or download the app: https://ollama.com/download/mac"]
    return ["curl -fsSL https://ollama.com/install.sh | sh", "details: https://ollama.com/download/linux"]


def start_commands(kind: str) -> list[str]:
    if kind == "windows":
        return ["Open 'Ollama' from the Start menu (it runs in the system tray)", "or run: ollama serve"]
    if kind == "macos":
        return ["open -a Ollama", "or run: ollama serve"]
    return ["sudo systemctl start ollama", "or run: ollama serve"]


def find_ollama_binary() -> Path | None:
    """The ollama executable: PATH first, then the installer's usual location."""
    found = shutil.which("ollama")
    if found:
        return Path(found)
    candidates: list[Path] = []
    if os_kind() == "windows":
        for env, sub in (("LOCALAPPDATA", ("Programs", "Ollama")), ("ProgramFiles", ("Ollama",))):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base, *sub, "ollama.exe"))
    elif os_kind() == "macos":
        candidates.append(Path("/Applications/Ollama.app/Contents/Resources/ollama"))
    else:
        candidates += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")]
    return next((c for c in candidates if c.is_file()), None)


def _gpu_info() -> str | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0] if out else None


def _writable_home() -> tuple[bool, Path]:
    home = aitutor_home()
    probe = home
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return os.access(probe, os.W_OK), home


def run_checks(settings: Settings | None = None, *, os_name: str | None = None, gpu: bool = True) -> Report:
    s = settings or resolve()
    kind = os_kind(os_name)
    checks: list[Check] = []

    v = sys.version_info
    checks.append(Check(
        "python", "Python 3.11 or newer",
        OK if v >= (3, 11) else MISSING,
        f"Python {v.major}.{v.minor}.{v.micro}",
        [] if v >= (3, 11) else ["Install Python 3.11+ from https://www.python.org/downloads/"],
    ))

    ok_home, home = _writable_home()
    checks.append(Check(
        "home", "AiTutor data folder", OK if ok_home else MISSING, str(home),
        [] if ok_home else [f"Make {home} writable, or set AITUTOR_HOME to a folder you own"],
    ))

    binary = find_ollama_binary()
    version = None
    try:
        version = llm_host.server_version(s, timeout=3)
    except llm_host.HostError:
        pass

    if binary or version:
        checks.append(Check(
            "ollama_installed", "Ollama installed", OK,
            str(binary) if binary else "server reachable (ollama CLI not on PATH)",
        ))
    else:
        checks.append(Check(
            "ollama_installed", "Ollama installed", MISSING, "ollama not found on this computer",
            install_commands(kind),
        ))

    models: list[str] = []
    if version:
        checks.append(Check("ollama_running", "Ollama running", OK, f"version {version} at {s.url}"))
        try:
            models = llm_host.list_models(s)
        except llm_host.HostError:
            models = []
        want = s.model if ":" in s.model else f"{s.model}:latest"
        have = want in {m if ":" in m else f"{m}:latest" for m in models}
        fix = [] if have else [f"ollama pull {s.model}"] + (
            [f"or use a model you already have: aitutor setup --model {models[0]}"] if models else []
        )
        checks.append(Check(
            "model", f"Model {s.model}", OK if have else MISSING,
            f"installed ({s.origin.get('model', 'default')} setting)" if have else "not downloaded yet",
            fix,
        ))
    else:
        checks.append(Check(
            "ollama_running", "Ollama running", MISSING, f"nothing answering at {s.url}",
            start_commands(kind) if binary else ["Install Ollama first (see above)"],
        ))
        checks.append(Check(
            "model", f"Model {s.model}", MISSING, "can't check until Ollama is running",
            [f"then: ollama pull {s.model}"],
        ))

    if gpu:
        g = _gpu_info()
        checks.append(Check(
            "gpu", "GPU", INFO, g or "no NVIDIA GPU detected (CPU works, just slower)",
            [] if g else ["Optional. Ollama also uses AMD/Apple GPUs where supported."],
        ))
    try:
        import textual  # noqa: F401
        tui = (OK, "full-screen interface available")
    except ImportError:
        tui = (INFO, "not installed; `aitutor tui` uses the plain interface")
    checks.append(Check("tui", "Full-screen TUI (optional)", tui[0], tui[1],
                        [] if tui[0] == OK else ['pip install "aitutor[tui]"']))
    from aitutor.pipeline.ingest import pdf_supported

    checks.append(Check(
        "pdf", "PDF sources (optional)", OK if pdf_supported() else INFO,
        "PDF reading available" if pdf_supported() else "not installed; text/Markdown/HTML still work",
        [] if pdf_supported() else ['pip install "aitutor[pdf]"'],
    ))
    return Report(settings=s, checks=checks, installed_models=models,
                  ollama_binary=str(binary) if binary else None)


def format_report(report: Report) -> str:
    mark = {OK: "[ok]  ", MISSING: "[!!]  ", INFO: "[--]  "}
    lines = [f"AiTutor requirements check  (model {report.settings.model} at {report.settings.url}, "
             f"num_ctx {report.settings.num_ctx})", ""]
    for c in report.checks:
        lines.append(f"{mark[c.status]}{c.label}: {c.detail}")
        for f in c.fix:
            lines.append(f"        {f}")
    lines.append("")
    lines.append("Ready: AiTutor can build and teach with the local model." if report.ready
                 else "Not ready yet: follow the steps marked [!!], then run `aitutor setup` again.")
    return "\n".join(lines)


def start_ollama(binary: str, settings: Settings | None = None, wait: float = 20.0) -> bool:
    """Start ``ollama serve`` in the background; True once the API answers."""
    s = settings or resolve()
    log_dir = aitutor_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "ollama-serve.log", "ab")
    kwargs: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if os_kind() == "windows":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([binary, "serve"], **kwargs)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            llm_host.server_version(s, timeout=2)
            return True
        except llm_host.HostError:
            time.sleep(0.5)
    return False


def pull_with_progress(model: str, settings: Settings | None = None,
                       write: Callable[[str], None] | None = None) -> None:
    out = write or (lambda t: (sys.stdout.write(t), sys.stdout.flush()))
    live = sys.stdout.isatty()
    last = [""]

    def progress(status: str, done: int | None, total: int | None) -> None:
        if total and done is not None:
            line = f"  {status}: {done / total:5.1%} of {total / 1e9:.1f} GB"
        else:
            line = f"  {status}"
        if live:
            out("\r" + line.ljust(70))
        elif status != last[0]:
            out(line + "\n")
        last[0] = status

    llm_host.pull(model, settings, on_progress=progress)
    if live:
        out("\n")


def _ask(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{question} [Y/n] y")
        return True
    if not sys.stdin.isatty():
        print(f"{question} [Y/n] (no terminal; skipped, use --yes to accept)")
        return False
    try:
        answer = input(f"{question} [Y/n] ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def interactive_setup(assume_yes: bool = False) -> int:
    """Check, then offer the fixes AiTutor can safely do itself."""
    report = run_checks()
    print(format_report(report))
    s = report.settings
    running = report.get("ollama_running")
    if running and running.status == MISSING and report.ollama_binary:
        print()
        if _ask("Ollama is installed but not running. Start it now?", assume_yes):
            if start_ollama(report.ollama_binary, s):
                print("Ollama started.")
            else:
                print("Ollama did not answer within 20 seconds. Start it yourself:")
                for line in start_commands(os_kind()):
                    print(f"  {line}")
                return 1
            report = run_checks(s, gpu=False)
    model = report.get("model")
    if model and model.status == MISSING and report.get("ollama_running").status == OK:
        print()
        if _ask(f"Download the model {s.model} now? (several GB, one time)", assume_yes):
            pull_with_progress(s.model, s)
            report = run_checks(s, gpu=False)
            print()
            print(format_report(report))
    return 0 if report.ready else 1
