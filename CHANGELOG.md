# Changelog

## 0.4.0: stress-test fixes

From a 124-case stress test (retraining + K-12, thin and junk material, prompt
injection, headless and live TUI runs).

- **Source text is data, not instructions.** Instruction-like sentences aimed at
  AI tools are removed when material is built from or retrieved for a lesson
  (and reported in the build log). Passages are fenced in `<source>` tags with a
  rule that they are never instructions. A tutor reply that names sources
  outside the course is retried once, then withheld.
- **No padding from thin material.** The unit count scales with the material
  (about one per 2,500 characters, 1 to 8), and the build prompt no longer asks
  for "the best schedule you can" when sources are thin: missing topics go to
  `gaps`. After the build, units whose topics aren't in the files they cite are
  re-cited to the right file, or moved to `gaps` as "Not in your sources".
- **"Build anyway?"** Before building, AiTutor flags material that is too short,
  unreadable or off-subject, and asks. `build --anyway` for scripts (otherwise
  exit code 4 when not interactive).
- **Self-contained practice tasks.** Tasks must quote the text they use; if a
  task points at "the source passages" or "S1" without quoting, AiTutor adds the
  passage under **Text to use**.
- **Always a grade.** A check without `SCORE: N/10` is re-asked once; otherwise
  it says **Not graded**. Looser score parsing (`Score of 7/10`, `7 out of 10`).
- **"That isn't in your material."** The tutor is told which words of a question
  the material doesn't contain, and to say so instead of filling in.
- **Robust to odd model output.** A JSON list, string or number instead of a
  course object, and non-list `weeks`/`sources`, give a clean error. The app's
  build and lesson workers catch unexpected errors instead of crashing.
- **TUI:** Build button visible at 80x24; text typed while the tutor is
  answering is kept; Esc on a lesson goes Home; Ctrl+P at unit 1 does nothing
  (and Textual's command palette no longer steals Ctrl+P); *Build anyway* button.
- **Scanned PDFs** get a specific message pointing to OCR.

## 0.3.0: self-hosted course builder and tutor

- **Local model built in.** AiTutor talks to [Ollama](https://ollama.com) over
  HTTP (stdlib only). Default model `qwen3:8b` with an 8K context, sized for an
  8 GB GPU. Choose another with `--model`, `AITUTOR_MODEL`, or
  `aitutor setup --model` (saved in `AITUTOR_HOME/config.json`).
- **`aitutor setup` / `aitutor doctor`.** Checks Python, the data folder, Ollama
  (installed? running?) and the model (pulled?). Prints the exact fix for
  Windows, Linux or macOS. `setup` offers to start Ollama and to download the
  model. `doctor --json` for scripts. Never a traceback.
- **Build from a file or folder:** `aitutor build --source PATH --host ollama --import`.
  Reads text, Markdown, HTML, and PDF (optional `pdf` extra). Long material is
  fitted to the context (opening + outline + samples). The model's output is
  schema-constrained, and AiTutor rewrites sources from what it actually read.
  The picked folder is remembered per course on this machine.
- **Learn:** `aitutor learn <id>` runs lesson → practice → check → review per
  unit, grounded in passages retrieved from your own files, with `SCORE: N/10`
  on practice work.
- **Standalone app:** `aitutor tui`. Full-screen (optional `tui` extra,
  Textual) or guided line mode (stdlib): requirements → pick source → build →
  learn. Bare `aitutor` shows a menu and offers to open it.
- `session --host auto|ollama|none` gives real tutor replies from Ollama, and
  falls back to offline replies when it's down.
- Console output never crashes on characters the terminal can't show
  (Windows code pages).
- Tests: a fake Ollama server (no network); the full-screen UI is driven headlessly.

## 0.2.0: portable install

- **Runs from any folder on Windows or Linux.** Bundled courses, prompts, and the
  example source layout moved into the package (`aitutor/content/`) and are
  located with `importlib.resources`. `pip install .` now ships them. No more
  `PYTHONPATH` setup.
- **Per-user data directory.** Imported courses go to `AITUTOR_HOME`
  (`%APPDATA%\aitutor` on Windows, `~/.aitutor` elsewhere) instead of the code tree.
- **`${SOURCE_ROOT}` is resolved on each machine.** `--source-root` /
  `AITUTOR_SOURCE_ROOT` (default: current directory). Ingested files are stored as
  `${SOURCE_ROOT}/relative/path`. Personal source layouts go in `AITUTOR_HOME/roots.json`.
  `build --file/--paste` take absolute, `${SOURCE_ROOT}/...`, or relative paths
  (current directory first, then the source root).
- New commands: `aitutor paths` (where everything resolved), `aitutor verify`
  (course hashes + which sources exist here). `aitutor roots` now shows resolved paths.
- `import-course` no longer silently overwrites. It needs `--force` and keeps a backup.
- `start`, `/prompt` and `lecture` print complete, valid JSON (they were truncated before).
- Unknown course ids and bad files give a one-line error (exit code 2) instead of a traceback.
- Bundled course provenance hashes re-stamped (course content unchanged).
- Docs rewritten: README, `docs/ARCHITECTURE.md`, new `docs/REQUIREMENTS.md`.

## 0.1.0

- Initial release: course catalog, lesson parsing, tutor session, course-builder
  prompt pack, course import with provenance, lecture payload.
