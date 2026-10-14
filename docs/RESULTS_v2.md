# AiTutor v0.4.0 stress-test results (v2 live re-run) — FINAL

_Measured on commit **d3c9aa8** (branch `fixes/stresstest-v0.4`, v0.4.0) with a local Ollama `qwen3:8b`,
run completed 2026-10-10 14:43 CT. Later commits 7f449eb (test-only TUI race fix) and 9f216df
(pre-check: piped stdout / non-English prose / hyphenated subject words) are **not** covered by this run.
Sources: `summary_v2.json`, `results_matrix_v2.csv`, `tables_v2.md`, `runs_v2/`._

## Headline

| Measure | v1 (live) | v2 (v0.4, live) |
|---|---|---|
| All cases passed | 89/124 (71.8%) | **105/124 (84.7%)** |
| Normal sources passed | 86/113 (76.1%) | **102/113 (90.3%)** |
| Courses built | — | 111/124 |
| Tracebacks | — | 0 |

The ≥ 90% target on normal sources is met (90.3%).

## Failures (19), from summary_v2.json

| Reason | Count |
|---|---|
| Timeout | 9 |
| Model omitted/invalid citation (masked by the normalizer) | 8 |
| Refusal / pre-check stop ("does not contain enough about …"; "none of the words in …"; "the text doesn't read …") | 3 |
| Thin/unusable/mismatched source not flagged | 1 |

(Counts sum to 21 reasons for 19 failing cases; a case can have more than one reason.)

Failing cases (results_matrix_v2.csv, `pass`=0), 19 total:
r_hvac_html, r_forklift_wiki1, r_emt_notes, k_prealgebra_html, k_biology_long, k_worldhistory_wiki1,
k_earthsci_ocr, k_kmath_pdf, k_finlit_ocr, k_writing_mixed, e_lorem, e_one_line, e_random_chars,
e_offtopic, e_spanish, e_table_dump, e_binary_txt, e_toc_only, e_mixed_topics.
(The 113 "normal" cases include some edge-band cases with a normal expectation, so 11 normal failures
include one e_* case.)

## By band (tables_v2.md)

| Band | Pass | Built | Avg units | Topic support | Ungrounded content units | Median build s |
|---|---|---|---|---|---|---|
| k12 | 50/57 (88%) | 56 | 6.6 | 0.96 | 0 | 27.8 |
| retraining | 47/50 (94%) | 49 | 6.1 | 0.99 | 0 | 27.9 |
| edge | 8/17 (47%) | 6 | 5.0 | 0.89 | 0 | 72.0 |

By source type (normal): html 11/13, long 14/15, mixed 12/13, multi 13/13, notes 12/13, ocr 11/13,
pdf 13/14, wiki1 11/13.
By K-12 grade band: 3-5 10/10, 6-8 10/12, 9-12 25/28, K-2 5/7.

## Caveats
- "Ungrounded content units" is 0 by construction: the post-build filter and the scorer share a rule.
  The independent check (objective/activity text not in the cited source) from the interim snapshot
  was 2/305 units on 56 normal cases (v1: 25/340); no final full-suite figure for it is in the files.
- The size and subject-typed tables in tables_v2.md cover 107 of the 113 normal cases.
- The "43/55 = 78%" figure cited elsewhere is not in any result file and is not used here.
- Controlled re-grade v1 was invalid (see interim notes); no final re-grade numbers are in these files.
