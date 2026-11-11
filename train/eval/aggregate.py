"""Build train/reports/phase2-results.json: one record per model on the frozen eval-v1 set.

    python3 train/eval/aggregate.py [BEST_MODEL_NAME]     # with a name: also that model's failure types

Inputs (all small, under the gitignored train/runs/):
  runs/models.json                 {name: {kind, goal, train_decisions, config, base, train_seconds, ...}}  (written by hand / the sweep)
  runs/steps/<name>.json           remote_eval.py --out, pulled from the sandbox (step accuracy rows)
  runs/eval/<name>/results.jsonl   run_episodes.py (verified episode success with the model as the policy)
  data/episodes/v2/baseline-teacher/  the recorder's product-like teacher run (its own small n)
Groups: "held_out_family" = us-tax-portal, tw-arrival-card (no variant of the family is in training);
"held_out_variant" = unseen variants of families that are in training.
"""

import gzip
import json
import sys
from pathlib import Path

TRAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRAIN / "recorder"))
FROZEN = json.loads((TRAIN / "eval" / "eval-v1.json").read_text())
HELD_OUT_FAMILIES = set(json.loads((TRAIN / "eval" / "split.json").read_text())["eval_families"])


def group_of(family):
    return "held_out_family" if family in HELD_OUT_FAMILIES else "held_out_variant"


def headers():
    out = {}
    for episode_id in FROZEN["episodes"]:
        with gzip.open(TRAIN.parent / FROZEN["directory"] / f"{episode_id}.jsonl.gz", "rt", encoding="utf-8") as f:
            h = json.loads(f.readline())
        out[episode_id] = {"family": h["form_family"], "variant": h["variant"], "start": h["perturbation"]["kind"]}
    return out


def breakdown(items, value):
    """items: [(keys dict, record)] -> {dimension: {key: {n, rate}}} for family / variant / start / group."""
    out = {}
    for dim in ("family", "variant", "start", "group"):
        cells = {}
        for keys, record in items:
            n, k = cells.get(keys[dim], (0, 0))
            cells[keys[dim]] = (n + 1, k + bool(value(record)))
        out["by_" + dim] = {key: {"n": n, "rate": round(k / n, 4)} for key, (n, k) in sorted(cells.items())}
    return out


def rate(items, value):
    return round(sum(bool(value(r)) for _k, r in items) / max(1, len(items)), 4)


def step_metrics(path):
    doc = json.loads(path.read_text())
    items = [({"family": p["family"], "variant": p["variant"], "start": p["start"], "group": group_of(p["family"])}, p) for p in doc["predictions"]]
    targeted = [(k, p) for k, p in items if p["tgt_ok"] is not None]
    s = doc["summary"]
    return {"n": len(items), "step_acc": rate(items, lambda p: p["ok"]), "operation_acc": rate(items, lambda p: p["op_ok"]),
            "target_acc": rate(targeted, lambda p: p["tgt_ok"]), "target_n": len(targeted), "errors": s["errors"],
            "latency_ms_p50": s["latency_ms_p50"], "latency_ms_p95": s["latency_ms_p95"], "by_label_operation": s["by_label_operation"],
            **breakdown(items, lambda p: p["ok"])}


def episode_metrics(path, heads):
    latest = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r["episode_id"] in heads:
            latest[r["episode_id"]] = r
    items = [({**heads[i], "group": group_of(heads[i]["family"])}, r) for i, r in sorted(latest.items())]
    steps, good = sum(r.get("teacher_steps", 0) for _k, r in items), sum(r.get("teacher_correct", 0) for _k, r in items)
    status = {}
    for _k, r in items:
        status[r["status"]] = status.get(r["status"], 0) + 1
    return {"n": len(items), "success": sum(bool(r["success"]) for _k, r in items), "episode_success": rate(items, lambda r: r["success"]),
            "on_policy_steps": steps, "on_policy_step_acc": round(good / max(1, steps), 4), "end_status": status,
            **breakdown(items, lambda r: r["success"])}


def failures(name, top=12):
    """What goes wrong for one model, from its on-policy episode records: the first wrong decision of every failed
    episode, typed as "<expected operation> on <widget role> -> <what the model did>"."""
    import core  # train/recorder/core.py

    kinds, examples, failed = {}, {}, 0
    for path in sorted((TRAIN / "runs" / "eval" / name / "eval").glob("*.jsonl.gz")):
        records = list(core.read_episode(path))
        summary = records[-1]
        if summary.get("type") != "summary" or summary["success"] or summary["episode_id"] not in FROZEN["episodes"]:
            continue
        failed += 1
        wrong = next((r for r in records[:-1] if r.get("teacher_correct") is False), None)
        if wrong is None:
            kind = f"no wrong decision recorded (ended {summary['status']})"
        else:
            want, got = wrong["label"], wrong["teacher"]
            role = (wrong["target_criteria"].get(want["operation"], {}).get(want["target"]) or {}).get("role", "") if want["target"] else ""
            expected = want["operation"] + (f" on {role}" if role else "")
            if got["operation"] == want["operation"]:
                did = "same operation, wrong target"
            elif got["operation"] in ("DONE", "BLOCKED", "WAIT", "SCROLL_DOWN", "SCROLL_UP"):
                did = got["operation"]
            else:
                did = f"{got['operation']} instead"
            kind = f"{expected} -> {did}"
        kinds[kind] = kinds.get(kind, 0) + 1
        examples.setdefault(kind, []).append(f"{summary['episode_id']}" + (f"#step{wrong['step']}" if wrong else ""))
    ranked = sorted(kinds.items(), key=lambda kv: -kv[1])[:top]
    return {"model": name, "failed_episodes": failed, "first_wrong_decision": [{"type": k, "episodes": n, "examples": examples[k][:3]} for k, n in ranked]}


def teacher_baseline():
    rows = []
    for path in sorted((TRAIN / "data" / "episodes" / "v2" / "baseline-teacher").rglob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            lines = f.read().splitlines()
        h, s = json.loads(lines[0]), json.loads(lines[-1])
        fields = [v for k, v in (s.get("verified_fields") or {}).items() if not k.startswith("__")]
        rows.append(({"family": h["form_family"], "variant": h["variant"], "start": h["perturbation"]["kind"], "group": group_of(h["form_family"])},
                     {"success": s["success"], "fields_ok": sum(bool(v["ok"]) for v in fields), "fields": len(fields)}))
    if not rows:
        return None
    return {"name": "jev-teacher", "kind": "teacher", "note": "product-like teacher alone (TypeSafe Jev + Bulk planner + text model), recorder batch baseline-teacher-v1; small n",
            "episodes": {"n": len(rows), "success": sum(bool(r["success"]) for _k, r in rows), "episode_success": rate(rows, lambda r: r["success"]),
                         "final_fields_correct": round(sum(r["fields_ok"] for _k, r in rows) / max(1, sum(r["fields"] for _k, r in rows)), 4),
                         **breakdown(rows, lambda r: r["success"])}}


def main():
    models = json.loads((TRAIN / "runs" / "models.json").read_text())
    heads = headers()
    records = []
    for name, info in models.items():
        record = {"name": name, **info}
        steps, episodes = TRAIN / "runs" / "steps" / f"{name}.json", TRAIN / "runs" / "eval" / name / "results.jsonl"
        if steps.exists():
            record["steps"] = step_metrics(steps)
        if episodes.exists():
            record["episodes"] = episode_metrics(episodes, heads)
        records.append(record)
    teacher = teacher_baseline()
    if teacher:
        records.append(teacher)
    out = {"eval_set": {"batch": FROZEN["batch"], "episodes": len(FROZEN["episodes"]), "held_out_families": sorted(HELD_OUT_FAMILIES),
                        "step_scoring": "executed (operation, target) in the oracle's acceptable set",
                        "episode_scoring": "model as policy in the recorder loop on the local forms; final page state verified (train/forms/verify.py); "
                                           "typed text supplied by the oracle, the model chooses operation + target only"},
           "models": records}
    if len(sys.argv) > 1:  # python3 aggregate.py BEST_MODEL_NAME: add its failure types
        out["failures"] = failures(sys.argv[1])
    path = TRAIN / "reports" / "phase2-results.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for r in records:
        s, e = r.get("steps", {}), r.get("episodes", {})
        print(f"{r['name']:28} train={r.get('train_decisions', '-')!s:>6} step={s.get('step_acc', '-')!s:>6} op={s.get('operation_acc', '-')!s:>6} "
              f"tgt={s.get('target_acc', '-')!s:>6} episodes={e.get('success', '-')}/{e.get('n', '-')} ({e.get('episode_success', '-')})", file=sys.stderr)


if __name__ == "__main__":
    main()
