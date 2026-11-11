"""Dataset composition of recorded episodes.

python3 train/recorder/stats.py [train/data/episodes] [--batch=NAME] [--json]
Counts episodes and decisions by split, family, variant, start state, persona, label order, operation, label source
and teacher correctness. Episodes that failed the independent verification are counted separately.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402


def collect(root, batch=None):
    episodes, decisions = Counter(), Counter()
    for path in sorted(Path(root).rglob("*.jsonl.gz")):
        *steps, summary = core.read_episode(path)
        if not steps or (batch and steps[0].get("batch") != batch):
            continue
        h = steps[0]
        keys = {"split": h["split"], "family": h["form_family"], "variant": f"{h['form_family']}/{h['variant']}",
                "state": h["perturbation"]["kind"], "persona": h.get("persona"), "teacher_mode": h["teacher_mode"], "batch": h.get("batch"),
                "label_order": (h.get("label_order") or {}).get("kind"), "verified": "success" if summary["success"] else "failed",
                "status": summary["status"]}
        for k, v in keys.items():
            episodes[k, str(v)] += 1
        if summary.get("teacher_steps"):
            decisions["teacher_agreement_by_family", f"{h['form_family']} correct"] += summary["teacher_correct"]
            decisions["teacher_agreement_by_family", f"{h['form_family']} total"] += summary["teacher_steps"]
        fields = [v["ok"] for k, v in summary["verified_fields"].items() if not k.startswith("__")]
        decisions["final_fields", "correct"] += sum(fields)
        decisions["final_fields", "total"] += len(fields)
        for r in steps:
            per = {**{k: keys[k] for k in ("split", "family", "variant", "state", "teacher_mode", "verified")},
                   "operation": r["label"]["operation"], "label_source": r["label_source"], "teacher_correct": r["teacher_correct"],
                   "executed_decision": r.get("executed_decision"), "acceptable_count": min(len(r["acceptable"]), 5)}
            for k, v in per.items():
                decisions[k, str(v)] += 1
        episodes["total", "all"] += 1
        decisions["total", "all"] += len(steps)
    return episodes, decisions


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    batch = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--batch=")), None)
    episodes, decisions = collect(args[0] if args else "train/data/episodes", batch)
    groups = sorted({k for k, _ in [*episodes, *decisions]})
    table = {g: {v: {"episodes": episodes.get((g, v), 0), "decisions": decisions.get((g, v), 0)}
                 for v in sorted({v for k, v in [*episodes, *decisions] if k == g})} for g in groups}
    if "--json" in sys.argv:
        return print(json.dumps(table, ensure_ascii=False, indent=1))
    for g, rows in table.items():
        print(f"\n{g:<32}{'episodes':>10}{'decisions':>11}")
        for v, c in rows.items():
            print(f"  {v:<30}{c['episodes'] or '':>10}{c['decisions'] or '':>11}")


if __name__ == "__main__":
    main()
