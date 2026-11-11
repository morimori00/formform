# Canonical episode format (recorder output)

Written by `train/recorder/record.py` to `train/data/episodes/<split>/<episode_id>.jsonl.gz`
(gzip, UTF-8, one JSON object per line). A file exists only once the episode finished; an interrupted episode leaves
`*.jsonl.gz.part` and is re-recorded on the next run. `<split>` is the variant's frozen split (`train` | `eval`;
the extension fixtures use `smoke` and are never part of train/eval data).

`episode_id` = `<family>.<variant>.<split>.<teacher_mode>.<k:03d>` (deterministic, so reruns resume).

**Read it with `core.read_episode(path)`** (or `python3 train/recorder/core.py <file>...` → expanded JSONL on stdout).
It yields one fully expanded record per step, then the summary. On disk the constant and unchanged parts are stored once:

- line 1, header: `{type:"episode", episode_id, form_family, variant, split, persona, goal, goal_generic, goal_mode, context_md,
  perturbation, teacher_mode, batch, seed, label_order:{kind, fields:[id…]}, page_path, title}`.
  `batch` = `--batch` name (also part of `episode_id`: `<family>.<variant>.<split>.<teacher_mode>.<batch>.<k>`).
  `goal_generic` (= `goal`) is the natural instruction without values; the student must take values from `context_md`.
  `label_order.kind` ∈ `top_down` (60%) / `local_swaps` (30%) / `shuffled` (10%), seeded by `seed`: the field preference used
  when the oracle chooses a label among several acceptable decisions.
- step lines: `step = 0, 1, 2, …`. The keys `page, goal_planned, goal_planned_oracle, elements, operations, targets, target_criteria` are
  written only when they differ from the previous step line (missing key = same as before).
- last line: summary.

## Expanded step record (one decision)

| key | type | meaning |
|---|---|---|
| header keys | | `episode_id, form_family, variant, split, persona, goal, goal_generic, goal_mode ("fill"\|"submit"), context_md, perturbation, teacher_mode, seed, label_order` |
| `step` | int | 0-based decision index |
| `page` | `{url,title,text}` | `text` = visible viewport text (≤ 6000 chars), the extension's `visibleText()` |
| `elements` | list | jev `action_space()` elements from the extension snapshot: `{index, label, role, operations:[…], value?, checked?, selected?, expanded?, options?:[{index,label,value}]}` |
| `recent_actions` | list | last ≤ 10 executed `{action, kind, text, page_changed}` |
| `operations` | `{OP: description}` | `CLICK`/`TYPE_TEXT`/`SELECT` (those with targets), `SCROLL_DOWN`/`SCROLL_UP` (when scrollable), `WAIT`, `DONE`, `BLOCKED` |
| `targets` | `{OP: [index,…]}` | valid targets per operation (`"7"` = element 7, `"7:3"` = option 3 of select 7) |
| `target_criteria` | `{OP: {index: {element, current_value, role?, …}}}` | per-target criteria of the TypeSafe request |
| `goal_planned`, `goal_source` | str | the product-style goal (field → value pairs, extension `fillGoal()`) that was sent in the decision request. `goal_source` `bulk`: values planned by the text model (may be wrong); `oracle`: the correct values (oracle mode); `context`: instruction + context (`--teacher jev`) |
| `goal_planned_oracle` | str | the same goal with the oracle-correct value of every feasible field on the current page/step (stable for a page; changes per step of a wizard, hence per step and not in the header) |
| **`label`** | `{operation, target, text}` | **the training target.** `target` null for SCROLL_*/WAIT/DONE/BLOCKED; `text` only for TYPE_TEXT and always the oracle-correct string (`""` = clear the field), also when the teacher's own string was accepted (that one is in `teacher.text`) |
| **`acceptable`** | `[{operation, target, text?, field?}]` | every decision the oracle accepts in this state, best first. Eval: a prediction is correct if its (operation, target) is in this list. `text` is the canonical value; a different string is accepted if it passes the field's verifier normalization. Entries with `prelude:true` are harmless focus clicks into a plain text field before typing: accepted (once), never used as the label |
| **`label_source`** | `"teacher"` \| `"oracle"` | teacher: the teacher's decision was acceptable and is the label. oracle: the oracle's decision is the label |
| **`teacher`** | object \| null | the teacher's decision (null in oracle mode): `{operation, target, choice, text, probabilities, operation_probabilities, confidence, target_confidence, latency_ms, model, text_model, text_latency_ms, text_error?}` |
| **`teacher_correct`** | bool \| null | teacher decision ∈ acceptable (null in oracle mode) |
| `executed_decision` | `"label"` \| `"teacher"` | what was run. `teacher` with `teacher_correct:false` = a deliberately executed safe mistake (`--wrong-rate`) or plan/jev mode; the following steps are real recovery states |
| `action` | object \| null | executed action `{id, kind, label, role, value, node}`; null for DONE/BLOCKED |
| `executed` | bool | a browser input (or wait/scroll) actually ran |
| `page_changed` | bool \| null | fingerprint differs at the next observation; null when not executed |
| `error` | str \| null | `"stale: …"` (target changed/covered; that target is avoided at the next decision), `"text_unavailable"` (plan/jev only) |
| `bulk` | object \| null | set when the Bulk planner ran at this step: `{fields, fills, latency_ms}` |
| `outcome_after_step` | object \| null | verifier after the step settled: `{success, fields_ok, fields_total, url}` |

Rebuilding the exact TypeSafe request of a step:
`{model, state: {page, elements, recent_actions}, questions: {operation: {type:"choice", criteria: operations, instructions:{goal: goal_planned, rules: NEXT_ACTION}}, <op>_target: {type:"choice", criteria: target_criteria[OP], instructions:{goal: goal_planned, operation: OP, rules:[NEXT_ACTION, TARGET]}}}}`.

## Teacher modes (`--teacher`)

- `checked` (default): the .env teacher (TypeSafe Jev; Bulk-planned `fillGoal`; text model for unplanned TYPE_TEXT) decides
  every step. The oracle judges it. Acceptable → executed, `label_source: teacher`. Not acceptable → the oracle decision is the
  label and is executed; with probability `--wrong-rate` (0.12) the teacher's wrong decision is executed instead when it is
  recoverable (typing, select, scroll, wait, or a click on a known field's widget). A wrong submit/next/DONE/BLOCKED or a click
  on an unknown control is never executed.
- `oracle`: no model, no keys loaded, zero paid calls. `teacher: null`, `label_source: oracle`.
- `plan` / `jev`: the teacher alone is executed (still judged, so `label`/`teacher_correct` are filled).

## Oracle (`train/recorder/oracle.py`)

Pure function of one observation (element table + DOM probe + `window.__formState()`) and meta.json. A field is unfinished
when its current value fails the verifier. Per widget kind the acceptable next interaction is:
text-like → TYPE_TEXT; select/cascade → SELECT (WAIT while the option is not offered yet); radio/chips → CLICK the option;
checkbox/switch → CLICK only when the state differs; custom dropdown → CLICK to open, then CLICK the option;
autocomplete → TYPE_TEXT, WAIT while suggestions load, CLICK the suggestion; calendar date → TYPE_TEXT in the field's format,
or (read-only field) open → SELECT year/month → CLICK the day; 民國 date → three SELECTs; inactive tab → CLICK the tab once the
open tab is finished; off-screen → SCROLL_*; delayed render → WAIT. While a popup is open only its own interaction is acceptable.
A field that must be empty but is not → TYPE_TEXT `""` / uncheck. When the page has nothing left: fill goals → DONE;
submit goals → CLICK next/submit, DONE once the page reports the submission, BLOCKED when a required value is not in the context.

## Personas and start states

Each episode has one persona (`persona` id + its `context_md`) and one start state. Personas follow
`train/docs/forms-catalog.md` "Personas": ids from `meta.json["personas"]`, context `train/contexts/<P>.md`, expected values,
`submit` and prefill data from `train/contexts/<P>.expected.json` (`verify.with_persona`). Only personas of the variant's own
split are used. Per variant, personas and start states each cycle in a seeded order, so both are balanced.
Persona/variant pairs that no agent with the extension's action space can finish are left out (printed at start):
`password` (the persona has a password to type, but the extension never exposes password inputs) and
`blocked_before_last_page` (a required value is missing on a non-final wizard step, so later steps cannot be filled).

`--perturb` start states (header `perturbation` = `{kind, …}`): `none`; `prefill` (a seeded half of the fields already correct);
`complete` (everything correct: only submit is left); `wrong` (correct prefill + wrong values with their validation message);
`scroll` (starts at the bottom); `delay` (late render, `?state=loading`); `reject` (first submit rejected, `?state=error`,
only on variants that support it). Corpus forms are prefilled with `window.__ffPrefill(right[, wrong])` and the persona's values;
fixtures get the same states by DOM edits.

Batches: `--batch NAME` is stored in the header and in the id. `--max-decisions N` is a TypeSafe budget (a new episode starts
only while finished decisions plus a reserve for running episodes stay under N); episodes are scheduled round-robin over
variants so a budget stop leaves them evenly covered. Composition: `python3 train/recorder/stats.py DIR [--batch=NAME]`.

## Summary line

```json
{"episode_id": "...", "type": "summary", "success": true,
 "verified_fields": {"<field id>": {"ok": true, "observed": "...", "expected": ["..."]}, "__submitted": {"ok": true, "observed": true, "expected": true}},
 "steps": 27, "status": "done|blocked|blocked_no_change|blocked_loop|blocked_wait|max_steps|error", "error": null,
 "teacher_steps": 27, "teacher_correct": 22, "label_teacher": 22, "label_oracle": 5, "executed_wrong": 1,
 "model_calls": {"decision": 27, "text": 0, "bulk": 3, "text_cost_usd": 0.003, "text_tokens": 4100, "decision_tokens": 0},
 "elapsed_ms": 23000}
```

`success` is independent of every model and of the oracle's own DONE: corpus forms are scored by
`train/forms/verify.py score(meta, window.__formState())` (all fields match, infeasible fields empty,
`submitted == success.require_submitted` — so stopping without submit is the success when a required value is missing).
Fixtures are scored from the DOM / `window.__submitted` with the rules below.

## meta.json dialects

Corpus forms: see `train/docs/forms-catalog.md` (`source:"state"`, `kind`, `normalization`, `success.require_submitted`).
Hand-written (fixtures):

```json
{"split": "smoke", "contexts": ["a.md"], "submit": true, "submit_selectors": ["#next", "#submit"], "back_selectors": ["#back"],
 "fields": [
   {"id": "zip1", "selector": "[data-k=zip1]", "expected": "105", "normalize": ["nfkc", "digits"]},
   {"id": "addr", "selector": "#addr", "expected": "芝公園3-?丁?目?5-8", "match": "regex", "value": "芝公園3丁目5-8"},
   {"id": "terms", "selector": "#terms", "kind": "checkbox", "expected": true},
   {"id": "pin", "selector": "#pin", "expected": "", "infeasible": true, "required": true},
   {"id": "country", "selector": "#country", "kind": "dropdown", "source": "submitted", "key": "country", "expected": "Japan"}]}
```

`kind`: `text`(default) `tel email number textarea date editable select cascade radio ariaradio checkbox switch checks dropdown combobox static`
(`static` = verify-only text such as an error node). `expected`: value or list of alternatives; `value`: what the oracle enters
(default: first expected). `match`: `equals` | `contains` | `regex`. `normalize`: `nfkc trim collapse_space strip_space casefold
digits alnum amount strip_punct url`. `source:"submitted"` + `key`: final value from `window.__submitted[key]`.
Selectors are used by the verifier/oracle/perturbations only — never shown to or produced by a model.
