# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright==1.65.0", "httpx[http2]>=0.28,<1", "daytona"]
# ///
"""Episode success of a Laya checkpoint: the model drives the recorder loop on the local forms, the final DOM is verified.

    uv run train/eval/run_episodes.py --name ours-planned --model /home/daytona/runs/ft_planned/ckpt --goal planned
    uv run train/eval/run_episodes.py --name laya-browser --model cklxx/laya-browser --goal planned --only 'parabank/*'

The loop is train/recorder/record.py's Episode in `--teacher jev` mode (the model alone is executed, the oracle only
judges), with the model swapped for a student that asks the sandbox decision server (sandbox/remote_serve.py, started
with `sandbox/dt start serve 'python remote_serve.py'`). No paid API is called and no .env key is loaded.

What the student decides: operation + target, every step. What it does not: the typed text. TYPE_TEXT values come from
the oracle (the value the planner / text model would supply for that field); a TYPE_TEXT on a field the oracle has no
value for types nothing. --goal planned also gives the student the oracle's "- field: value" plan (a perfect Bulk
planner); --goal generic gives it only the context document.
Success = recorder verification of the final page state (train/forms/verify.py for corpus forms), never the model's DONE.
Results: train/runs/eval/<name>/{eval/*.jsonl.gz episodes, results.jsonl} and train/reports/eval/<name>.json.
"""

import argparse
import gzip
import json
import sys
import time
import types
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

TRAIN = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TRAIN / "recorder"), str(TRAIN / "data"), str(TRAIN / "sandbox")]
import convert_to_laya as fmt
import core
import oracle
import record


def ask(student, state, questions):
    body = json.dumps({"model": student["model"], "max_len": student["max_len"], "state": state, "questions": questions}).encode()
    req = urllib.request.Request(student["url"], data=body, headers={
        "Content-Type": "application/json", "x-daytona-preview-token": student["token"], "X-Daytona-Skip-Preview-Warning": "true"})
    for attempt in range(3):  # a decision request does not touch the page, so a bounded retry is fine
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["answers"]
        except urllib.error.HTTPError as e:
            if e.code == 400:
                raise RuntimeError(json.load(e).get("error", "decision server error")) from None
            if attempt == 2:
                raise
        except OSError:
            if attempt == 2:
                raise
        time.sleep(1 + attempt)


class StudentEpisode(record.Episode):
    def observe(self):
        self.last = super().observe()
        return self.last

    def teacher_text(self, model, action, goal, snap, history, cache):
        table = oracle.Table(snap, model.action_space)
        target = table.fill.get(action.get("node"))
        for item in oracle.decide(self.meta, self.last, self.task["goal_mode"], table):
            if item["operation"] == "TYPE_TEXT" and item.get("target") == target and item.get("text") is not None:
                return item["text"], "oracle", None
        return None


def student_model(jev, episode, student):
    def choose(snap, _goal, history):
        request = record.request_for(jev, snap, episode.task["goal"], history)
        _elements, targets, controls = jev.action_space(snap["actions"])
        operations = request["questions"]["operation"]["criteria"]
        heads = {q.removesuffix("_target").upper(): v["criteria"] for q, v in request["questions"].items() if q != "operation"}
        plan = None
        if student["goal"] == "planned":
            table = oracle.Table(snap, jev.action_space)
            plan = fmt.plan_lines(core.fill_goal(oracle.planned(episode.meta, episode.last, table), "", episode.task["goal_mode"]))
        state, questions = fmt.build_request(episode.task["goal"], request["state"]["page"], request["state"]["elements"], operations,
                                             heads, request["state"]["recent_actions"], plan, episode.context_md,
                                             fmt.CONTEXT_CHARS[student["goal"]])
        started = time.perf_counter()
        answers = ask(student, state, questions)
        op, target = fmt.decision(answers)
        head = answers.get(op.lower() + "_target") or {}
        choice = targets[op][target]["id"] if op in targets else controls[op]["id"] if op in controls else op
        return {"choice": choice, "operation": op, "target": target if op in targets else None,
                "confidence": answers["operation"]["confidence"], "probabilities": {},
                "operation_probabilities": answers["operation"]["probabilities"],
                "target_probabilities": head.get("probabilities", {}), "target_confidence": head.get("confidence"),
                "model": student["model"], "usage": {}, "latency_ms": round((time.perf_counter() - started) * 1000), "request": request}

    return types.SimpleNamespace(action_space=jev.action_space, choose=choose, post_json=jev.post_json)


def worker(task, base_url, out_dir, max_steps, student):
    jev = record.load_jev_model()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            episode = StudentEpisode(task, base_url, out_dir, max_steps, 0.0)
            return episode.run(browser, student_model(jev, episode, student))
        finally:
            browser.close()


def recorded_tasks(out, only):
    """One task per recorded eval episode (same form, persona, start state, goal and seed as the frozen eval batch),
    so episode success and step accuracy are measured on the same set."""
    tasks = []
    (out / "contexts").mkdir(parents=True, exist_ok=True)
    for path in sorted((TRAIN / "data" / "episodes" / "eval").glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            h = json.loads(f.readline())
        if h["split"] != "eval" or (only and not any(Path(f"{h['form_family']}/{h['variant']}").match(o) for o in only)):
            continue
        context = out / "contexts" / f"{h['episode_id']}.md"
        context.write_text(h["context_md"], encoding="utf-8")
        tasks.append({"episode_id": h["episode_id"], "form_family": h["form_family"], "variant": h["variant"], "split": "eval",
                      "teacher": "jev", "meta_path": str(TRAIN / "forms" / h["form_family"] / h["variant"] / "meta.json"),
                      "persona": h.get("persona"), "page_path": h["page_path"], "context_path": str(context),
                      "goal_mode": h["goal_mode"], "goal": h["goal_generic"], "perturbation": h["perturbation"]["kind"], "seed": h["seed"]})
    return tasks


def summarize(results):
    def rate(rows):
        steps, ok = sum(r.get("teacher_steps", 0) for r in rows), sum(r.get("teacher_correct", 0) for r in rows)
        return {"episodes": len(rows), "success": sum(bool(r["success"]) for r in rows),
                "episode_success": round(sum(bool(r["success"]) for r in rows) / max(1, len(rows)), 4),
                "on_policy_steps": steps, "on_policy_step_acc": round(ok / max(1, steps), 4)}

    by = {}
    for r in results:
        by.setdefault(r["episode_id"].split(".")[0], []).append(r)
    status = {}
    for r in results:
        status[r["status"]] = status.get(r["status"], 0) + 1
    return {**rate(results), "status": status, "by_family": {k: rate(v) for k, v in sorted(by.items())}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="label of this run (output directory)")
    ap.add_argument("--model", required=True, help="laya.load id or checkpoint dir on the sandbox")
    ap.add_argument("--goal", choices=["planned", "generic"], default="planned")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--only", action="append", help="family/variant glob, repeatable")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=40)
    args = ap.parse_args()

    import dt  # train/sandbox/dt.py: the API key stays in this process

    sandbox = dt.sandbox()
    link = sandbox.get_preview_link(args.port)
    student = {"url": link.url, "token": link.token, "model": args.model, "goal": args.goal, "max_len": args.max_len}
    out = TRAIN / "runs" / "eval" / args.name
    tasks = recorded_tasks(out, args.only)
    todo = [t for t in tasks if not core.EpisodeWriter.done(out, t["split"], t["episode_id"])]
    print(f"{args.name}: {len(tasks)} eval episodes, {len(todo)} to run", flush=True)
    record.build_page_js()
    base_url = record.serve(TRAIN / "forms")
    results_path = out / "results.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(args.workers) as pool, open(results_path, "a") as log:
        futures = {pool.submit(worker, t, base_url, out, args.max_steps, student): t for t in todo}
        for n, future in enumerate(as_completed(futures), 1):
            t = futures[future]
            try:
                r = future.result()
            except Exception as e:  # browser crash; the .part file stays and the episode reruns next time
                r = {"episode_id": t["episode_id"], "success": False, "steps": 0, "status": "crash", "error": str(e)[:300]}
            log.write(json.dumps(r, ensure_ascii=False) + "\n")
            log.flush()
            print(f"[{n}/{len(todo)}] {r['episode_id']} success={r['success']} steps={r['steps']} status={r['status']} "
                  f"ok={r.get('teacher_correct', 0)}/{r.get('teacher_steps', 0)}" + (f" error={r['error']}" if r.get("error") else ""), flush=True)
            if n % 5 == 0:
                sandbox.refresh_activity()  # preview traffic does not count as activity; idle GPU sandboxes are deleted
    latest = {}
    for line in results_path.read_text().splitlines():
        r = json.loads(line)
        latest[r["episode_id"]] = r
    summary = {"name": args.name, "model": args.model, "goal": args.goal, "max_len": args.max_len,
               "text_source": "oracle", **summarize([latest[t["episode_id"]] for t in tasks if t["episode_id"] in latest])}
    report = TRAIN / "reports" / "eval" / f"{args.name}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "by_family"}))


if __name__ == "__main__":
    main()
