# Phase 0 — GPU sandbox, Laya format, smoke train (agent: gpu)

> Superseded in part by `phase1-gpu.md`: the synthetic smoke data, `convert_to_laya.py --synth` and `bench.sh` were removed once
> real episodes existed; the throughput numbers below were measured with torch's cuDNN attention backend still on (see phase 1).

## Sandbox

| | |
|---|---|
| sandbox | `614be772-6b8b-47df-878a-d9adaba12d92` (details + usage: `train/sandbox/STATE.md`) |
| GPU | 1× **NVIDIA H100 80GB HBM3** on-demand (driver 595.91, CUDA 13.2 driver / torch cu128), earth region |
| other resources | 8 vCPU, 32 GiB RAM, 100 GiB local disk; volume `formform-train` at `/home/daytona/vol` (mountpoint-s3) |
| image | `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime` + laya 0.4.31, transformers 5.22.2 |
| auto-stop | 60 min of API inactivity. **GPU sandboxes are ephemeral: stop = delete** (local disk gone, volume kept). Auto-stop fires even while a process runs; `dt.py wait` / `keepalive` poll, which counts as activity. |
| quota | org GPU quota = **1 unit** (on-demand). Spot needs Tier 2 (probe refused). So Phase 2 = several jobs on this one H100, not several sandboxes — unless the quota is raised. |
| availability (21:28) | H100 400 on-demand, H200 78, B300 1, RTX-PRO-6000 143 |

Cost/hour (Daytona pricing page; the GPU column shown is the *preemptible* rate, on-demand GPU rates are not published there):
H100 $2.27/h + 8 vCPU × $0.0504 + 32 GiB × $0.0162 + disk ≈ **$3.2/h** (more if on-demand GPU is priced above spot).
$200 ≈ 60 h of this sandbox. H200 ($2.61) would not be faster: the 322M model uses <25 GB and training is launch-bound, not
memory-bound. B300 had 1 unit and is 1.8× the price for no expected gain here.

## Smoke train (end to end, works)

Data: no recorded episodes existed yet, so `convert_to_laya.py --synth 12` hand-builds 12 canonical episodes on
`extension/fixtures/c-en-wizard.html` (2-page wizard, custom country listbox, selects, radio, prefilled fields, DONE) with the
`c-harbor.md` context → **193 decisions** (TYPE_TEXT 97, CLICK 60, SELECT 24, DONE 12); episodes 0–9 train (161), 10–11 eval (32).
Converter output is byte-identical to `laya_browser.build_request` (checked in the sandbox) plus `state.context`.

`laya-train --data data/smoke_train.jsonl --eval data/smoke_eval.jsonl --base $(cat BASE_DIR) --out …/smoke2/ckpt --epochs 4 --max-len 2048`
→ 312 items, 281 train / 31 calibration, 20 optimizer updates, 174 s wall (incl. load, base eval, calibration, save).

| on 32 held-out synthetic decisions | base `cklxx/laya-browser` | smoke fine-tune |
|---|---|---|
| operation accuracy | 0.22 | **0.81** |
| target top-1 (op also right) | 0.10 | **0.73** |
| laya-train item accuracy (62 items) | 0.34 | 0.84 |
| warm latency / decision (H100) | 16 ms | 16 ms |

Then `laya.load(ckpt)` + one prediction on eval step 0: gold TYPE_TEXT → target 3 ("Legal entity name"); the base said SCROLL_DOWN,
the fine-tune says TYPE_TEXT / 3. Caveats: the synthetic eval shares the form with training (laya-train flags 49/62 overlapping
items), so this proves the plumbing, not generalization. Calibration fit on 31 items hit the temperature clamp (5.0) → confidences
are meaningless until real data; don't gate on `min_confidence` yet. p50 latency in `eval_ft.json` (968 ms) is warm-up of new
length buckets — measured warm it is 16 ms for both checkpoints.

## Throughput (H100, 1,610 decisions = 3,120 items, max_len 2048, rlcd, 2 epochs)

| config | epoch 1 (incl. warm-up) | epoch 2 (steady) | steady items/s |
|---|---|---|---|
| micro-batch 8 × accum 8 (default) | 197 s | 56 s | 50 |
| micro-batch 32 × accum 2 (same effective batch 64) | 89 s | 45 s | 63 |
| 3 jobs in parallel (mb 8), per job | 229–250 s | 100–115 s | 26 each, **77 aggregate** |

The first epoch pays a one-time per-length-bucket kernel warm-up; afterwards a step is kernel-launch bound (GPU mostly idle at
mb 8: `nvidia-smi dmon` shows 0–20% SM with bursts; py-spy: main thread in `cudaLaunchKernel`). Peak memory ~17 GB per job at mb 8 (3 jobs: 51 GB of 80). With 3 concurrent jobs the GPU sits at ~100% SM: the 3 runs
finished in 365 s wall vs 262 s for one alone → **2.15× aggregate throughput**, i.e. one H100 comfortably runs 3 configs at once
(more mostly queue on the GPU).
≈ 1.94 items per decision → **per 1k decisions: ~31 s/epoch steady at mb 32, ~2.5 min for 4 epochs + ~1.5 min fixed (load,
warm-up, calibration, save)**.

## Phase 2 plan (estimate)

| decisions | 4 epochs (mb 32) | GPU-h | cost @ $3.2/h |
|---|---|---|---|
| 500 | ~3 min | 0.05 | $0.2 |
| 2,000 | ~6.5 min | 0.11 | $0.4 |
| 5,000 | ~14 min | 0.23 | $0.8 |
| 10,000 | ~27 min | 0.45 | $1.5 |

The whole learning curve (≈17.5k decisions of training) × 4 hyperparameter configs ≈ 3.5 GPU-h ≈ **$12** sequentially, less with
parallel jobs. Compute is not the constraint; teacher recording and eval episodes in the browser are. One H100 runs several jobs
at once (see the parallel row): run 3 concurrent jobs (each pins one of the 8 vCPUs; GPU saturates at ~3).

## Commands (from `formform/train`)

```bash
sandbox/dt capacity                                    # free GPU units
sandbox/dt create --gpu H100,H200 --auto-stop 60       # → STATE.md
sandbox/dt setup                                       # pip install laya …, download cklxx/laya-browser, verify 1 sample
python3 data/convert_to_laya.py --synth 12 -o data/laya/smoke.jsonl      # or: data/episodes/train -o data/laya/train.jsonl
sandbox/dt push data/laya /home/daytona/work/data
sandbox/dt push data/convert_to_laya.py /home/daytona/work/convert_to_laya.py
sandbox/dt push sandbox/remote_eval.py /home/daytona/work/remote_eval.py
sandbox/dt start smoke2 'B=$(cat BASE_DIR); laya-train --data data/smoke_train.jsonl --eval data/smoke_eval.jsonl --base $B \
    --out /home/daytona/runs/smoke2/ckpt --epochs 4 --max-len 2048 && python remote_eval.py /home/daytona/runs/smoke2/ckpt data/smoke_eval.jsonl'
sandbox/dt wait smoke2                                 # polls; keeps the sandbox alive
sandbox/dt push sandbox/bench.sh /home/daytona/work/bench.sh && sandbox/dt start bench 'bash bench.sh data/smoke_x10.jsonl 3' # smoke_x10 = smoke_train.jsonl ×10 (regenerate; not kept locally)
sandbox/dt pull /home/daytona/runs/smoke2/train_report.json reports/…   # results; finished runs are also on the volume
sandbox/dt teardown
```

## Blockers / risks

- **GPU quota 1, no spot** → parallel configs share one H100 (fine for this model). Ask Daytona for a higher GPU quota / Tier 2 only
  if Phase 2 also needs GPU for something else at the same time.
- **Ephemeral sandbox**: if nobody polls for 60 min it is deleted with the local disk; finished runs survive on the volume. Never
  point `--out` at the volume (mountpoint-s3: no rename/overwrite; laya-train's `checkpoint_latest` rewrite would fail).
- Copying to the volume is slow (a 6.4 GB copy of 5 bench checkpoints was still running after >10 min; aborted). `dt.py start`
  copies the whole run dir — keep only the checkpoints you need in it, or delete `checkpoint_latest/` before the copy.
- Format decision to carry into the extension: context lives in `state.context`, not in the goal (`train/docs/laya-format.md` §3);
  the on-device runtime must reuse `build_request()`.
- No LoRA in laya-train; checkpoints are full 644 MB fp16. Browser path = laya-ts + onnxruntime-web (WebGPU→WASM); fp32 ONNX is
  ~1.3 GB, so quantization / vocab pruning is needed for the extension (untested).
- Real-data unknowns: long enterprise contexts vs the 2048-token budget; >60-option target questions (chunked, final round not trained).
