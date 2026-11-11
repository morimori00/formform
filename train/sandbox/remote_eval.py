"""Step accuracy of a Laya checkpoint on converted eval rows (runs in the sandbox).

    python remote_eval.py CHECKPOINT_OR_ID DATA.jsonl [--max-len 4096] [--limit N] [--out results.json]

A step is correct when the executed decision (operation + that operation's target) is in meta.acceptable.
Also reported: operation-only accuracy (operation matches any acceptable one), per-operation and per-family step
accuracy, warm latency. Episode success (primary metric) is measured in the browser by train/eval/run_episodes.py.
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
ok = op_ok = errors = 0
by_op, by_family, lat, preds = {}, {}, [], []
for r in rows:
    m = r["meta"]
    acceptable = {(o, t) for o, t in m["acceptable"]}
    t0 = time.perf_counter()
    try:
        op, target = decision(predict_chunked(agent, r["state"], r["questions"]))
    except Exception as e:  # e.g. a base checkpoint whose head budget cannot hold the options
        op, target, errors = f"ERROR {type(e).__name__}", None, errors + 1
    lat.append((time.perf_counter() - t0) * 1000)
    good = (op, target) in acceptable
    ok += good
    op_ok += op in {o for o, _ in acceptable}
    for table, key in ((by_op, m["operation"]), (by_family, m["form_family"])):
        n, k = table.get(key, (0, 0))
        table[key] = (n + 1, k + good)
    preds.append({"episode_id": m["episode_id"], "step": m["step"], "operation": op, "target": target, "ok": good})
lat.sort()
rate = lambda t: {k: {"n": n, "acc": round(c / n, 4)} for k, (n, c) in sorted(t.items())}
res = {"checkpoint": ckpt, "data": data, "max_len": agent.cfg["max_len"], "rows": len(rows), "errors": errors,
       "step_acc": round(ok / max(1, len(rows)), 4), "op_acc": round(op_ok / max(1, len(rows)), 4),
       "latency_ms_p50": round(lat[len(lat) // 2], 1), "latency_ms_p95": round(lat[int(len(lat) * 0.95) - 1], 1),
       "by_label_operation": rate(by_op), "by_family": rate(by_family)}
print(json.dumps(res))
if arg("--out"):
    with open(arg("--out"), "w") as f:
        json.dump({"summary": res, "predictions": preds}, f)
