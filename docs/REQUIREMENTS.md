# AiTutor requirements

This document lists what AiTutor needs to work. It assumes only the computer
AiTutor is installed on: its own install folder, its own user profile, and
whatever folders you choose to point it at. Nothing depends on a particular
drive letter, user name, or directory layout.

## Required

| Item | Version / detail | Why |
| --- | --- | --- |
| Python | **3.11 or newer** (tested on 3.13 / Linux and 3.14 / Windows) | AiTutor is Python; its core uses only the standard library |
| pip + venv | ship with Python. Debian/Ubuntu: `sudo apt install python3-venv` | installing into an isolated environment |
| **Ollama** | any recent version (tested with 0.40) | runs the local model that builds courses and teaches |
| **A chat model in Ollama** | default **`qwen3:8b`** (≈5 GB download) | the model AiTutor talks to; configurable |
| Disk | ≈1 MB for AiTutor, plus the model (≈5 GB for `qwen3:8b`) | |

`aitutor setup` checks every row above and tells you exactly what to do for
anything missing. AiTutor needs no administrator or root rights; installing
Ollama itself may.

### Getting Ollama and the model

| | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Install Ollama | `winget install --id Ollama.Ollama -e` or the installer from ollama.com/download/windows | `curl -fsSL https://ollama.com/install.sh \| sh` | `brew install ollama` or the app from ollama.com/download/mac |
| Start it | Open **Ollama** from the Start menu (tray icon), or `ollama serve` | `sudo systemctl start ollama`, or `ollama serve` | `open -a Ollama`, or `ollama serve` |
| Get the model | `ollama pull qwen3:8b` | same | same |

`aitutor setup` offers to start Ollama (if it's installed but not running) and
to download the model (if Ollama is running). It never installs Ollama for you.

### Hardware

| Setup | What to expect with `qwen3:8b` at 8K context |
| --- | --- |
| NVIDIA/AMD GPU with **8 GB** VRAM | Runs fully on the GPU (≈6 GB used). Building a course from a book-sized folder took ≈12 s on an 8 GB RTX laptop GPU; a tutor reply takes a few seconds |
| GPU with less VRAM | Ollama splits the model between GPU and CPU: works, slower. Consider a smaller model (`aitutor setup --model qwen3:4b`) |
| CPU only, 16 GB RAM | Works, but expect around a minute per reply |

A larger context (`--num-ctx 16384`) lets more of your material reach the model,
and needs more memory.

## Optional

| Item | When you need it |
| --- | --- |
| `textual` (extra `tui`) | the full-screen interface: `pip install -e ".[tui]"`. Without it, `aitutor tui` uses the guided line-mode interface |
| `pypdf` (extra `pdf`) | reading PDF sources: `pip install -e ".[pdf]"`. Without it, PDFs are listed as skipped |
| git | to clone the repository (you can also download a ZIP) |
| `pytest` | to run the tests: `pip install -e ".[dev]"` (also installs both extras) |
| A folder of source material | anything you want to learn: notes, manuals, books (text, Markdown, HTML, PDF with a text layer) |

## Supported systems

| System | Status | Notes |
| --- | --- | --- |
| Windows 10 / 11 | supported | PowerShell, Windows Terminal, or `cmd.exe`. The `py` launcher or `python` both work. The full-screen interface looks best in Windows Terminal |
| Linux (any distribution with Python 3.11+) | supported | Debian/Ubuntu, Fedora, Arch, etc. Use the distro's Python or one from pyenv/conda |
| macOS | expected to work | same commands as Linux. Not part of the test matrix yet |
| WSL | supported, as Linux | WSL has its own home folder, so its `AITUTOR_HOME` is separate from the Windows one. Point `AITUTOR_OLLAMA_URL` at the Windows Ollama if you run it there |

## What AiTutor reads and writes on your machine

AiTutor uses three locations, all resolved when it runs (`aitutor paths`
prints them):

1. **Install folder** (read-only to AiTutor). The `aitutor` package with its
   bundled courses, prompts, and example source layout. Found through
   `importlib.resources`, so any install location works: a clone, a virtual
   environment, system site-packages, or a read-only/shared install.

2. **`AITUTOR_HOME`** (read-write). Your imported courses
   (`courses/built/*.json`) and an optional personal `roots.json`.
   - Set it explicitly with the `AITUTOR_HOME` environment variable, or accept the default:
   - **Windows:** `%APPDATA%\aitutor` (falls back to `<your profile>\AppData\Roaming\aitutor`)
   - **Linux / macOS:** `~/.aitutor`
   - Created automatically the first time you import a course.

3. **Source root** (read-only to AiTutor). The top folder of your source
   material. Course files refer to it as `${SOURCE_ROOT}`. Resolved in this order:
   1. `--source-root <folder>` on the command line
   2. the `AITUTOR_SOURCE_ROOT` environment variable
   3. the current directory (AiTutor prints a note when it falls back to this)

AiTutor also writes any file you name with `--out`. It never writes into the
install folder or the git checkout.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AITUTOR_HOME` | `%APPDATA%\aitutor` / `~/.aitutor` | your courses, settings (`config.json`), course folders (`course_roots.json`), PDF text cache, personal `roots.json` |
| `AITUTOR_SOURCE_ROOT` | current directory (or the folder remembered for a course) | what `${SOURCE_ROOT}` means on this machine |
| `AITUTOR_MODEL` | `qwen3:8b` | Ollama model name |
| `AITUTOR_OLLAMA_URL` | `http://127.0.0.1:11434` | where Ollama is listening |
| `AITUTOR_NUM_CTX` | `8192` | model context window in tokens |

The two folder variables accept `~` and any absolute path, including other drives, network shares
(`\\server\share\...` on Windows), and mounted volumes on Linux. Paths with spaces
or non-English characters are fine.

## Path conventions inside course files

- Locators under the source root are stored as `${SOURCE_ROOT}/sub/folder/file.ext`.
  The forms `$SOURCE_ROOT` and `%SOURCE_ROOT%` are also accepted, and `/` and `\` are
  interchangeable, so a course authored on Windows resolves on Linux and vice versa.
- Relative locators (`Ebooks/book.pdf`) resolve against the source root.
- On the command line (`build --file`, `--paste`), a relative path is tried in the
  current directory first, then under the source root. If neither exists, the
  error lists both places it looked.
- `paste://...` and URLs are citations, not files, and are never opened.
- Files outside the source root keep their absolute path. That only works on the
  machine that created them, so set a source root before sharing courses.

## Console text on Windows

Course titles contain characters such as `–` and `’`. If they show up garbled
in an older console, use Windows Terminal, or run
`$env:PYTHONIOENCODING = "utf-8"` (PowerShell) / `set PYTHONIOENCODING=utf-8`
(cmd) before `aitutor`.
