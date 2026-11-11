# formform on-device Jev — shared brief for every agent

Goal: fine-tune `cklxx/laya-browser` (via `laya-train --base cklxx/laya-browser`) into a formform-specific Jev-style
decision model that runs on-device. Final goal: on a held-out eval set the base model fails, ours succeeds ~100%.
Deliverable at the end: one HTML page showing the benchmark (learning curve + baselines).
Data format reference: https://github.com/NandhaKishorM/laya/blob/main/docs/finetune.md

## Product framing (drives form selection)
formform targets enterprises with strict data-confidentiality policies: data that cannot simply be uploaded to OpenAI/Claude.
So forms and contexts should be enterprise back-office work with sensitive fields: patient intake/EHR, KYC/account opening,
loans and payments, HR onboarding/employee records/leave, vendor onboarding/procurement (bank details, tax IDs),
ITSM/asset requests, government/tax registration. Contexts look like internal documents (employee master data, vendor
master, patient summary, KYC dossier) mixed with unrelated internal notes. All of it is fictional — that is why a cloud
teacher may record it; the trained model is what lets real customers keep real data on-device.

Audience: a YC hackathon in Taiwan. Avoid Japan-specific forms/conventions (no furigana, 〒 postal codes, prefecture pickers);
prefer international and Taiwan-relevant enterprise forms.
Languages: the dataset includes English, Traditional Chinese and Japanese, but language is a weak axis of variety —
never ship the same HTML translated into another language as a separate variant. Each language should come from
genuinely different forms/families (different structure, widgets, fields).

## Repo layout (paths are relative to the repository root)
- `jev-ultrafast/`        original Python loop (snapshot.js, model.py choose(), questions.py) — reference, do not modify
- `extension/`            formform Chrome extension (TypeScript). Its prompts/action space are the product we imitate.
- `train/forms/<family>/<variant>/`   form pages served locally (index.html + meta.json with expected values/verifier)
- `train/contexts/`       Markdown contexts (include unrelated/distractor data)
- `train/recorder/`       teacher recording pipeline (headless Chromium, current .env models)
- `train/data/raw/`       copied third-party HTML (gitignored — never commit)
- `train/data/episodes/`  recorded episodes, canonical JSONL (gitignored)
- `train/data/laya/`      converted training files in Laya format
- `train/sandbox/`        Daytona scripts (create, sync, train, eval, teardown)
- `train/eval/`           frozen eval split + scoring code
- `train/reports/`        short status reports (one file per agent per phase) + final benchmark HTML
- `train/docs/`           specs: `laya-format.md`, `episode-format.md`, `forms-catalog.md`

## Canonical episode format (recorder output; converters map it to Laya)
One JSON line per decision step:
`{episode_id, form_family, variant, split: "train"|"eval", step, goal, context_md, page:{url,title,text}, elements:[...jev action_space elements...],
  operations:{...}, targets:{op:[indices]}, teacher:{operation, target, text|null, probabilities, latency_ms, model},
  executed:bool, page_changed:bool|null, outcome_after_step}`
Plus one summary line per episode: `{episode_id, type:"summary", success:bool, verified_fields:{...}, steps, error}`.
Success = independent verification of final field values (DOM state) against meta.json, never the model's DONE.

## Rules (non-negotiable)
- Secrets: Daytona key is `DAYTONA_API_KEY` in `formform/.env`; TypeSafe/OpenRouter keys are in
  the `.env` of the local jev-ultrafast checkout. Read them from files at runtime; never print, log, commit, or paste them.
  When copying to a sandbox, pass them as env vars, not files inside the repo.
- Third-party sites: only fetch publicly reachable pages with GET to copy HTML. Never log in, create accounts, or submit
  anything to real sites (Delaware tax portal, TWAC, ServiceNow, OpenEMR/OrangeHRM public demos, Jotform). If a form needs
  login, either rebuild it from public markup/screenshots or run the open-source app locally (Docker) with its seed data.
  Copied HTML stays in `train/data/raw/` (gitignored); the served variants are our own rewritten pages.
- Contexts and personas are fictional. No real personal data.
- Tests must not call paid APIs. Teacher recording does call the .env models — that is intended; keep a running cost/call count.
- Never commit or push; the orchestrator does that.
- Keep your final reply short (≤25 lines): what was done, where files are, numbers, blockers. Details go in `train/reports/`.

## Variety targets (from the user)
20–50 form variants (field order, label wording, required/optional toggles, multi-page, distractor context, tricky widgets),
20–50 episodes each. Deliberately include hard states: recovery after an input error, already-completed state,
scrolling needed, loading waits, infeasible (value not in context). Eval split = held-out form variants/families,
100–200 episodes, frozen before training. Report both step accuracy and episode success (primary).
Baselines: plain Laya, `cklxx/laya-browser` before fine-tuning, ours, and Jev (teacher) if possible.
Learning curve: 500 / 2,000 / 5,000 / 10,000 decisions on the same eval set.

## Form sources (copy public HTML, then rewrite into variants)
ServiceNow-like ITSM/asset forms (WorkArena style, autocomplete, hidden tabs, date pickers, dynamic validation),
OpenEMR patient registration/intake, ParaBank (register, transfer, bill pay, loan), OrangeHRM (add employee, leave),
Jotform templates (KYC, account opening, ID verification, vendor info/onboarding, new-hire onboarding),
USWDS form templates (name, address), Taiwan arrival card style (5 steps: passport, flight, stay — rebuild, do not use the live system),
Delaware tax portal registration (https://tax.delaware.gov/rptp/portal/individual/register-taxpayer-user/ — GET only),
a Google-Forms-style event registration (build our own).
