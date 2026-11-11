"""Step accuracy of a Laya checkpoint on converted eval rows (runs in the sandbox).

    python remote_eval.py CHECKPOINT_OR_ID DATA.jsonl [--max-len 4096] [--limit N] [--out results.json]

A step is correct when the executed decision (operation + that operation's target) is in meta.acceptable.
Also: operation accuracy (operation matches any acceptable one), target accuracy (given an acceptable targeted
operation, its head picks an acceptable target), per-label-operation step accuracy, warm latency, and one line per
row in --out for the local breakdowns (family, start state, held-out group). Episode success (primary metric) is measured in the browser by train/eval/run_episodes.py.
"""

import json
import sys
import time

import laya
import torch
from convert_to_laya import decision, predict_chunked

torch.backends.cuda.enable_cudnn_sdp(False)  # see ltrain.py: ~1 s per new sequence shape otherwise


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


ckpt, data = sys.argv[1], sys.argv[2]
agent = laya.load(ckpt, device="cuda")
agent.cfg["head_max_len"] = max(768, agent.cfg.get("head_max_len_train", agent.cfg.get("head_max_len", 0)))
agent.cfg["max_len"] = int(arg("--max-len", agent.cfg["max_len"]))
try:  # ModernBERT would torch.compile its embeddings on first use
    agent.model.encoder.config.reference_compile = False
except AttributeError:
    pass
with open(data) as f:
    rows = [json.loads(line) for line in f]
rows = rows[:int(arg("--limit", len(rows)))]
ok = op_ok = tgt_ok = tgt_n = errors = 0
by_op, lat, preds = {}, [], []
for r in rows:
    m = r["meta"]
    acceptable = {(o, t) for o, t in m["acceptable"]}
    t0 = time.perf_counter()
    try:
        answers = predict_chunked(agent, r["state"], r["questions"])
        op, target = decision(answers)
    except Exception as e:  # e.g. a base checkpoint whose head budget cannot hold the options
        answers, op, target, errors = {}, f"ERROR {type(e).__name__}", None, errors + 1
    lat.append((time.perf_counter() - t0) * 1000)
    good = (op, target) in acceptable
    op_good = op in {o for o, _ in acceptable}
    # Target accuracy: with the operation given (any acceptable targeted one), is that head's choice acceptable?
    targeted = [(o, t) for o, t in acceptable if t is not None]
    tgt_good = any(answers.get(o.lower() + "_target", {}).get("choice") == t for o, t in targeted) if targeted else None
    ok, op_ok = ok + good, op_ok + op_good
    if targeted:
        tgt_n, tgt_ok = tgt_n + 1, tgt_ok + tgt_good
    n, k = by_op.get(m["operation"], (0, 0))
    by_op[m["operation"]] = (n + 1, k + good)
    preds.append({"episode_id": m["episode_id"], "step": m["step"], "family": m["form_family"], "variant": m["variant"], "start": m.get("start"),
                  "label": [m["operation"], m["target"]], "pred": [op, target], "ok": good, "op_ok": op_good, "tgt_ok": tgt_good})
lat.sort()
res = {"checkpoint": ckpt, "data": data, "max_len": agent.cfg["max_len"], "rows": len(rows), "errors": errors,
       "step_acc": round(ok / max(1, len(rows)), 4), "op_acc": round(op_ok / max(1, len(rows)), 4),
       "target_acc": round(tgt_ok / max(1, tgt_n), 4), "target_rows": tgt_n,
       "latency_ms_p50": round(lat[len(lat) // 2], 1), "latency_ms_p95": round(lat[int(len(lat) * 0.95) - 1], 1),
       "by_label_operation": {k: {"n": n, "acc": round(c / n, 4)} for k, (n, c) in sorted(by_op.items())}}
print(json.dumps(res))
if arg("--out"):
    with open(arg("--out"), "w") as f:
        json.dump({"summary": res, "predictions": preds}, f)
