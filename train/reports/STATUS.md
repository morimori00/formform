# Status at the end of the hackathon (2026-11-11)

The work stopped when the hackathon ended. This is where it stands; nothing below is a final benchmark.

## What exists
- **Forms**: 51 enterprise form variants (40 train, 11 eval; two whole families held out), 468 generated fictional personas,
  a page-state hook for independent verification (`train/forms/`, `train/contexts/`).
- **Recorder**: per-step teacher recording on headless Chromium, an oracle that judges and corrects each teacher decision,
  final-state verification (`train/recorder/`).
- **Data (not in the repository, regenerable)**: frozen eval set `eval-v1` (154 episodes, 2,637 decisions), 17,333 oracle-labelled
  train decisions, 3,049 teacher-judged train decisions (71% agreed with the oracle).
- **Training**: conversion to the Laya request format, Daytona GPU scripts, a step evaluator and an on-policy episode evaluator
  (`train/data/convert_to_laya.py`, `train/sandbox/`, `train/eval/`).

## Results so far (Phase 1 only)
Trained on the first oracle batch (5,863 decisions from the earlier version of the form pages) and evaluated on that batch's
held-out eval split: 154 episodes, 2,732 decisions, forms never seen in training. Product-style goal (field → value list);
typed text is supplied by the oracle, because Laya models choose among options and do not generate text.

| Model | Step accuracy | Operation accuracy | Verified episode success |
|---|---|---|---|
| Laya multilingual base | 0.059 | 0.084 | 2/154 (1.3%) |
| `cklxx/laya-browser`, untuned | 0.334 | 0.760 | 3/154 (1.9%) |
| Fine-tuned (`ft_planned`) | 0.817 | 0.891 | 26/154 (16.9%) |

Fine-tuned episode success by family: emr-registration 10/14, kyc-account-opening 6/14, hr-orangehrm 2/14, itsm-request 2/14,
us-tax-portal 4/42, tw-arrival-card 2/42, vendor-onboarding 0/14. Most failed episodes end stuck with the page unchanged
(116 of 154), not with a wrong submission.

Separately, the cloud teacher alone (TypeSafe Jev + text model, no oracle) completed 7 of 22 eval episodes (32%) on the
regenerated pages; that run used a different page version and a smaller sample, so it is not directly comparable to the table.

Raw files: `train/reports/phase1/`.

## Not done
- Phase 2 (training on the 20k-decision v2 data, the 500 / 2k / 5k / 10k learning curve, hyperparameter comparison) was started
  and stopped mid-run; no Phase 2 numbers exist.
- The goal of near-100% episode success on held-out forms was not reached: the best measured result is 16.9%.
- The single-page benchmark HTML was not built.
- On-device inference in the extension (ONNX / WebGPU, quantisation of the ~1.3 GB export) was not attempted.
- Typed text still needs a text model; choosing values on-device was not resolved.
- Known recorder/product limits: option lists that run off a page that cannot scroll, options covered by a sticky bar, and
  password fields (never exposed to the model).

## Paid usage
About 4,000 TypeSafe decisions and about 600 text-model calls (under $0.50 of text-model cost; TypeSafe returns no price).
One H100 sandbox on Daytona for about two hours.
