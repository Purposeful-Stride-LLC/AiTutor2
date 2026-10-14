# AiTutor

AiTutor turns **your own source material** (a file or a whole folder of notes,
manuals, books) into a **structured, cited course**, then **teaches it to you**
in interactive lessons, using a **local AI model** through
[Ollama](https://ollama.com). Everything runs on your computer: no cloud
account, no API keys, no data leaving the machine.

It runs on **Windows and Linux** (macOS should work too). Every folder it uses
is worked out on your machine at run time. The repository contains no paths
from anyone's computer.

© Purposeful Stride LLC. Proprietary, all rights reserved; free 30-day evaluation
license, see `LICENSE`. Source visibility does not grant any rights.

> **Status: v0.3.0, working prototype.** Build-from-material and the
> lesson → practice → check → review cycle run end to end with a local model.
> Learner progress is not saved between sessions yet (see
> [Known limitations](#known-limitations-v030)).

---

## How it works

1. **Setup checks your computer.** Is Ollama installed and running? Is the
   model downloaded? If not, AiTutor tells you the exact command for your OS,
   and offers to start Ollama or download the model for you.
2. **You pick your source material:** one file, or a folder.
3. **The local model builds a course from it:** 4–8 units, each with an
   objective, topics, an activity, an assessment, and citations to your files.
4. **You learn it, unit by unit:**
   **lesson** (taught from passages of your own sources, with `[S1]` citations)
   → **practice** (a task you do and paste back)
   → **check** (the tutor scores your work out of 10 and gives feedback)
   → **review** (summary and an offline next step), then on to the next unit.

## Requirements

- **Python 3.11 or newer** (`python --version`, or `py --version` on Windows)
- **[Ollama](https://ollama.com/download)**, installed and running
- **A model** for Ollama. The default is **`qwen3:8b`** (about 5 GB download).
  With AiTutor's 8K context it fits an **8 GB GPU**; it also runs on CPU, slowly.
  Any chat model works: `aitutor setup --model <name>`.
- **git** (only to clone the repository)

`aitutor setup` checks all of this for you. Details, including optional extras,
supported systems and GPU sizing, are in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

## Install

Pick any folder you like. AiTutor doesn't care where it lives.

**Linux / macOS (bash or zsh)**

```bash
git clone https://github.com/Purposeful-Stride-LLC/AiTutor.git
cd AiTutor
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/Purposeful-Stride-LLC/AiTutor.git
cd AiTutor
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all]"
```

> On Windows, use `python` instead of `py` if the Python launcher isn't installed.
> If PowerShell blocks `Activate.ps1`, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip
> activation and call `.\.venv\Scripts\aitutor.exe` directly.
> In `cmd.exe`, activate with `.venv\Scripts\activate.bat`.

`[all]` adds the two optional extras: `tui` (the full-screen interface, via
`textual`) and `pdf` (reading PDF sources, via `pypdf`). Without them AiTutor
still works with the Python standard library only: you get the guided
line-mode interface and text/Markdown/HTML sources. Install one extra with
`pip install -e ".[tui]"` or `".[pdf]"`.

After installing, the `aitutor` command works **from any directory**.
`python -m aitutor` is equivalent.

## Quick start

```text
aitutor setup        # check requirements; offers to start Ollama / download the model
aitutor tui          # the app: pick a file or folder → build the course → learn it
```

Running `aitutor` with no arguments shows a short menu and offers to open the app.

`aitutor tui` opens the **full-screen interface** when the `tui` extra is
installed and you're in a real terminal (Windows Terminal, PowerShell, cmd,
any Linux terminal); otherwise the **guided** line-mode interface, which does
the same steps with numbered menus. Force either with `--full` or `--plain`.

In the full-screen interface:

| Screen | What you do |
| --- | --- |
| Requirements | See each check (✔/✘). **Download model** / **Start Ollama** buttons when they apply. **Continue** when ready |
| Home | Build a new course, or open one you already have |
| Pick source | Browse folders, or type any path (any drive) and press Enter. Shows how many usable files it found. Set subject, audience, goal, then **Build course** |
| Build | Live progress while the model writes the course, then the unit list |
| Learn | Units on the left; lesson/practice/check/review tracker and score on top; chat in the middle. Type a question, or paste your practice work. **Ctrl+N** next phase, **Ctrl+P** previous unit, **Esc** home, **Ctrl+Q** quit |

Prefer plain commands? The same flow:

```text
aitutor build --source <file-or-folder> --host ollama --import
aitutor learn <course-id>
```

## Where AiTutor keeps things

AiTutor uses three locations. None of them is written into the repository.
All three are resolved on the computer where AiTutor is installed.

| What | Where | How it's found |
| --- | --- | --- |
| **Bundled data**: sample courses, prompts, the example source layout | Inside the installed `aitutor` package | Located with `importlib.resources`, so it works from any install folder |
| **Your data**: courses you build or import, settings, which folder each course came from, an optional personal `roots.json` | `AITUTOR_HOME` | Environment variable, else `%APPDATA%\aitutor` on Windows or `~/.aitutor` on Linux/macOS |
| **Your source material**: books, manuals, notes | The *source root* | `--source-root` flag, else the `AITUTOR_SOURCE_ROOT` environment variable, else the current directory |

AiTutor writes only to `AITUTOR_HOME` and to files you name with `--out`.
It never writes into the package or your clone.

### Your source root and `${SOURCE_ROOT}`

Course files never store a full path from your computer. A source under your
source root is stored as `${SOURCE_ROOT}/relative/path`, e.g.
`${SOURCE_ROOT}/Manuals/field_manual.pdf`. On each machine
`${SOURCE_ROOT}` is replaced with that machine's source root, so the same course
file works for everyone who keeps the same folder layout under their own root,
on any drive and any OS.

Set it for the current terminal:

```bash
# Linux / macOS
export AITUTOR_SOURCE_ROOT="$HOME/study-material"
```

```powershell
# Windows PowerShell
$env:AITUTOR_SOURCE_ROOT = "$HOME\Documents\StudyMaterial"
```

To make it permanent, add the `export` line to `~/.bashrc` (or `~/.zshrc`) on
Linux/macOS. On Windows run
`setx AITUTOR_SOURCE_ROOT "%USERPROFILE%\Documents\StudyMaterial"` once and open
a new terminal. You can also pass it per command:
`aitutor --source-root <folder> roots`.

If none is set, AiTutor uses the current directory and prints a note saying so.

Check the result:

```text
aitutor roots      # each example source folder, resolved here, with exists: true/false
aitutor verify     # course hashes + which cited sources are present on this machine
```

The bundled `roots.json` is only an **example layout**. To describe your own
folders, copy it to `AITUTOR_HOME/roots.json` and edit the `path` entries
(relative to `${SOURCE_ROOT}`). AiTutor uses your copy when it exists.

## Building a course from your material

```text
aitutor build --source "<file or folder>" --host ollama --import
```

- `--source` takes one file or a folder (searched recursively; hidden folders
  skipped; up to 40 files). Readable: `.txt .md .markdown .rst .csv .tex .org
  .html .htm`, and `.pdf` with the `pdf` extra. Others are listed as skipped.
- The picked folder (or the file's folder) becomes `${SOURCE_ROOT}` for this
  course, unless you set `--source-root` / `AITUTOR_SOURCE_ROOT`. AiTutor
  remembers that folder **for this course on this computer only** (in
  `AITUTOR_HOME/course_roots.json`), so lessons can quote your files later from
  any directory. The course file itself stays portable.
- Long sources are fitted into the model's context: the opening (often the
  table of contents), an outline of headings found anywhere, and samples from
  the rest. The model is constrained to the course JSON schema.
- AiTutor rewrites the course's `sources` from the files it actually read. A
  source the model invents is moved to `gaps` as a suggestion, and invalid
  citations are dropped.
- **Before building**, AiTutor checks the material: too little text (under ~150
  words), text that doesn't read like prose (placeholder, random characters, a
  bare table, or another language), or a typed subject whose words never appear
  in the material. It then asks **Build anyway?** (in the app: a *Build anyway*
  button). Scripts get exit code 4 unless they pass `--anyway`.
- The number of units is scaled to the material (about one per 2,500
  characters, 1 to 8), and the model is told to teach only what the material
  contains. **After building**, each unit's topics are checked against the
  file(s) it cites. A unit cited to the wrong file is re-cited; a unit that none
  of your files support is moved to `gaps` as "Not in your sources: …". If no
  unit is left, the build stops and says what is missing.
- Source text is treated as material, never as instructions: sentences aimed at
  AI tools ("ignore all previous instructions …") are removed before the model
  sees them, and the build log says so.
- Scanned PDFs (no text layer) are named in the error, with a pointer to OCR.
- Without `--import`, the built course JSON is printed (or written to `--out`)
  and not saved. `--course-id` picks the id; an existing id gets `-2`, `-3`
  unless you pass `--force` (which keeps a backup).
- Also accepted: `--file` (repeatable), `--paste <file>` (a primary syllabus),
  `--stdin-paste`, `--subject`, `--learner`, `--goal`,
  `--audience adult|child|mixed`, `--notes`.

**Without a local model** (`--host none`, the default), `build` writes a
prompt pack instead: `aitutor build --file notes.txt --subject X --out pack.json`.
Paste its `system` and `user` fields into any model, then
`aitutor import-course --file model_reply.txt`. The importer validates the JSON,
adds content hashes, and refuses to overwrite without `--force`.

## Learning

```text
aitutor learn <course-id> [--week N]
```

Each unit cycles **lesson → practice → check → review**. The tutor's system
prompt contains the unit plan and the most relevant passages from *your* files
(ranked by keyword overlap with the unit), and it's told to say so when the
material doesn't cover something. Commands: `/next` (next phase or unit),
`/prev`, `/phase <name>`, `/sources` (which files were found on this computer),
`/quit`. Text you type during **practice** is your submission; the tutor
scores it (`SCORE: N/10`). If the model forgets the score, AiTutor asks once
more and otherwise shows **Not graded**.

Practice tasks include any text from your material they rely on (under
**Text to use**), because the learner can't see the passages the tutor reads.
Passages are fenced as data; a reply that names sources outside the course is
retried once and otherwise withheld. When a question asks for something your
material doesn't contain (a newer rule, a page number), the tutor is told which
words are missing and to start with "That isn't in your material."

If a course's files aren't on this computer, AiTutor says how many are missing
and teaches from the course plan; `aitutor verify <id>` shows where it looked.

`aitutor session <id> --host auto|ollama|none` is the older free-form chat. It
uses Ollama when ready and otherwise falls back to offline placeholder replies.

## Choosing the model

| Setting | Flag | Environment | Saved by `setup` | Default |
| --- | --- | --- | --- | --- |
| Model | `--model` | `AITUTOR_MODEL` | yes | `qwen3:8b` |
| Ollama URL | `--ollama-url` | `AITUTOR_OLLAMA_URL` | yes | `http://127.0.0.1:11434` |
| Context (tokens) | `--num-ctx` | `AITUTOR_NUM_CTX` | yes | `8192` |

Precedence: flag, then environment, then `AITUTOR_HOME/config.json`, then the
default. `aitutor setup --model llama3.1:8b` saves your choice and offers to
download it. Thinking-style models (qwen3) are asked to answer directly.

## Command reference

| Command | What it does |
| --- | --- |
| `aitutor setup [--yes]` | Check requirements; offer to start Ollama and download the model. `--model`/`--ollama-url`/`--num-ctx` are saved |
| `aitutor doctor [--json]` | Check only, no changes. Exit code 0 = ready, 1 = something missing |
| `aitutor tui [--full\|--plain]` | The standalone app (see [Quick start](#quick-start)) |
| `aitutor build --source PATH --host ollama --import [--anyway]` | Build and save a course from your material with the local model. `--anyway` skips the "Build anyway?" question for thin or off-subject material |
| `aitutor learn <id> [--week N]` | Lesson → practice → check → review, grounded in your sources |
| `aitutor session <id> [--week N] [--host auto\|ollama\|none]` | Free-form tutoring chat |
| `aitutor list` | All courses: id, type (`baked`/`built`), title, audience, tags |
| `aitutor show <id>` | Overview plus unit titles and objectives |
| `aitutor start <id> [--week N]` | The opening line plus the full JSON prompt bundle (for other hosts) |
| `aitutor lecture <id> [--week N]` | JSON lecture script for voice/GUI front ends |
| `aitutor build ... --out pack.json` | Prompt pack for any model (no local model needed) |
| `aitutor import-course --file F [--force]` | Save a model's course JSON into `AITUTOR_HOME` |
| `aitutor built` | Model-built courses, and whether each is `bundled` or `user` |
| `aitutor roots` | Example/personal source folders resolved on this machine |
| `aitutor verify [<id>]` | Course hashes, and which cited sources exist on this machine |
| `aitutor paths` | Every location AiTutor resolved on this machine |
| `aitutor manifest` | JSON describing the module (for integrations) |

Every command accepts `--source-root`, `--model`, `--ollama-url` and `--num-ctx`.
`aitutor --version` prints the version. Errors are one line (exit code 2, 3
when the model host fails, 4 when a build was declined at "Build anyway?"),
never a traceback.

## Your data

- AiTutor talks only to the Ollama URL you configure (your own computer by
  default). `setup` can ask Ollama to download a model; that download comes
  from Ollama's model library.
- Your files are read in place and never copied, except that text extracted
  from PDFs is cached in `AITUTOR_HOME/cache/` to make lessons faster.
- Course files store sources as `${SOURCE_ROOT}/...`. Which folder that means
  on your computer is kept in `AITUTOR_HOME`, not in the course.
- Lessons are not saved yet. Closing `learn` or the app discards the conversation.

## Repository layout

```text
aitutor/                   Python package (CLI in __main__.py)
  paths.py                 every location, resolved at run time
  settings.py              model / Ollama URL / context settings
  llm_host.py              Ollama client (stdlib HTTP, streaming)
  doctor.py                requirements check and guided setup
  grounding.py             finds the passages of your sources that fit each unit
  pedagogy.py              lesson → practice → check → review engine
  tui/                     guided.py (stdlib) and full.py (Textual) interfaces
  pipeline/                ingest, prompt builder, autobuild, course store, provenance, lecture
  prompts/                 course-builder and tutor-delivery prompt templates
  content/                 bundled sample courses and example source layout
docs/                      ARCHITECTURE.md, REQUIREMENTS.md
examples/                  usage examples (not installed)
tests/                     pytest suite (uses a fake Ollama server; never a real one)
```

## Known limitations (v0.4.0)

- **Progress isn't saved.** Reopening a course starts at unit 1 (use `--week`).
- **Small models make small mistakes.** With an 8B model, examples are
  occasionally wrong (e.g. calling a passive sentence active). Scores are a
  guide, not a grade. A bigger model helps if your GPU allows.
- **Retrieval is keyword-based.** Good for a handful of documents; very large
  libraries would want embeddings.
- **Grounding checks are lexical.** The unit check and the "not in your
  material" hint compare words, not meaning: a unit that uses different words
  for something your files do cover can be moved to gaps, and a paraphrase can
  slip through. Check the build log's notes.
- **Source checks are English-centric.** Material in another language is
  flagged and needs *Build anyway*.
- **PDFs need a text layer.** Scanned PDFs need OCR first. EPUB/DOCX aren't
  read yet; export to PDF or text.
- **Context is 8K tokens by default.** Long books are summarized by excerpt
  for course building, not read in full.
- Plain-text sample syllabi need lines like `Week 3: Title` to parse well.

See `CHANGELOG.md` for what changed in each version.

## Testing

```text
pip install -e ".[dev]"
python -m pytest
```

The tests use a temporary `AITUTOR_HOME` and a fake Ollama server, so they never
touch your real data or a real model. The full-screen interface is tested
headlessly.

## License

Proprietary — © Purposeful Stride LLC, all rights reserved. See `LICENSE`. In short: free
**30-day evaluation** (install and evaluate only); no redistribution, resale, sublicensing,
derivative or commercial use; continued use after 30 days needs written permission; no warranty.
Source being visible on GitHub does not grant any rights.

## Reporting bugs

Please open a GitHub Issue on this repository with steps to reproduce, expected vs. actual
behaviour, your OS, Python version and AiTutor version. Feedback may be used by
Purposeful Stride LLC (see `LICENSE` §4).

## Support

If this work is useful to you, you can [buy Michael a coffee on PayPal](https://paypal.me/MichaelWuchevich680). Bug reports are just as welcome.
