# Daytona GPU sandbox (no secrets here)

- sandbox_id: `614be772-6b8b-47df-878a-d9adaba12d92`
- gpu: NVIDIA H100 80GB HBM3, 81559 MiB, 595.91.07
- image: pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime
- resources: 8 vCPU, 32 GiB RAM, 100 GiB disk, 1 GPU
- auto_stop_interval: 60 min (stop == delete for GPU sandboxes)
- volume: `formform-train` mounted at /home/daytona/vol (survives the sandbox)
- created: 2026-11-11 21:33 CST in 77s

## Log

- 2026-11-11 21:33 created (on-demand H100, earth region). Org GPU quota is **1 unit** (spot needs Tier 2: refused).
- 21:37 setup: laya 0.4.31, transformers 5.22.2, torch 2.11.0+cu128; base `cklxx/laya-browser` @ 645cf366 cached in /home/daytona/hf
  (snapshot dir in /home/daytona/work/BASE_DIR); verify on sample_request.json: TYPE_TEXT 0.846, 18 ms warm.
- 21:41 smoke train ok: /home/daytona/runs/smoke2 (copied to /home/daytona/vol/runs/smoke2).

- 22:25 phase 1: decision server `remote_serve.py` on :8791 (run dir `serve`), fine-tunes `ft_planned` / `ft_generic` in
  /home/daytona/runs (checkpoints copied to /home/daytona/vol/runs/ft_*/ckpt). torch's cuDNN attention backend is switched off in
  `ltrain.py` / `remote_eval.py` / `remote_serve.py` (it stalls ~1 s on every new sequence shape).

## Usage (from formform/train)

    sandbox/dt status | capacity
    python3 data/convert_to_laya.py data/episodes/train --split train --goal planned -o data/laya/train_planned.jsonl
    python3 data/convert_to_laya.py data/episodes/eval  --split eval  --goal planned -o data/laya/eval_planned.jsonl
    sandbox/dt push data/laya /home/daytona/work/data          # data + scripts live flat in /home/daytona/work
    for f in data/convert_to_laya.py sandbox/ltrain.py sandbox/remote_eval.py sandbox/remote_serve.py; do sandbox/dt push $f /home/daytona/work/$(basename $f); done
    sandbox/dt start NAME 'python ltrain.py --data data/train_planned.jsonl --base $(cat BASE_DIR) --out /home/daytona/runs/NAME/ckpt --epochs 4 --max-len 4096 \
        && rm -rf /home/daytona/runs/NAME/ckpt/checkpoint_latest \
        && python remote_eval.py /home/daytona/runs/NAME/ckpt data/eval_planned.jsonl --max-len 4096 --out /home/daytona/runs/NAME/eval_steps.json'
    sandbox/dt wait NAME                                       # polling keeps the sandbox alive (auto-stop = delete!)
    sandbox/dt start serve 'python remote_serve.py'            # once; then, locally, from formform/:
    uv run train/eval/run_episodes.py --name NAME-planned --model /home/daytona/runs/NAME/ckpt --goal planned
    sandbox/dt pull /home/daytona/runs/NAME/eval_steps.json reports/eval/NAME-steps.json
    sandbox/dt teardown                                        # deletes the sandbox, keeps volume formform-train

One 4096-token training job needs ~32 GB (peaks higher); two at once went out of memory next to an eval, so queue them.
If the sandbox is gone (auto-stop after 60 idle min deletes GPU sandboxes): `sandbox/dt create && sandbox/dt setup` (~2 min),
push data + scripts again; checkpoints are on the volume.

- 2026-11-11 23:39 sandbox deleted (teardown)

- 2026-11-11 23:30 hackathon ended: sandbox deleted with `sandbox/dt teardown`. Phase 2 jobs were stopped mid-run and their
  outputs were not kept. The volume `formform-train` (Phase 1 checkpoints under `runs/ft_*/ckpt`) still exists.
