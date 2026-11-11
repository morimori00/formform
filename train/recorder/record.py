# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright==1.65.0", "httpx[http2]>=0.28,<1"]
# ///
"""Teacher recorder: the current TypeSafe Jev + text model drive a per-step jev loop on headless Chromium.

uv run train/recorder/record.py --forms train/forms --contexts train/contexts --episodes-per-variant 3 --split train --workers 4
"""

import argparse
import functools
import http.server
import json
import os
import random
import subprocess
import sys
import threading
import time
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402
import oracle  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # formform/
ENV_FILE = ROOT.parent / "jev-ultrafast" / ".env"
ENV_KEYS = {"TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL", "TEXT_MODEL", "TEXT_MODEL_REASONING"}
PAGE_JS = HERE / "page.js"
MAX_BULK = 6  # Bulk calls per episode (each new page/step usually needs one, plus one retry on an empty answer)
NO_CHANGE_LIMIT = 3
WAIT_LIMIT = 25  # consecutive waits before an episode is given up (delayed renders take a few)
LOOP_LIMIT = 4  # recorder-only: the same page state reached 4 times after non-wait actions -> blocked_loop  # the extension's jev(): three non-wait actions without a page change -> blocked


def load_env(path=ENV_FILE):
    """Read the teacher keys into this process only. Never printed or written anywhere."""
    for line in Path(path).read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key.strip() in ENV_KEYS:
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def load_jev_model():
    """jev-ultrafast's model.py (choose, action_space, validate_choice, field_text) without its browser deps."""
    package = types.ModuleType("jev_ultrafast")
    package.__path__ = [str(ROOT / "jev-ultrafast" / "jev_ultrafast")]
    sys.modules.setdefault("jev_ultrafast", package)
    from jev_ultrafast import model

    return model


def build_page_js():
    sources = [HERE / "page.ts", *(ROOT / "extension/src/content").glob("*.ts"), *(ROOT / "extension/src/shared").glob("*.ts")]
    if PAGE_JS.exists() and PAGE_JS.stat().st_mtime >= max(p.stat().st_mtime for p in sources):
        return
    subprocess.run([str(ROOT / "node_modules/.bin/esbuild"), str(HERE / "page.ts"), "--bundle", "--format=iife",
                    "--target=chrome120", "--log-level=warning", f"--outfile={PAGE_JS}"], check=True)


def chat_json(model, system, user, max_tokens):
    """The extension's chatJson(): OpenAI-compatible JSON chat with the .env text model. Returns (output, usage)."""
    base = os.environ["TEXT_MODEL_BASE_URL"].rstrip("/")
    reasoning = {"thinking": {"type": "disabled"}} if "api.deepseek.com/" in base else {"reasoning": {"effort": "low"}}
    if os.environ.get("TEXT_MODEL_REASONING") == "none":
        reasoning = {"reasoning": {"enabled": False}}
    result = model.post_json(base + "/chat/completions", os.environ.get("TEXT_MODEL_API_KEY", ""), {
        "model": os.environ["TEXT_MODEL"], "max_tokens": max_tokens, "response_format": {"type": "json_object"}, **reasoning,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
    })
    content = (result.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        output = json.loads(content.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
    except ValueError:
        output = {}
    return output, result.get("usage")


class Stale(Exception):
    pass


DELAY_JS = """document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.style.visibility = 'hidden';
  setTimeout(() => document.documentElement.style.visibility = '', %d);
});"""


class _Captured(Exception):
    pass


def request_for(model, snap, goal, history):
    """The exact TypeSafe request model.choose() would send, without sending it (--teacher oracle)."""
    def capture(_url, _key, body):
        raise _Captured(body)

    os.environ.setdefault("TYPESAFE_API_KEY", "unused")
    real, model.post_json = model.post_json, capture
    try:
        model.choose(snap, goal, history)
    except _Captured as c:
        return c.args[0]
    finally:
        model.post_json = real


class Episode:
    def __init__(self, task, base_url, out_dir, max_steps, wrong_rate=0.12):
        self.task, self.base_url, self.out_dir, self.max_steps, self.wrong_rate = task, base_url, out_dir, max_steps, wrong_rate
        self.mode = task["teacher"]
        expected = json.loads(Path(task["expected_path"]).read_text()) if task.get("expected_path") else None
        self.meta = core.load_meta(task["meta_path"], expected)
        self.context_md = Path(task["context_path"]).read_text()
        self.rng = random.Random(task["seed"])
        self.order_kind, order = core.order_for(len(self.meta["fields"]), random.Random(task["seed"] + 1))
        self.rank = {self.meta["fields"][i]["id"]: pos for pos, i in enumerate(order)}
        self.selectors = [f.get("selector") or ":not(*)" for f in self.meta["fields"]]
        self.buttons = self.meta["submit_selectors"] + self.meta["back_selectors"]
        self.calls = {"decision": 0, "text": 0, "bulk": 0, "text_cost_usd": 0.0, "text_tokens": 0, "decision_tokens": 0}
        self.planned, self.attempted, self.seen = {}, set(), {}

    def text_cost(self, usage):
        usage = usage or {}
        self.calls["text_cost_usd"] += float(usage.get("cost") or 0)
        self.calls["text_tokens"] += int(usage.get("total_tokens") or 0)

    def update_plan(self, snap, model, table):
        """The extension's Bulk Fill as a planner: one text call per new set of empty (or erroring) fields.
        Its values go into the decision goal (fillGoal) and feed TYPE_TEXT; every widget step stays a Jev decision."""
        key = lambda f: f"{f['node']}:{len(f.get('options') or [])}"  # noqa: E731 - re-plan when a select gains options
        todo = [f for f in snap["fields"] if (not f["filled"] or f.get("error")) and key(f) not in self.attempted]
        if not todo or self.calls["bulk"] >= MAX_BULK:
            return None
        self.attempted.update(key(f) for f in todo)
        started = time.perf_counter()
        fills = []
        for _ in range(2):  # an empty answer is usually provider variance; the extension retries once too
            self.calls["bulk"] += 1
            output, usage = chat_json(model, core.BULK, core.bulk_request(self.context_md, snap, todo), 4096)
            self.text_cost(usage)
            fills = core.parse_fills(output, todo)
            if fills:
                break
        for f in fills:  # name planned values the way the element table names the element
            f["label"] = table.labels.get(f["node"], f["label"])
        self.planned.update({f["node"]: f for f in fills})
        return {"fields": len(todo), "fills": fills, "latency_ms": round((time.perf_counter() - started) * 1000)}

    def loop_detected(self, snap, history):
        """Stop cycles the no-change rule cannot see (scroll down/up forever, retyping a field that re-scrolls the page)."""
        if history and history[-1]["kind"] != "wait":
            self.seen[snap["fingerprint"]] = self.seen.get(snap["fingerprint"], 0) + 1
        return self.seen.get(snap["fingerprint"], 0) >= LOOP_LIMIT

    # ---- browser helpers
    def ev(self, expression, arg=None):
        return self.page.evaluate(expression, arg)

    def observe(self):
        """One atomic read: the extension's element table, the oracle probe and the page's own state."""
        for _ in range(50):
            try:
                self.page.wait_for_load_state("domcontentloaded")
                obs = self.ev("([f, b]) => window.__ff && window.__ff.observe(f, b)", [self.selectors, self.buttons])
                if obs:
                    return obs
            except Exception:  # navigation destroyed the context mid-read; read again
                pass
            time.sleep(0.1)
        raise RuntimeError("page never became readable")

    def verify(self, obs):
        return core.verify(self.meta, oracle.values(self.meta, obs), oracle.is_submitted(obs), self.task["goal_mode"], obs["state"])

    def outcome(self, obs):
        ok, results = self.verify(obs)
        fields = [v for k, v in results.items() if not k.startswith("__")]
        return {"success": ok, "fields_ok": sum(v["ok"] for v in fields), "fields_total": len(fields), "url": self.page.url}

    def perturb(self):
        """Hard starting states. Generated forms build theirs from ?state= (already in the URL); fixtures get DOM edits."""
        kind, s = self.task["perturbation"], self.task["seed"]
        info = {"kind": kind}
        if kind in ("none", "delay", "reject"):
            return info
        for _ in range(60):  # the form may render late (closed shadow DOM, loading state)
            obs = self.observe()
            if any(obs["probe"]) and (obs["state"] or {}).get("ready", True):
                break
            time.sleep(0.1)
        if self.meta["ff"] and kind != "scroll":
            # Corpus forms: the page's own setter with this persona's values (forms-catalog "Personas").
            pre = self.meta["prefill"] or {"right": {}, "wrong": {}}
            right = pre["right"]
            if kind == "prefill":  # a seeded half of the fields is already correct
                keys = sorted(right)
                random.Random(s).shuffle(keys)
                right = {k: right[k] for k in right if k in keys[: (len(keys) + 1) // 2]}
            wrong = pre.get("wrong") if kind == "wrong" else None
            self.ev("([r, w]) => window.__ffPrefill(r, w || undefined)", [right, wrong])
            return {**info, "fields": sorted(right), **({"wrong": wrong} if wrong else {})}
        if kind == "scroll":
            self.ev("() => scrollTo(0, document.documentElement.scrollHeight)")
            return {**info, "scroll_y": self.ev("() => scrollY")}
        fields = [f for f in self.meta["fields"] if f["feasible"] and not core.empty(f["value"]) and f.get("perturb", True)
                  and f.get("selector") and f["kind"] in oracle.TEXT_KINDS | {"select", "checkbox"}]
        texts = [f for f in fields if f["kind"] in oracle.TEXT_KINDS - {"date"}]
        if kind == "wrong" and texts:
            f = texts[s % len(texts)]
            wrong = f.get("wrong") or core.wrong_value(f["value"])
            self.ev("([s, v]) => window.__ff.prefill(s, v)", [f["selector"], wrong])
            self.ev("([s, m]) => window.__ff.markError(s, m)", [f["selector"], self.meta["error_message"]])
            return {**info, "fields": [f["id"]], "wrong": wrong}
        if kind in ("prefill", "complete"):
            picked = fields if kind == "complete" else [f for i, f in enumerate(fields) if (s >> i) % 3 == 0] or fields[:1]
            done = []
            for f in picked:
                try:
                    if self.ev("([s, v]) => window.__ff.prefill(s, v)", [f["selector"], f.get("prefill", f["value"])]):
                        done.append(f["id"])
                except Exception:
                    pass  # e.g. a dependent select whose options are not loaded yet
            info["fields"] = done
        return info

    def execute(self, action, snap, text):
        kind, node = action["kind"], action.get("node")
        if kind == "wait":
            # The product waits 100 ms and then spends a model round trip; without a model that would be a busy loop.
            return time.sleep(0.1 if self.mode != "oracle" else 0.35)
        if kind == "scroll":
            return self.ev("d => window.__ff.scroll(d)", action["delta"])
        # Fresh check immediately before a mutation; a stale node is re-decided, never retried blindly.
        if self.ev("n => window.__ff.guard(n)", node) != snap["guards"].get(str(node), ""):
            raise Stale("target changed since the snapshot")
        try:
            if kind == "select":
                self.ev("([n, v]) => window.__ff.setValue(n, v)", [node, action["value"]])
            elif kind == "fill":
                if self.ev("n => window.__ff.focusText(n)", node) == "date":
                    self.ev("([n, v]) => window.__ff.setValue(n, v)", [node, text])  # date inputs ignore typed text
                elif text == "":
                    self.page.keyboard.press("Delete")  # focusText selected everything: clear the field
                else:
                    self.page.keyboard.insert_text(text)  # CDP Input.insertText, as the extension does
            else:
                point = self.ev("n => window.__ff.point(n)", node)
                if not point:
                    raise Stale("target moved or is covered")
                self.page.mouse.click(point["x"], point["y"])
        except Stale:
            raise
        except Exception as e:
            if "stale" in str(e):
                raise Stale(str(e)) from None
            raise

    def teacher_text(self, model, action, goal, snap, history, cache):
        """Value for the teacher's TYPE_TEXT: Bulk's planned value, else the text model. (text, text_model, latency) or None."""
        planned = self.planned.get(action.get("node"))
        if planned and "option" not in planned:
            return planned["value"], "bulk", None  # Bulk already generated this value (the extension's plannedFor)
        helper_input = model.field_context(goal, action, snap, history)
        if cache.get("input") == helper_input:
            return cache["result"]  # identical helper input: reuse the stale retry's value
        try:
            self.calls["text"] += 1
            text, helper = model.field_text(helper_input)
        except ValueError:
            return None  # the text model answered null: value not in the context
        self.text_cost(helper.get("usage"))
        cache.update(input=helper_input, result=(text, helper["model"], helper["latency_ms"]))
        return cache["result"]

    # ---- the loop
    def run(self, browser, model):
        task, meta, mode = self.task, self.meta, self.mode
        context = browser.new_context(viewport={"width": 1366, "height": 768}, locale=meta["locale"])
        context.add_init_script(path=str(PAGE_JS))
        delay_ms = 0
        if task["perturbation"] == "delay" and not meta["ff"]:
            delay_ms = 1200 + task["seed"] % 1500
            context.add_init_script(script=DELAY_JS % delay_ms)
        self.page = context.new_page()
        self.page.goto(self.base_url + task["page_path"], wait_until="load")
        perturbation = {**self.perturb(), **({"delay_ms": delay_ms} if delay_ms else {})}
        writer = core.EpisodeWriter(self.out_dir, {
            "episode_id": task["episode_id"], "form_family": task["form_family"], "variant": task["variant"], "split": task["split"],
            "persona": task.get("persona"), "goal": task["goal"], "goal_generic": task["goal"], "goal_mode": task["goal_mode"],
            "context_md": self.context_md, "perturbation": perturbation, "seed": task["seed"],
            "label_order": {"kind": self.order_kind, "fields": sorted(self.rank, key=self.rank.get)},
            "teacher_mode": mode, "batch": task.get("batch"), "page_path": task["page_path"], "title": meta["title"]})
        error, status, history, pending, cache, previous = None, "max_steps", [], None, {}, None
        avoid, waits, last_click = set(), 0, None
        stats = {"teacher_steps": 0, "teacher_correct": 0, "label_teacher": 0, "label_oracle": 0, "executed_wrong": 0}
        started = time.perf_counter()
        obs = None
        try:
            for step in range(self.max_steps + 1):
                obs = self.observe()
                snap = obs["snap"]
                if pending:
                    # Execution was logged before this observation; only now is page_changed known.
                    changed = snap["fingerprint"] != previous if pending["executed"] else False
                    pending["page_changed"] = changed if pending["executed"] else None
                    history[-1]["page_changed"] = changed
                    pending["outcome_after_step"] = self.outcome(obs)
                    writer.step(pending)
                    pending = None
                if step == self.max_steps:
                    break
                recent = history[-NO_CHANGE_LIMIT:]
                if len(recent) == NO_CHANGE_LIMIT and all(h["page_changed"] is False and h["kind"] != "wait" for h in recent):
                    status = "blocked_no_change"
                    break
                wait_limit = WAIT_LIMIT if mode != "oracle" else WAIT_LIMIT // 2  # oracle waits are 0.35 s each
                if self.loop_detected(snap, history) or waits >= wait_limit:
                    status = "blocked_loop" if waits < wait_limit else "blocked_wait"
                    break
                if snap["fingerprint"] != previous:
                    avoid.clear()
                previous = snap["fingerprint"]
                table = oracle.Table(snap, model.action_space)
                acceptable = oracle.decide(meta, obs, task["goal_mode"], table, last_click)
                goal_oracle = core.fill_goal(oracle.planned(meta, obs, table), self.context_md, task["goal_mode"])

                # -- the decision request (and the teacher's answer, unless the oracle works alone)
                bulk = decision = None
                if mode == "oracle":
                    goal, goal_source = goal_oracle, "oracle"
                    request = request_for(model, snap, goal, history)
                else:
                    if mode == "jev":
                        goal, goal_source = core.teacher_goal(task["goal"], self.context_md), "context"
                    else:
                        bulk = self.update_plan(snap, model, table)
                        nodes = {f["node"] for f in snap["fields"]}
                        goal = core.fill_goal([p for n, p in self.planned.items() if n in nodes], self.context_md, task["goal_mode"])
                        goal_source = "bulk"
                    decision = model.choose(snap, goal, history)
                    self.calls["decision"] += 1
                    self.calls["decision_tokens"] += int((decision.get("usage") or {}).get("total_tokens") or 0)
                    request = decision["request"]
                heads = {q.removesuffix("_target").upper(): v["criteria"] for q, v in request["questions"].items() if q != "operation"}

                # -- judge the teacher against the oracle, choose the label and what to execute
                teacher = t_action = t_text = None
                teacher_ok = None
                explore = mode == "checked" and self.rng.random() < self.wrong_rate
                if decision:
                    op, target = decision["operation"], decision["target"]
                    if decision["choice"] not in ("DONE", "BLOCKED"):
                        t_action = next(a for a in snap["actions"] if a["id"] == decision["choice"])
                    teacher = {
                        "operation": op, "target": target, "choice": decision["choice"], "text": None,
                        "probabilities": decision["target_probabilities"] or decision["operation_probabilities"],
                        "operation_probabilities": decision["operation_probabilities"],
                        "confidence": decision["confidence"], "target_confidence": decision["target_confidence"],
                        "latency_ms": decision["latency_ms"], "model": decision["model"], "text_model": None, "text_latency_ms": None,
                    }
                    if t_action and t_action["kind"] == "fill" and (mode != "checked" or explore or oracle.same_target(acceptable, op, target)):
                        got = self.teacher_text(model, t_action, goal, snap, history, cache)
                        if got:
                            t_text = got[0]
                            teacher.update(text=got[0], text_model=got[1], text_latency_ms=got[2])
                        else:
                            teacher["text_error"] = "text_unavailable"
                    teacher_ok = oracle.judge(acceptable, op, target, t_text, meta) is not None
                    stats["teacher_steps"] += 1
                    stats["teacher_correct"] += teacher_ok
                if teacher_ok:  # the teacher's decision is the label; its text is replaced by the oracle's canonical text
                    item, label_source = oracle.same_target(acceptable, teacher["operation"], teacher["target"]), "teacher"
                else:
                    item, label_source = oracle.pick(acceptable, t_action.get("node") if t_action else None, avoid, self.rank), "oracle"
                if (item["operation"], item.get("target")) in avoid and label_source == "oracle":
                    # Every acceptable target was just found covered (e.g. by a sticky bar): move the page instead.
                    scroll = next((op for op in ("SCROLL_DOWN", "SCROLL_UP") if op in table.controls), None)
                    item = {"operation": scroll, "target": None} if scroll else item
                if item.get("prelude"):  # accepted focus click: fine to execute, but the label is the direct action
                    item, label_source = oracle.pick(acceptable, item["node"], avoid, self.rank), "oracle"
                label = {"operation": item["operation"], "target": item["target"], "text": item.get("text")}
                stats["label_" + label_source] += 1
                unsafe = not t_action or (t_action["kind"] == "fill" and t_text is None) or (
                    t_action["kind"] == "click" and t_action["node"] not in oracle.field_nodes(obs))
                run_teacher = bool(decision) and (teacher_ok or mode in ("plan", "jev") or (explore and not unsafe))
                run = teacher if run_teacher else label
                run_text = t_text if run_teacher else label["text"]  # an accepted teacher string passed the verifier's normalization
                stats["executed_wrong"] += bool(run_teacher and not teacher_ok)

                record = {
                    "step": step, "goal_planned": goal, "goal_planned_oracle": goal_oracle, "goal_source": goal_source, "bulk": bulk,
                    "page": request["state"]["page"], "elements": request["state"]["elements"],
                    "recent_actions": request["state"]["recent_actions"],
                    "operations": request["questions"]["operation"]["criteria"],
                    "targets": {o: list(c) for o, c in heads.items()}, "target_criteria": heads,
                    "label": label, "label_source": label_source, "acceptable": oracle.public(acceptable),
                    "teacher": teacher, "teacher_correct": teacher_ok,
                    "executed_decision": "teacher" if run_teacher else "label",
                    "action": None, "executed": False, "page_changed": None, "error": None, "outcome_after_step": None,
                }
                if run["operation"] in ("DONE", "BLOCKED"):
                    status = run["operation"].lower()
                    time.sleep(1.0)  # let in-flight submits/renders finish before the final read
                    obs = self.observe()
                    record["outcome_after_step"] = self.outcome(obs)
                    writer.step(record)
                    break
                action = table.targets[run["operation"]][run["target"]] if run["target"] else table.control_actions[run["operation"]]
                record["action"] = {k: action.get(k) for k in ("id", "kind", "label", "role", "value", "node")}
                if action["kind"] == "fill" and run_text is None:
                    # plan/jev only: the text model had no value. Nothing is typed; history shows the attempt made no change.
                    record["error"] = "text_unavailable"
                    history.append({"action": action["label"], "kind": "fill", "text": None, "page_changed": None})
                    pending = record
                    continue
                try:
                    self.execute(action, snap, run_text)
                except Stale as e:
                    record["error"] = f"stale: {e}"
                    avoid.add((run["operation"], run["target"]))
                    writer.step({**record, "outcome_after_step": self.outcome(obs)})
                    continue
                cache.clear()
                last_click = action.get("node") if action["kind"] == "click" else None
                waits = waits + 1 if action["kind"] == "wait" else 0
                record["executed"] = True
                history.append({"action": action["label"], "kind": action["kind"], "text": run_text if action["kind"] == "fill" else None,
                                "page_changed": None})
                pending = record
                try:
                    self.ev("([n, f]) => window.__ff.settle(n, f)", [action.get("node") or None, action["kind"] == "fill"])
                except Exception:
                    pass  # navigation; the next observation waits for the new document
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:500]
            status = "error"
            if pending:
                writer.step(pending)
        try:
            obs = self.observe()
        except Exception:
            pass
        success, results = self.verify(obs) if obs else (False, {})
        writer.finish({
            "episode_id": task["episode_id"], "type": "summary", "success": bool(success), "verified_fields": results,
            "steps": writer.steps, "status": status, "error": error, **stats,
            "model_calls": dict(self.calls), "elapsed_ms": round((time.perf_counter() - started) * 1000),
        })
        context.close()
        return {"episode_id": task["episode_id"], "success": bool(success), "steps": writer.steps, "status": status,
                "error": error, **stats, **self.calls}


def worker(task, base_url, out_dir, max_steps, wrong_rate):
    if task["teacher"] != "oracle":  # the oracle never needs keys, so it cannot make a paid call
        load_env()
    model = load_jev_model()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            return Episode(task, base_url, out_dir, max_steps, wrong_rate).run(browser, model)
        finally:
            browser.close()


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forms", default="train/forms", help="root with <family>/<variant>/{index.html,meta.json}")
    ap.add_argument("--contexts", default="train/contexts")
    ap.add_argument("--out", default="train/data/episodes")
    ap.add_argument("--costs", default="train/reports/recorder-costs.jsonl")
    ap.add_argument("--episodes-per-variant", type=int, default=3)
    ap.add_argument("--split", choices=["train", "eval"], help="record only variants of this split (the split itself is frozen in meta.json)")
    ap.add_argument("--goal-mode", choices=["meta", "fill", "submit"], default="meta")
    ap.add_argument("--perturb", default=",".join(core.PERTURBATIONS),
                    help="comma list cycled over episode k: " + ",".join(core.PERTURBATIONS))
    ap.add_argument("--only", action="append", help="family/variant glob, repeatable")
    ap.add_argument("--skip", action="append", help="family/variant glob to leave out, repeatable")
    ap.add_argument("--batch", help="name stored in every episode header and id (tells recording runs apart)")
    ap.add_argument("--teacher", choices=["checked", "oracle", "plan", "jev"], default="checked",
                    help="checked: the .env teacher decides every step, the oracle judges it and corrects wrong steps. "
                         "oracle: no model calls. plan/jev: the teacher alone (Bulk-planned goal / instruction+context goal)")
    ap.add_argument("--wrong-rate", type=float, default=0.12,
                    help="checked: chance to execute a safe wrong teacher decision so the next states are real recovery states")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--max-calls", type=int, default=0, help="stop scheduling new episodes after this many model calls (0 = no cap)")
    ap.add_argument("--max-decisions", type=int, default=0,
                    help="budget of TypeSafe decisions: a new episode starts only while the finished ones plus a reserve for the "
                         "running ones (their average so far) stay under it (0 = no cap)")
    ap.add_argument("--decision-usd-per-call", type=float, default=0.0, help="TypeSafe price per decision (unknown; 0 = not counted)")
    args = ap.parse_args()

    perturb = tuple(args.perturb.split(","))
    if set(perturb) - set(core.PERTURBATIONS):
        ap.error(f"--perturb must be from {core.PERTURBATIONS}")
    tasks = core.plan(args.forms, args.contexts, args.episodes_per_variant, args.split, args.goal_mode, perturb, args.only, args.teacher,
                      args.batch, args.skip)
    tasks.sort(key=lambda t: t["k"])  # round-robin over variants, so a budget stop leaves them evenly covered
    todo = [t for t in tasks if not core.EpisodeWriter.done(args.out, t["split"], t["episode_id"])]
    if core.SKIPPED:
        print(f"persona/variant pairs left out as unsolvable: {dict(core.SKIPPED)}", flush=True)
    print(f"{len(tasks)} episodes planned, {len(tasks) - len(todo)} already recorded, {len(todo)} to run", flush=True)
    if not todo:
        return
    build_page_js()
    base_url = serve(Path(args.forms).resolve())
    Path(args.costs).parent.mkdir(parents=True, exist_ok=True)
    totals = {"episodes": 0, "success": 0, "decision": 0, "text": 0, "bulk": 0, "text_cost_usd": 0.0, "teacher_steps": 0, "teacher_correct": 0}
    with ProcessPoolExecutor(args.workers) as pool, open(args.costs, "a") as costs:
        pending = list(todo)
        running = {}
        while pending or running:
            reserve = (totals["decision"] / totals["episodes"] if totals["episodes"] else args.max_steps) * (len(running) + 1)
            over = (args.max_calls and totals["decision"] + totals["text"] + totals["bulk"] >= args.max_calls) or (
                args.max_decisions and totals["decision"] + reserve > args.max_decisions)
            while pending and len(running) < args.workers and not over:
                t = pending.pop(0)
                running[pool.submit(worker, t, base_url, args.out, args.max_steps, args.wrong_rate)] = t
                reserve += reserve / len(running)
                over = over or (args.max_decisions and totals["decision"] + reserve > args.max_decisions)
            if not running:
                print(f"call budget reached; {len(pending)} episodes left for a later run")
                break
            future = next(as_completed(running))
            t = running.pop(future)
            try:
                r = future.result()
            except Exception as e:  # browser crash etc.; the .part file stays and the episode reruns next time
                r = {"episode_id": t["episode_id"], "success": False, "steps": 0, "status": "crash", "error": str(e)[:300],
                     "decision": 0, "text": 0, "text_cost_usd": 0.0}
            totals["episodes"] += 1
            totals["success"] += r["success"]
            for k in ("decision", "text", "bulk", "text_cost_usd", "teacher_steps", "teacher_correct"):
                totals[k] += r.get(k, 0)
            est = totals["text_cost_usd"] + totals["decision"] * args.decision_usd_per_call
            costs.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **r, "running": {**totals, "approx_usd": round(est, 5)}},
                                   ensure_ascii=False) + "\n")
            costs.flush()
            print(f"[{totals['episodes']}/{len(todo)}] {r['episode_id']} success={r['success']} steps={r['steps']} "
                  f"status={r['status']} teacher_ok={r.get('teacher_correct', 0)}/{r.get('teacher_steps', 0)} calls={r.get('decision', 0)}+{r.get('text', 0)}+{r.get('bulk', 0)} "
                  f"total_calls={totals['decision'] + totals['text'] + totals['bulk']} ~${est:.4f}" + (f" error={r['error']}" if r["error"] else ""), flush=True)
    print(f"done: {totals['success']}/{totals['episodes']} verified, teacher agreement "
          f"{totals['teacher_correct']}/{totals['teacher_steps']}, calls {totals['decision'] + totals['text'] + totals['bulk']}")


if __name__ == "__main__":
    main()
