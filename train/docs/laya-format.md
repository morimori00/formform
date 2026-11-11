# Laya training format for formform (base: `cklxx/laya-browser`)

Sources read (2026-11-11): laya repo `docs/finetune.md`, `docs/finetune_browser_agent.md`, `laya/train_cli.py`,
`laya/train.py`, `laya/common.py` (laya 0.4.31); HF `cklxx/laya-browser` model card, `laya_browser.py`,
`code/finetune/{build_items,train}.py`, `rl_agent_config.json`. Verified in the Daytona sandbox, not just read.

## 1. The model

| | |
|---|---|
| what | Non-autoregressive "System 1" decision model: one bidirectional encoder pass answers typed questions (`choice` / `score` / `noul`) with probabilities. No text generation. |
| `cklxx/laya-browser` | v19s: Laya fine-tuned into the jev-ultrafast `/v1/systemone` decision head (operation + target). Its request format *is* `Agent.predict(state, questions)`. |
| backbone | `jhu-clsp/mmBERT-base` (ModernBERT, 22 layers, hidden 768, vocab 256k, multilingual) + 2-layer decision head. **322M params, 644 MB fp16 safetensors**; ~197M of that is the 256k-token embedding matrix. |
| budgets | `max_len` 1024 (whole sequence), `head_max_len` 768 (question + options), `max_options` 60 (wider choices are chunked), page text 1200 chars, `laya_fmt` v5 |
| calibration | `temperature` = [choice 4.56, score 1, noul 1] in `rl_agent_config.json` |
| latency | H100: **16–17 ms/decision warm** (measured, fp32 weights as `laya.load` gives them); the first request of each new length bucket costs ~1–1.5 s once (kernel warm-up) — warm up before measuring. |
| license | Apache-2.0 |

## 2. Training row schema (what `laya-train --data` reads)

One JSON object per line, one row per decision step:

```json
{"state":     {...any JSON...},
 "questions": {"<qid>": {"type": "choice", "criteria": {"<option id>": "<option text>", ...}, "instructions": <str|dict|list>}},
 "gold":      {"<qid>": {"probabilities": {"<option id>": p, ...}}},
 "meta":      {...ignored by laya-train...}}
```

- `gold` = teacher distributions (soft targets, what RLCD wants). Alternatively `expected: {"<qid>": "<option id>"}` (hard label,
  `--label-smoothing` applies). A question with neither is unlabelled and simply not trained.
- `state` is serialized with `json.dumps(state, ensure_ascii=False)`; questions go through `Agent._to_internal`, i.e. **training
  renders exactly what inference renders**. Sequence: `[CLS] <type> instructions [SEP] [MASK] opt0 [MASK] opt1 … [SEP] state [SEP]`;
  the head (≤ `head_max_len`) is kept whole and the state is clamped to the room left in `max_len`.
- Each labelled question becomes one training *item*. Our rows label `operation` plus the selected operation's target
  question → **≈1.94 items per decision** (DONE / control operations have no target).
- Rows whose options don't fit are skipped and counted (`options_collapsed`, `options_beyond_max_len`, …); `--dry-run` shows it.

## 3. How a formform decision maps to a row (`train/data/convert_to_laya.py`)

Input: canonical episodes through `recorder/core.read_episode()` (`train/docs/episode-format.md`). Format = laya-browser v5
(same code as `laya_browser.build_request`; parity checked in the sandbox on the HF `sample_request.json`) **plus two state keys**:

```text
state = {
  "plan":    "- Legal name: Bluecrest Analytics LLC\n- State: Delaware\n…"   # --goal planned only (goal_planned_oracle of the step)
  "fields":  "Legal entity name = (empty); Company website = 'https://…'; Newsletter: checked=False; …"  # ≤14 form fields
  "page":    {"url", "title", "text": page text[:1200]},
  "recent_actions": [{"action": label, "kind": "fill|click|select|…", "text": typed text|null, "page_changed": bool}]  # last 10
  "context": context markdown[:4000]                  # --goal generic only
}
questions.operation = {type: choice, instructions: {goal: goal_generic, rules: NEXT_ACTION},
                       criteria: {CLICK|TYPE_TEXT|SELECT, SCROLL_DOWN|SCROLL_UP, WAIT, DONE, BLOCKED: description}}
questions.<op>_target = {type: choice, instructions: {goal, operation: <OP>, rules: [NEXT_ACTION, TARGET]},
                         criteria: {"<element index>" or "<index>:<option#>" (SELECT): compact option string}}
compact option string = "Label (role) = 'current value' checked=…"; a select option is "Field → Option"; label ≤ 50 chars
gold.operation = {label.operation: 1.0};  gold.<op>_target = {label.target: 1.0}        # `label`, never `teacher`
meta = {episode_id, form_family, variant, split, step, operation, target, acceptable: [[op, target], …]}
```

- **Two goal variants (`--goal`)**. Both use the instruction-only `goal_generic` as the question goal.
  `planned`: the product-style field→value list goes to `state.plan`, no context. `generic`: no values, the context document
  goes to `state.context`. Neither puts values or context into the goal string: the goal is repeated in every question's
  768-token head and would push options out. **The runtime must build requests with the same `build_request()`** (port to TS).
- Observations: the element table never goes into `state` (cklxx: moving it into the options was their biggest win).
- Train rows (`--split train`): `operation` + only the labelled operation's target head; WAIT-labelled rows down-sampled
  (`--wait-keep 0.35`); refuses anything from the frozen eval split (`train/eval/split.json` + record `split`).
  `--limit-decisions N` gives nested hash-ordered subsets for the learning curve.
- Eval rows (`--split eval`): every row, every head (the request exactly as the loop sends it) + `meta.acceptable`.
- Targets with > 60 candidates (2–3% of steps: country/year selects): `predict_chunked()` splits them into interleaved chunks
  and lets chunk winners compete in a second pass; training emits both rounds (`<op>_target` = the gold's chunk,
  `<op>_target__final` = gold vs one option from every other chunk).
- Measured on the phase1-oracle batch (5,608 train decisions → 10,359 items): head mean 440 / max 772 tokens; whole sequence
  mean ≈1,350 (planned) / ≈1,720 (generic), max ≈3,200. `max_len 1024` truncates 66–100% of items, 2048 still 13–18%,
  **4096 none → train and serve with `--max-len 4096`**. Contexts: mean 1,616 / max 2,868 chars = mean 680 / max 926 tokens.

## 3b. Can the student type the TEXT itself (fully on-device)?

**Not by generation.** Laya has no decoder: per question it scores the options listed in the request (`choice`), a level
(`score`) or yes/no (`noul`). `cklxx/laya-browser` answers operation + target only; its typed text and dropdown values come from
a separate LLM (they used a local Qwen3-8B), exactly like jev's TEXT_MODEL. So a Laya student alone gives operation + target.

What the format *can* express is **extractive** text: a third choice question ("which context value goes into the chosen
field?") whose options are candidate strings cut from the context (values after `:`, table cells; ≤ 60 per pass, chunked
beyond). Ceiling measured on the phase1 batch (3,396 TYPE_TEXT labels): **85% of typed strings occur verbatim in the context**,
but only 37% equal a whole line/cell value under naive splitting; the remaining 15% are reformatted (dates in the field's format,
split phone/postal parts, name parts, kana readings, units) and cannot be chosen — they need deterministic formatters or a
generative model. Not built or trained yet; the labels to try it (`label.text` + `context_md`) are already in every episode.

Product options, most to least proven:
1. **planned**: a small on-device generative model does the Bulk plan once per page (one call, values + formats), the Laya
   student does every per-step decision (16–40 ms). The student's part is what Phase 1 measures.
2. **extractive value head + rule formatters**: no generative model at all; covers at most the verbatim share above.
3. **generic** student still needs (1) or (2) for the text; it only removes the need for a plan when choosing *where* to act.

Context-length limits: ModernBERT has 8,192 positions; cklxx trained at 1,024; we use 4,096. A request holds head (≤ 768
tokens: instructions + ≤ 60 options) + state. English contexts cost ≈ 0.4 tokens/char, so 4k chars ≈ 1.3–1.7k tokens and fits
with page text, history and plan. CJK contexts cost up to ~1 token/char: 4k chars ≈ 4k tokens does **not** fit in 4,096 with
the rest — cap `--context-chars` (≈2,000 for CJK) or go to `max_len 8192` (slower, more memory). The element table is not a
limit on the state (it lives in the options), but each head holds only 60 targets per pass.

## 4. `laya-train` CLI (laya 0.4.31)

```bash
laya-train --data train.jsonl --base cklxx/laya-browser --out ./ckpt \
           [--eval eval.jsonl] [--epochs 4] [--micro-batch 8] [--grad-accum 8] [--encoder-lr 2.5e-5] [--head-lr 1e-4] \
           [--loss rlcd|soft-ce] [--label-smoothing 0.0] [--shuffle-options] [--freeze-encoder] \
           [--max-len N] [--head-max-len N] [--target-error 0.10] [--min-abstain-n 10] [--device auto] [--seed 0] [--dry-run]
```

- `--base` accepts a dir, a built-in alias, or a Hub id; for `cklxx/laya-browser` it downloads only the checkpoint files (root).
  `--base cklxx/laya-browser` works as-is (verified); in the sandbox we pass the cached snapshot dir (`$(cat BASE_DIR)`).
- What a run does: build items → hold out a calibration slice (min(400, 10%)) → train (AdamW, cosine, fp16/bf16 autocast,
  grad-clip 1, gradient checkpointing on for CUDA) → fit one temperature per question type → write the checkpoint.
- Loss: `rlcd` (default; GRPO-style noisy-logit policy gradient, 4 samples, σ 0.4→0.1, spherical + RPS rewards, + soft CE) or
  `soft-ce`. Upstream numbers: soft-ce ≥ rlcd on typed-decisions (0.790 vs 0.772). Try both in Phase 2.
- Optimizer budget: `updates = epochs * ceil(ceil(items / micro_batch) / grad_accum)`. Small data needs more epochs (the
  smoke set at defaults gets only 20 updates). Collapse to the class prior is seed-dependent — run ≥2 seeds before concluding.
- `--eval` scores the same file before and after (accuracy, loss, ECE, Brier, confidence) and flags train/eval overlap.
- Output dir: `model.safetensors` (fp16, 644 MB), `encoder/`, `tokenizer/`, `rl_agent_config.json` (records `max_len`, training
  settings, calibration report), `questions.json`, `train_report.json`, `checkpoint_latest/` (per epoch). Loads with `laya.load(dir)`.
- Mixed precision is automatic on CUDA. No `torch.compile` (cklxx: 6× slower on variable lengths).

## 5. LoRA vs full fine-tune

- `laya-train` has **no LoRA/PEFT**. Options are full fine-tune (default; what every published result uses) or
  `--freeze-encoder` (head only: "fits a small GPU or CPU, gains much less"). A LoRA adapter would need our own loop around
  `laya.train.train_model` + `peft` on the ModernBERT encoder — not worth it: the model is 322M and a full run fits easily on one
  H100 (~17 GB per training job at micro-batch 8, 2.3 GB for inference).
- So the "adapter" we ship is a full checkpoint (644 MB fp16). If per-customer adapters are ever needed, head-only training gives a
  small diff (the head is a few % of params); measure quality first.

## 6. Evaluation tooling

- `laya-train --eval` (before/after on one file), `laya-evals run data.jsonl --model <ckpt> --json r.json` (accuracy, ECE,
  slices, thresholds, `compare` against a baseline), `laya-evals agreement` (student vs repeated teacher).
- Step accuracy: `train/sandbox/remote_eval.py CKPT eval_<goal>.jsonl --max-len 4096` → a step is correct when the executed
  (operation, target) is in `meta.acceptable`; also per-operation / per-family accuracy and latency.
- **Episode success (primary)**: `uv run train/eval/run_episodes.py --name N --model CKPT --goal planned|generic` runs the
  recorder loop (`record.Episode`, teacher mode `jev`) on the local forms with the student answering through
  `sandbox/remote_serve.py` (Daytona preview URL), and the recorder's verifier (`forms/verify.py`) scores the final page.
  Typed text comes from the oracle (see 3b); no paid call, no .env key.
- cklxx serving shim: `python laya_browser.py serve --model <ckpt>` answers jev's `/v1/systemone` (TYPESAFE_BASE_URL=…), so the
  recorder/jev loop can run the student unchanged — but its `systemone()` builds `state` without `context`; for our format call
  `convert_to_laya.build_request` and `agent.predict` directly.

## 7. On-device inference paths

| path | status | notes |
|---|---|---|
| **laya-ts + onnxruntime-web (WebGPU → WASM)** | upstream, works in browsers | `python laya-ts/scripts/export_onnx.py --model-dir <ckpt> --out-dir model` → `encoder.onnx` + `head.onnx` + `tokenizer.json` + config (checked vs torch to 1e-4). `Agent.load(url)` in the page/extension; WebGPU in Chrome/Edge, WASM fallback. **Best fit for the Chrome extension** (MV3: run it in an offscreen document; ORT WASM needs `wasm-unsafe-eval` in the CSP). |
| laya-ts + onnxruntime-node | upstream | Node CPU/CUDA, for a local helper process. |
| Python `laya` (`laya.load`) | upstream | CPU/CUDA/MPS; reference implementation. |
| laya-cpp | skeleton only | no inference code yet. |
| llama.cpp / GGUF | **not applicable** | it is an encoder + custom decision head, not a causal LM. |

Size: the exported fp32 ONNX is ~1.3 GB (upstream demo note) — too big for comfortable extension download. Shrinking options,
in order of effort: fp16 ONNX (~650 MB); int8 dynamic quantization of the encoder (~330 MB, re-check accuracy); prune the 256k
vocab to the tokens our languages use (embeddings are ~60% of params). Per-step latency on a laptop GPU via WebGPU is untested.
