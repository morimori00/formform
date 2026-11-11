"""Oracle tests on small HTML snippets in headless Chromium. No model calls (oracle mode never loads keys).

uv run --with pytest --with playwright==1.65.0 --with 'httpx[http2]' pytest train/recorder
"""

import json

import core
import oracle
import pytest
import record

SUBMIT = "<button id=go onclick=\"window.__submitted={name:document.getElementById('name')?.value}\">Send</button>"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    record.build_page_js()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def run(browser, tmp_path, body, fields, submit=True, perturbation="none"):
    form = tmp_path / "forms" / "t" / "v"
    form.mkdir(parents=True, exist_ok=True)
    (form / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>t</title><body>{body}</body>")
    (form / "meta.json").write_text(json.dumps({"contexts": ["c.md"], "submit": submit, "submit_selectors": ["#go"], "fields": fields}))
    (form / "c.md").write_text("ctx")
    task = core.plan(tmp_path / "forms", tmp_path, 1, perturb=(perturbation,), only=["t/v"], teacher="oracle")[0]
    result = record.Episode(task, (tmp_path / "forms").as_uri() + "/", tmp_path / "out", 40).run(browser, record.load_jev_model())
    records = list(core.read_episode(core.EpisodeWriter.final_path(tmp_path / "out", task["split"], task["episode_id"])))
    labels = [(r["label"]["operation"], (r["action"] or {}).get("label"), r["label"]["text"]) for r in records[:-1]]
    return result, labels, records


def test_native_widgets_submit_and_no_needless_toggle(browser, tmp_path):
    body = """<label>Name <input id=name></label>
      <label>Plan <select id=plan><option value="">-</option><option value=a>Basic</option><option value=b>Pro</option></select></label>
      <label><input type=checkbox id=terms checked> Terms</label><label><input type=checkbox id=news checked> News</label>
      <label><input type=radio name=size value=s> Small</label><label><input type=radio name=size value=l> Large</label>
      <label>PIN <input id=pin></label>""" + SUBMIT
    fields = [{"id": "name", "selector": "#name", "expected": "Dana"}, {"id": "plan", "selector": "#plan", "kind": "select", "expected": "b"},
              {"id": "terms", "selector": "#terms", "kind": "checkbox", "expected": True},
              {"id": "news", "selector": "#news", "kind": "checkbox", "expected": False},
              {"id": "size", "selector": "input[name=size]", "kind": "radio", "expected": "l"},
              {"id": "pin", "selector": "#pin", "expected": "", "infeasible": True}]
    result, labels, records = run(browser, tmp_path, body, fields)
    assert result["success"] and result["status"] == "done"
    assert sorted(labels[:4]) == sorted([("TYPE_TEXT", "Name", "Dana"), ("SELECT", "Plan → Pro", None), ("CLICK", "News", None),
                                         ("CLICK", "Large", None)])  # field order is sampled per episode
    assert labels[4:] == [("CLICK", "Send", None), ("DONE", None, None)]
    first = records[0]
    assert {a["operation"] for a in first["acceptable"]} == {"TYPE_TEXT", "SELECT", "CLICK"}  # any unfinished field is valid
    focus = [a for a in first["acceptable"] if a.get("prelude")]
    assert [a["field"] for a in focus] == ["name"]  # clicking into the text field first is accepted, never the label
    assert first["goal_planned_oracle"].count("- Name: Dana") == 1 and first["goal_generic"] == first["goal"]
    assert first["label_source"] == "oracle" and first["teacher"] is None and first["context_md"] == "ctx"


def test_dropdown_and_autocomplete_need_the_option_click(browser, tmp_path):
    body = """<span id=l>Country</span><button id=dd aria-haspopup=listbox aria-expanded=false aria-labelledby="l dd">Choose</button>
      <ul id=list role=listbox hidden><li role=option>Japan</li><li role=option>Taiwan</li></ul>
      <input id=city role=combobox aria-label=City aria-expanded=false aria-controls=hits><ul id=hits role=listbox hidden></ul>
      <script>
      dd.onclick = () => { list.hidden = !list.hidden; dd.setAttribute('aria-expanded', String(!list.hidden)); };
      list.onclick = e => { dd.textContent = e.target.textContent; list.hidden = true; dd.setAttribute('aria-expanded', 'false'); };
      city.oninput = () => { hits.innerHTML = '<li role=option>Taipei</li>'; hits.hidden = false; city.setAttribute('aria-expanded', 'true'); };
      hits.onmousedown = e => { e.preventDefault(); city.value = e.target.textContent; hits.hidden = true; city.setAttribute('aria-expanded', 'false'); };
      </script>"""
    fields = [{"id": "country", "selector": "#dd", "kind": "dropdown", "expected": "Taiwan"},
              {"id": "city", "selector": "#city", "kind": "combobox", "expected": "Taipei"}]
    result, labels, records = run(browser, tmp_path, body, fields, submit=False)
    assert result["success"]
    assert [x[0] for x in labels] == ["CLICK", "CLICK", "TYPE_TEXT", "CLICK", "DONE"]
    assert labels[1][1] == "Taiwan" and labels[3][1] == "Taipei"
    assert [a["operation"] for a in records[3]["acceptable"]] == ["CLICK"]  # open suggestion list: only the option click


def test_required_value_missing_ends_blocked_without_submit(browser, tmp_path):
    body = "<label>Name <input id=name></label><label>Password <input id=pw type=text required></label>" + SUBMIT
    fields = [{"id": "name", "selector": "#name", "expected": "Dana"},
              {"id": "pw", "selector": "#pw", "expected": "", "infeasible": True, "required": True}]
    result, labels, _ = run(browser, tmp_path, body, fields)
    assert [x[0] for x in labels] == ["TYPE_TEXT", "BLOCKED"]
    assert result["success"] and result["status"] == "blocked"  # not submitting is the verified outcome


def test_wait_for_delayed_render_then_scroll_to_offscreen_field(browser, tmp_path):
    body = """<div id=root></div><script>setTimeout(() => { root.innerHTML =
      '<label>Name <input id=name></label><div style="height:1500px"></div><label>Note <input id=note></label>'; }, 600);</script>"""
    fields = [{"id": "name", "selector": "#name", "expected": "Dana"}, {"id": "note", "selector": "#note", "expected": "hi"}]
    result, labels, _ = run(browser, tmp_path, body, fields, submit=False)
    ops = [x[0] for x in labels]
    assert result["success"] and ops[0] == "WAIT"
    assert [o for o in ops if o != "WAIT"][:2] == ["TYPE_TEXT", "SCROLL_DOWN"] and ops[-2:] == ["TYPE_TEXT", "DONE"]


def test_wrong_prefilled_value_is_replaced(browser, tmp_path):
    body = "<label>Name <input id=name></label>"
    result, labels, records = run(browser, tmp_path, body, [{"id": "name", "selector": "#name", "expected": "Dana Whitfield"}],
                                  submit=False, perturbation="wrong")
    assert records[0]["perturbation"]["wrong"] == "Dana Wh" and "Please check" in records[0]["page"]["text"]
    assert [(x[0], x[2]) for x in labels] == [("TYPE_TEXT", "Dana Whitfield"), ("DONE", None)] and result["success"]


def test_judge_uses_the_verifier_normalization():
    meta = {"fields": [{"id": "phone", "expected": ["2065550142"], "normalize": ["digits"]}]}
    items = [{"operation": "TYPE_TEXT", "target": "3", "text": "2065550142", "field": "phone", "check": {"mode": "field"}},
             {"operation": "TYPE_TEXT", "target": "4", "text": "Taipei City", "check": {"mode": "substring", "of": ["Taipei City", "TPE"]}},
             {"operation": "TYPE_TEXT", "target": "5", "text": "11/28/2026", "check": {"mode": "date", "text": "11/28/2026"}}]
    assert oracle.judge(items, "TYPE_TEXT", "3", "(206) 555-0142", meta)
    assert not oracle.judge(items, "TYPE_TEXT", "3", "206-555-0143", meta)
    assert not oracle.judge(items, "CLICK", "3", None, meta) and not oracle.judge(items, "TYPE_TEXT", "9", "2065550142", meta)
    assert oracle.judge(items, "TYPE_TEXT", "4", "taipei", meta) and not oracle.judge(items, "TYPE_TEXT", "4", "Tokyo", meta)
    assert oracle.judge(items, "TYPE_TEXT", "5", "11-28-2026", meta) and not oracle.judge(items, "TYPE_TEXT", "5", "2026-11-28", meta)
    assert oracle.pick(items, teacher_node=None, avoid={("TYPE_TEXT", "3")})["target"] == "4"
    assert oracle.pick(items, rank={"phone": 2})["target"] == "4"  # this episode prefers another field first
