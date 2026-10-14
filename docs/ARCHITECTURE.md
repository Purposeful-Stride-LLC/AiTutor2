# AiTutor architecture

## Purpose

Turn source material (manuals, syllabi, standards, notes) into a **cited course
plan** with a **local model**, then **teach** that plan in a lesson → practice →
check → review cycle grounded in the same material. Source material stays
wherever you keep it. AiTutor stores only course plans, settings and portable
pointers to the sources.

## Locations are resolved at run time

`aitutor/paths.py` is the only module that decides where files are. The
repository holds no machine-specific paths, and every location is worked out
on the computer AiTutor runs on:

| Location | Resolver | Contents |
| --- | --- | --- |
| Package data | `importlib.resources.files("aitutor")` | `content/courses/*.txt`, `content/courses/built/*.json`, `content/source_roots/*`, `prompts/*.md` |
| User data | `aitutor_home()`: `$AITUTOR_HOME`, else `%APPDATA%\aitutor` (Windows) or `~/.aitutor` | `courses/built/*.json`, `config.json` (model settings), `course_roots.json`, `cache/text/` (PDF text), `logs/`, optional `roots.json` |
| Source root | `source_root()`: `--source-root`, else `$AITUTOR_SOURCE_ROOT`, else the current directory. Per course, `course_source_root()` also uses the folder remembered when the course was built here | your books, manuals, notes |

`resolve_locator()` turns a stored locator into a path on this machine.
`portable_locator()` does the reverse when a file is ingested
(`<root>/a/b.txt` → `${SOURCE_ROOT}/a/b.txt`). Both use `pathlib` and accept
either slash, so course files move freely between Windows and Linux.

## Pipeline (v0.3.0)

```text
 aitutor setup / doctor                           (doctor.py: Python, AITUTOR_HOME, Ollama installed,
        │                                           running, model pulled; OS-specific fixes)
        ▼
 a file or folder you pick                        (tui/, or build --source)
        │  scan_folder + ingest_path               (pipeline/ingest.py: text/MD/HTML, PDF via pypdf;
        │                                           locators made portable as ${SOURCE_ROOT}/…)
        ▼
 SourceRegistry S1, S2, …  +  smart_excerpt        (sources.py; excerpts sized to num_ctx)
        │  build_prompt_pack → Ollama /api/chat     (builder.py, autobuild.py, llm_host.py;
        │                      format = course JSON schema, think=false, num_ctx 8192)
        ▼
 normalize_course → save_course                    (sources rewritten from what was read; invented
        │                                           sources → gaps; ids made unique; hashed)
        │  AITUTOR_HOME/courses/built/<id>.json  +  course_roots.json (this machine only)
        ▼
 LearnSession (pedagogy.py)
        │  Grounding.for_course → top passages      (grounding.py: chunk + keyword/IDF ranking)
        │  per phase: lesson → practice → check → review, streamed from Ollama
        ▼
 learn (CLI) · tui guided (stdlib) · tui full (Textual)

 Also: session (free-form chat, --host auto|ollama|none), start / lecture (JSON for
 other hosts), import-course (manual path), verify (hashes + sources found here).
```

### Model host

`llm_host.py` is stdlib-only HTTP to Ollama: `/api/version`, `/api/tags`,
`/api/chat` (always streamed; `think: false`; `<think>` blocks filtered even when
split across chunks) and `/api/pull`. Failures raise `HostUnavailable`,
`ModelMissing` or `HostError` with a plain-language fix; the CLI turns them
into one-line errors (exit 3), and `session --host auto` falls back to offline
replies. Settings come from `settings.py` (flag > env > `config.json` > default).

### Pedagogy

Each phase has its own system prompt containing the unit plan and the
retrieved passages. **Practice** sets one task; the learner's reply is graded
in **check** against that task (the task is carried into the check prompt),
and the score is parsed from `SCORE: N/10`. **Review** summarizes and gives an
offline next step. `/next` advances phases, then units.

## Inputs

| Input | Handler | Notes |
| --- | --- | --- |
| A folder | `scan_folder` + `ingest_source` | Recursive, sorted, hidden folders skipped, up to 40 files; unsupported types listed as skipped |
| Text / Markdown / HTML / CSV file | `ingest_path` → `read_source_text` | Up to 120,000 chars read. With a model host, `smart_excerpt` fits all sources into the context budget; the prompt-pack path keeps 6,000 per source |
| PDF | `read_source_text` (needs `pypdf`) | Text layer only (no OCR). Extracted text cached by hash for lessons |
| Pasted syllabus (file or stdin) | `ingest_text` | Marked `primary`. Locator `paste://<title>` |
| Baked course `.txt` | `CourseCatalog` + `COURSE_INDEX` | Bundled. Hard-coded list in `catalog.py` |
| Built course `.json` | `list_built` / `load_course` | Bundled courses plus `AITUTOR_HOME/courses/built/`. A user copy (imported with `--force`) takes precedence |
| Source roots | `roots.json` | `AITUTOR_HOME/roots.json` if present, else the bundled example. Informational: shown by `aitutor roots`, never read automatically |

## Course JSON contract (`aitutor.course.v1`)

Required: `course_id`, `title`, `weeks[]` (non-empty). Recommended: `audience`,
`goal`, `duration_hint`, `sources[]` (`id`, `title`, `locator`, `authority`,
`note`), per-week `objective`, `topics[]`, `activity`, `source_ids[]`,
`assessment`, plus `gaps[]` and `tutor_notes`.

`locator` is portable: `${SOURCE_ROOT}/relative/path`, a `paste://` id, or a URL.

On import AiTutor adds:
- `sources[].sha256` when the locator resolves to a readable file on this machine
- `provenance.content_sha256`: SHA-256 of the canonical course body
  (everything except `provenance` and `WHI`). `aitutor verify` re-checks it
- an optional `WHI` header (a lightweight metadata stamp for downstream indexing)

Imports never overwrite an existing course, or reuse a bundled id, without `--force`.
With `--force` the previous file is kept as `<id>.json.bak-<timestamp>`.

## Citation rule

Every built week should list `source_ids`. The tutor prompt tells the model not
to invent standards, regulations, or credentials, and to record missing
coverage in `gaps[]` rather than fabricate. With the local model,
`normalize_course` enforces it: `sources` are rebuilt from the files actually
read, citations to unknown ids are dropped, and model-invented sources become
`gaps[]` suggestions. The manual `import-course` path still trusts the JSON.

## Host split

- **Builder model** and **tutor model**: the same local Ollama model by default
  (`qwen3:8b`), configurable with `--model` / `AITUTOR_MODEL` / `aitutor setup --model`.
- **Lecturer** (optional, e.g. a voice/GUI front end): consumes `lecture` payloads.
  It doesn't own the corpus.

## Integration surface

`aitutor.nova_bridge.TutorModule` exposes `list_courses()`, `lesson_plan()`,
`start_session()`, `lecture()`, `build_pack()` and `nova_manifest()`. Because data
is located through the installed package, integrations can `pip install` AiTutor
and import it from anywhere. They don't need to run inside a checkout.
