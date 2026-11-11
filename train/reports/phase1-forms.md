# Phase 1: persona scale-up, layout fix, new train variants (forms agent)

## 1. Bug: parabank/loan-and-open-account
Cause: label cells in the ParaBank theme were `white-space: nowrap`, so the long "minimum of $100.00…" label made the
step-2 table 1160 px wide and pushed both selects past the 1366 px viewport. Fix: labels wrap (`build.py`, ParaBank
theme CSS); the selects now sit at x = 751–951. `verify.py` now runs at 1366×768 and fails any step with horizontal overflow.

## 2. Generated personas
`train/forms/personas.py` (deterministic, `FF_PERSONA_SEED`, default 1) → 468 personas; `build.py` writes
`train/contexts/<family>/<id>.md` and, for every persona (hand-written ones too), `train/contexts/<id>.expected.json`.

| family | train personas (generated) | eval-only personas (generated) |
|---|---|---|
| itsm-request | 40 | 8 (access-request-wizard) |
| emr-registration | 40 | 8 (eval-intake) |
| parabank | 40 | — |
| hr-orangehrm | 40 | 8 (add-employee-wizard) |
| kyc-account-opening | 40 | 8 (eval-salary-account) |
| vendor-onboarding | 40 overseas + 12 Taiwanese | 8 (eval-us-vendor, US entities) |
| tw-vendor-master | 40 Taiwanese + 8 overseas | — |
| jp-travel-request | 40 | — |
| event-registration | 40 | — |
| us-tax-portal (eval family) | — | 24 (8 per variant) |
| tw-arrival-card (eval family) | — | 24 (8 per variant) |

Hand-written personas are kept and stay first in each variant's `personas` list.
- Style: same internal-document formats as the hand-written contexts (HR master record, patient summary, customer file,
  KYC dossier, vendor pack in English or zh-TW, Japanese trip plan, entity fact sheet, arrival dossier) with distractors
  (look-alike colleague or patient, previous address, closed bank account, competing vendor with another 統一編號, old asset tag).
- Locale data: valid 統一編號 checksums, 民國 dates with the Gregorian date, 台/臺 spelling variation, bank codes,
  縣市/區 addresses with matching postal codes and area codes, Japanese names and currency tables, US state/ZIP pairs.
- Missing values: optional ones often (evening phone, licence, fax, group number, email…); a required one at a low rate
  (password, PIN, asset tag, cost centre, T-shirt size, mobile, payee phone, SWIFT, passport, visa number, email).
  Result: 1–9% of (variant, persona) pairs per family/split are "fill, then stop without submitting" (11% = 1 of 9 on one eval variant).
- Train/eval separation: disjoint given-name, surname and company-stem pools; numeric IDs start with 1–4 (train) or
  6–9 (eval); build.py fails on any overlap and also checks generated names against the hand-written contexts of the other split.
- Directory widgets (user, asset, approver lookups) list all personas of the same split plus look-alikes, so suggestion
  lists now have ~230 (train) / ~50 (eval) entries and a few characters are no longer enough to find the person.
- Shared option lists were extended so values vary: 8 departments, 14 job titles, 12 training sessions, 7 insurers,
  10 bank accounts, 7 currencies, 7 Japanese cost centres.

Checks: build.py verifies for every (variant, persona) that each expected value's source text is in the persona's
document and each choice value is an option of that variant. verify.py then, for every persona of every variant,
prefills the persona's values through `window.__ffPrefill`, clicks Next/Submit and scores against the persona's
expected.json (submitted must equal `submit`).

## 3. Contract for the recorder
See "Personas" in `train/docs/forms-catalog.md`. Short version: iterate `meta.json["personas"]`; context =
`train/contexts/<id>.md`; expected = `train/contexts/<id>.expected.json` → `variants["<family>/<variant>"]` =
`{submit, fields, infeasible, hidden, prefill}`; `fields[key]` replaces `meta.fields[].expected`, `submit` replaces
`meta.submit`; perturbations via `window.__ffPrefill(right[, wrong])`.

## 4. New train variants (28 → 40 train; eval unchanged at 11)
| variant | what is structurally new |
|---|---|
| itsm-request/incident-quick-sticky | sticky Submit from the start, optional routing block below, contenteditable details, two async lookups |
| itsm-request/hardware-two-step | delivery site as type-and-click list, model as radios, calendar-only date, switch |
| emr-registration/front-desk-sticky | sticky Save, country suggestion list, insurance in closed shadow root, optional block below the fold |
| parabank/bill-pay-two-step | state as suggestion list ("Virginia"/"West Virginia"), ten-account radio list with a closed account |
| parabank/register-wizard | 3 steps, 52-state select, password optional (fill only if the context has one) |
| hr-orangehrm/leave-calendar-only | read-only date inputs (calendar only), leave type suggestion list, conditional half-day radio |
| hr-orangehrm/new-employee-one-page | long page, sticky Save, only the name block required, three suggestion lists |
| kyc-account-opening/kyc-tabbed | four hidden tabs mixing KYC and account fields, conditional address below the tabs |
| vendor-onboarding/vendor-sticky-long | banking first, sticky Submit, optional block and conditional licence number at the bottom |
| tw-vendor-master/vendor-long-sticky | single long zh-TW page, sticky 送出, 500 ms bank lookup, Gregorian date from a 民國 source |
| jp-travel-request/trip-onepage-sticky | single long page, sticky 申請する, country suggestion list, typed YYYY/MM/DD dates |
| event-registration/training-lookup | session found by typing into a list of twelve near-identical sessions, second lookup for department |

Runtime additions: `sticky_submit` (early-submit trap; `hard_states_supported` gains `early_submit_trap`), `calendar_only`,
`window.__ffPrefill`. Existing pages changed only through longer option lists and the ParaBank label wrap; the eval
variant list in `split.json` is unchanged (build.py fails if it differs from the frozen list).

## 5. Verification
`uv run --with playwright python train/forms/verify.py --personas all` → 51/51 variants pass at 1366×768: scripted UI
fill of the hand-written persona for every variant (including the 12 new ones) plus all 1,668 generated (variant, persona) pairs
through prefill → Next/Submit → score. Default run checks a sample of 3 generated personas per variant.
No paid APIs were called. Generation is reproducible: two runs with the same seed give identical documents.

## 6. Notes
- All pages were regenerated (longer option lists, new directories), so episodes recorded on the old pages no longer
  match the element tables and should be re-recorded.
- The recorder needs one change: read `personas` + `<id>.expected.json` as described above; `?state=` shortcuts only
  cover the hand-written persona, so use `window.__ffPrefill` for generated ones.
- The machine's disk was full for a few minutes during this work (not caused by these files: contexts are 5 MB);
  nothing was deleted and all writes were re-done atomically afterwards.
- build.py now needs Python ≥ 3.12 (nested f-string quotes in personas.py).
