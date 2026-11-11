# Phase 0 — teacher recorder

## What exists
- `train/recorder/record.py` — CLI (uv inline script: `playwright==1.65.0`, `httpx[http2]`). Serves `--forms` over
  `127.0.0.1:<random port>`, runs one headless Chromium per episode in a process pool, writes canonical JSONL.
- `train/recorder/page.ts` → `page.js` (esbuild, rebuilt automatically when sources change) — the **extension's own**
  `content/snapshot.ts` + `dom.ts` + `detector.ts` element table (crosses closed shadow DOM; closed roots are captured by
  wrapping `attachShadow` in an init script as a stand-in for `chrome.dom.openOrClosedShadowRoot`), plus ports of the
  content-script handlers the service worker uses (`guard`, `point`, `focusText`, `setValue`, `scroll`, `settle`).
- `train/recorder/core.py` — goals, deterministic episode plan, verifier + normalization, Bulk/fillGoal/parseFills
  ports, `EpisodeWriter`. `train/recorder/test_core.py` — 13 offline tests (no browser, no paid API).
- Decisions come from `jev-ultrafast/jev_ultrafast/model.py` itself (`choose`, `action_space`, `validate_choice`,
  `field_context`, `field_text`, `post_json`; loaded without its browser-harness deps). Keys are read from
  `jev-ultrafast/.env` into the worker processes only; nothing is printed or written.
- Execution mirrors `extension/src/background/index.ts`: guard check right before every mutation (stale → re-decide,
  never retried), trusted mouse click at the hit-tested centre, `focusText` + `Input.insertText` for TYPE_TEXT,
  native setter for SELECT, `scrollBy` for scroll, the extension's `settle`. Execution is recorded before the next
  observation; `page_changed` is filled from that observation.
- Fixtures: `train/forms/fixtures/{a-ja-event,b-zh-shadow,c-en-wizard}/index.html` (symlinks to
  `extension/fixtures/*.html`) + `meta.json`.
- Spec of what is emitted: `train/docs/episode-format.md`.

## Usage
```bash
uv run train/recorder/record.py --forms train/forms --contexts train/contexts \
  --episodes-per-variant 3 --split train --workers 4            # resumable: finished episodes are skipped
  [--teacher plan|jev] [--goal-mode meta|fill|submit] [--perturb none,prefill,wrong,scroll,delay]
  [--only 'family/variant*'] [--max-steps 40] [--max-calls 500] [--decision-usd-per-call X]
uv run --with pytest pytest train/recorder                     # offline tests
```
Episode k of a variant uses `contexts[k % n]` and perturbation `perturb[k % n]` (default cycle:
none, prefill, wrong, scroll, delay). `--goal-mode meta` uses `meta.json` `submit`.
Every finished episode appends a line with its calls and running totals to `train/reports/recorder-costs.jsonl`.

## Teacher modes
- `plan` (default, product-shaped): the extension's Bulk Fill prompt plans values for the empty/erroring fields of each
  new page (1 text call; re-plans when a dependent select gains options), and Jev gets the extension's `fillGoal()` with
  those values. Every widget step (type, open, click option, select, scroll, submit) is still a single Jev decision.
- `jev`: pure jev-ultrafast loop; goal = instruction + context; each TYPE_TEXT asks the text model.

## Smoke test (fixtures, 1 episode each, perturbation none, jev-latest + qwen/qwen3.8-27b:nitro)
| episode | teacher | success | steps | calls (decision+text+bulk) | fields ok | end |
|---|---|---|---|---|---|---|
| A ja-event (fill) | plan | no | 25 | 25+0+1 | 23/25 | loop: typed 東京都 but never clicked the suggestion; never ticked 利用規約, scrolled up/down |
| B zh-shadow (submit) | plan | no | 19 | 19+0+2 | 12/15 | loop: after 縣市 never selected 區 / meal / consent; scrolled and retyped a filled field |
| C en-wizard (submit) | plan | **yes** | 20 | 20+0+3 | 14/14 | DONE after "Application received" |
| A | jev | no | 25 | 25+21 | 20/25 | wrong company kana/hiragana readings, pref uncommitted, birthday asked 3× (null) |
| B | jev | no | 9 | 9+4 | 1/15 | text model wrote 凌智造 for 曜石智造, retyped it until no-change stop |
| C | jev | no | 11 | 11+5 | 1/14 | typed "April 12, 2019" into a date input (now fixed: date inputs get setValue) |

Extra check: C with `--perturb wrong` (Employees prefilled "3" + visible error): teacher retyped 37, submitted, success, 24 calls.
Paid usage for all of Phase 0 development + smoke: ~270 model calls (~205 TypeSafe decisions, ~65 text/bulk),
text-model cost ≈ $0.024 (OpenRouter `usage.cost`). TypeSafe returns no usage/price, so decision cost is logged as
count only (`--decision-usd-per-call` to estimate). Wall time ≈ 10–11 s per episode; ~10–15 KB per step line.

## Deliberate deviations from the extension (documented in page.ts / record.py)
1. Elements with no accessible name get the extension's own `hintOf()` text, and split boxes get `(part i/n)`.
   Without it A/B show a column of identical "textbox" rows. Suggest porting to `snapshot.ts` so product = training.
2. Bulk `fields[].label` uses the same hint, so planned labels in the goal match element labels.
3. Date-like inputs receive TYPE_TEXT through the native setter (Input.insertText is ignored by `<input type=date>`;
   the extension's Jev path has the same gap).
4. Recorder-only stop rule `blocked_loop`: same page fingerprint reached 3× after non-wait actions.
5. Submit goals replace fillGoal's "do not submit" line with "CLICK the button that submits / goes to the next step".

## Open issues
- The current teacher is weak on long single-page forms in a pure per-step loop (1/3 fixtures succeed): it leaves
  autocomplete uncommitted, skips checkboxes/radios below the fold and oscillates scroll. The product succeeds on A/B
  only because Bulk types simple fields in code. Options: keep only verified-successful episodes + steps whose
  `outcome_after_step.fields_ok` increases; record more `prefill` hard states (resembles the product's post-Bulk state);
  or add a `hybrid` mode that copies the product exactly (code-typed Bulk, Jev for the rest).
- `outcome_after_step` for `source: submitted` fields only moves after submission (C shows 1/14 until the end).
- The perturbation error message is a generic English `role=alert` node; forms with native validation should declare
  their own expected error behaviour in meta.json instead.
- Not exercised against a real full-page navigation form yet (the init script re-injects, should work).


---

# Update: oracle-checked labels (supersedes the modes/smoke/open-issues sections above)

## What changed
- `train/recorder/oracle.py`: acceptable-decision oracle (no model). `--teacher checked` (default) / `oracle` / `plan` / `jev`.
- Step records carry `label`, `acceptable`, `teacher`, `label_source`, `teacher_correct`, `executed_decision`.
- Output is `*.jsonl.gz` with a header line and carry-forward of unchanged keys; read with `core.read_episode()`.
  ~0.3–0.9 KB per step on disk (was 10–15 KB). `train/data/convert_to_laya.py` still globs `*.jsonl` with per-line
  `context_md`: it must switch to `core.read_episode()` and train on `label` (not `teacher`).
- Corpus integration: `window.__formState()` drives the oracle (`values`, `visible`, `step`, `ready`, `submitted`); success =
  `train/forms/verify.py score()`; hard states from `?state=`; split taken from meta.json (`--split` only filters);
  fixtures are split `smoke` and only recorded with `--only 'fixtures/*'`.
- Extension (`content/snapshot.ts`, `content/dom.ts` only): unnamed controls are labelled with nearby text (`hint (placeholder)`),
  split boxes get `(part i/n)`, and `allRoots()` now probes every element for a shadow root (the corpus hosts closed shadow
  roots on plain `<div>`s; before, those fields were missing from the element table, in the product too).
  `npm test` (21) and `npm run typecheck` pass.
- Viewport is now 1366×768.

## Numbers
| run | episodes | verified success | teacher agreement | paid calls |
|---|---|---|---|---|
| fixtures, oracle (5 states each) | 15 | 15/15 | – | 0 |
| fixtures, checked (1 each) | 3 | 3/3 | A 15/23, B 20/22, C 19/20 (83%) | 71 |
| corpus, oracle (39 variants × 7 states) | 273 | 268/273 (38/39 variants; eval 77/77, train 191/196) | – | 0 |
| corpus, checked (6 train variants × 1) | 6 | 6/6 | 104/135 (77%); per variant 5/7, 9/15, 13/25, 22/26, 22/27, 33/35 | 151 |

Oracle corpus run: 4,455 decisions in 2.3 MB (TYPE_TEXT 1872, CLICK 1389, WAIT 472, SELECT 451, SCROLL 299, DONE 262, BLOCKED 21).
Text-model cost of the checked runs ≈ $0.023; TypeSafe decisions are counted only.
Typical teacher mistakes: opening a field before typing ("Open X"), clicking submit while fields remain, scrolling away,
typing elsewhere while a suggestion list is open, wrong script for a name (蔡明翰 for "Tsai Ming-Han").

## Open issues
- `parabank/loan-and-open-account` (0/5): on step 2 the table is 1160 px wide inside a 980 px column, so both selects sit
  right of the viewport (page scrollWidth 1500 > 1366). No element table can reach them without horizontal scroll: forms bug.
- Oracle strictness: "CLICK Open <field>" before typing counts as a teacher error although harmless; this lowers agreement.
- WAIT steps are 10% of oracle labels (0.35 s per oracle wait; delayed renders take several). Down-sample when converting.
- `allRoots()` now calls `shadowOf()` for every element on each call; fine on these forms, cache per snapshot if large pages lag.
- In oracle mode the goal lists the expected values (as Bulk would); in checked mode it lists the teacher-planned values,
  which can be wrong while `label.text` is right. The converter should decide which goal the student sees.
- A wrong value in an earlier wizard step is fixed via Back only for corpus forms (they expose `step`).

## Update 2 (pre-volume changes)
- A focus click into a plain text field before typing is accepted once (`prelude`), never used as a label.
- Oracle labels follow a seeded per-episode field order (`label_order` in the header: 60% top-down, 30% local swaps, 10% shuffled).
- Header has `goal_generic`, `persona`, `seed`; steps have `goal_planned` (was `teacher_goal`) and `goal_planned_oracle`;
  `label.text` is always the oracle-correct string.
- Personas × start states are balanced per variant (seeded grid); persona-specific expected values are supported in a
  provisional `personas` shape. `train/recorder/stats.py` reports composition.
- Re-check: oracle corpus 268/273 (unchanged; parabank layout bug), fixtures 21/21, checked 2/2 with 36/38 agreement (43 calls).
- Earlier recorded episodes used the old header and were deleted; `train/data/episodes/` is empty until the volume run.
