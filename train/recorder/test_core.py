"""Offline tests for the verifier, planner parsing and JSONL writer. No browser, no paid APIs.

uv run --with pytest --with playwright==1.65.0 --with 'httpx[http2]' pytest train/recorder
"""

import gzip
import json

import core
import pytest

META = {
    "fields": [
        {"id": "zip", "selector": "#zip", "expected": "105", "normalize": ["nfkc", "digits"]},
        {"id": "kana", "selector": "#kana", "expected": ["ミナト", "カブシキガイシャミナト"], "normalize": ["nfkc", "strip_space"]},
        {"id": "terms", "selector": "#terms", "prop": "checked", "expected": True},
        {"id": "news", "selector": "#news", "prop": "checked", "expected": False},
        {"id": "birthday", "selector": "#bd", "expected": ""},
        {"id": "web", "selector": "#web", "expected": "https://a.example.com", "normalize": ["url"]},
        {"id": "street", "selector": "#st", "expected": "瑞光路513巷", "match": "contains", "normalize": ["nfkc", "strip_space"]},
    ]
}


def values(**over):
    base = {"zip": "１０５", "kana": "ミナト ", "terms": True, "news": False, "birthday": "", "web": "HTTPS://a.example.com/",
            "street": "內湖區 瑞光路 513 巷 22 號"}
    return {**base, **over}


def meta(tmp_path, **extra):
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"contexts": ["c.md"], "submit": True, **META, **extra}))
    return core.load_meta(path)


def test_verify_success_with_normalization(tmp_path):
    ok, results = core.verify(meta(tmp_path), values(), True, "submit")
    assert ok, results


@pytest.mark.parametrize("override", [
    {"zip": "106"}, {"terms": False}, {"news": True},
    {"birthday": "1990/01/31"},  # infeasible field must stay empty
    {"street": "瑞光路"},
])
def test_verify_rejects_wrong_values(tmp_path, override):
    ok, results = core.verify(meta(tmp_path), values(**override), True, "submit")
    assert not ok and [k for k, v in results.items() if not v["ok"]] == [next(iter(override))]


def test_verify_submission_must_match_goal_mode(tmp_path):
    m = meta(tmp_path)
    assert not core.verify(m, values(), False, "submit")[0]  # submit goal, nothing submitted
    assert not core.verify(m, values(), True, "fill")[0]  # fill goal, but the form was submitted
    blocked = meta(tmp_path, fields=[*META["fields"], {"id": "pin", "expected": "", "infeasible": True, "required": True}])
    assert core.verify(blocked, values(), False, "submit")[0]  # a required value is missing: stopping is the success


def test_corpus_meta_uses_the_corpus_scorer(tmp_path):
    raw = {"contexts": ["c.md"], "success": {"require_submitted": True}, "goal": "Fill and submit.", "fields": [
        {"key": "phone", "kind": "tel", "normalization": "phone", "expected_value_from_context": "+886 912 408 337", "required": True},
        {"key": "pw", "kind": "password", "normalization": "exact", "infeasible": True, "required": False}]}
    (tmp_path / "meta.json").write_text(json.dumps(raw))
    m = core.load_meta(tmp_path / "meta.json")
    assert m["ff"] and m["fields"][0]["selector"] == '[data-ff-key="phone"]' and not m["fields"][1]["feasible"]
    assert core.check_field(m["fields"][0], "0912-408-337")["ok"] and not core.check_field(m["fields"][0], "0912")["ok"]
    state = {"values": {"phone": "0912408337", "pw": ""}, "submitted": True}
    assert core.verify(m, state["values"], True, "submit", state)[0]
    assert not core.verify(m, state["values"], False, "submit", {**state, "submitted": False})[0]


def test_missing_element_counts_as_empty_or_unchecked_only():
    assert core.check_field({"expected": "", "id": "x"}, None)["ok"]
    assert core.check_field({"expected": False, "id": "x"}, None)["ok"]
    assert not core.check_field({"expected": "a", "id": "x"}, None)["ok"]


def test_regex_and_unknown_normalization():
    spec = {"expected": "港区芝公園3-?丁?目?5-8", "match": "regex", "normalize": ["nfkc", "strip_space"]}
    assert core.check_field(spec, "港区芝公園３丁目５－８")["ok"]
    assert core.check_field(spec, "港区芝公園3-5-8")["ok"]
    with pytest.raises(ValueError):
        core.normalize("x", ["nope"])


HEADER = {"episode_id": "f.v.train.oracle.000", "form_family": "f", "variant": "v", "split": "train", "persona": "p", "goal": "g",
          "goal_generic": "g", "goal_mode": "fill", "context_md": "日本語", "perturbation": {"kind": "none"}, "teacher_mode": "oracle",
          "seed": 1, "label_order": {"kind": "top_down", "fields": []}}


def test_writer_gzip_header_carry_forward_and_atomic_finish(tmp_path):
    w = core.EpisodeWriter(tmp_path, HEADER)
    step = {k: None for k in core.REQUIRED_STEP_KEYS} | {"step": 0, "page": {"text": "long page text"}, "elements": [{"index": "1"}]}
    w.step(step)
    with pytest.raises(ValueError):
        w.step(step)  # step 0 again: out of order
    with pytest.raises(ValueError):
        w.step({"step": 1})  # missing keys
    w.step({**step, "step": 1})  # same page: not written again
    w.step({**step, "step": 2, "page": {"text": "next page"}})
    assert not core.EpisodeWriter.done(tmp_path, "train", HEADER["episode_id"])  # still a .part file
    w.finish({"episode_id": HEADER["episode_id"], "type": "summary", "success": True, "verified_fields": {}, "steps": 3, "error": None})
    path = core.EpisodeWriter.final_path(tmp_path, "train", HEADER["episode_id"])
    assert core.EpisodeWriter.done(tmp_path, "train", HEADER["episode_id"]) and not list(tmp_path.rglob("*.part"))
    raw = [json.loads(line) for line in gzip.open(path, "rt", encoding="utf-8")]
    assert raw[0]["type"] == "episode" and "page" in raw[1] and "page" not in raw[2] and "context_md" not in raw[1]
    out = list(core.read_episode(path))
    assert [r.get("type") for r in out] == [None, None, None, "summary"]
    assert [r["page"]["text"] for r in out[:3]] == ["long page text", "long page text", "next page"]
    assert out[1]["context_md"] == "日本語" and out[1]["elements"] == [{"index": "1"}] and out[2]["episode_id"] == HEADER["episode_id"]


def test_plan_is_deterministic_cycles_perturbations_and_respects_the_split(tmp_path):
    for variant, split in (("v1", "train"), ("v2", "eval"), ("fx", "smoke")):
        form = tmp_path / "forms" / "fam" / variant
        form.mkdir(parents=True)
        (form / "meta.json").write_text(json.dumps({"contexts": ["c.md"], "submit": True, "split": split, "fields": []}))
    (tmp_path / "c.md").write_text("ctx")
    a = core.plan(tmp_path / "forms", tmp_path, 3, perturb=("none", "wrong"), split="train")
    assert a == core.plan(tmp_path / "forms", tmp_path, 3, perturb=("none", "wrong"), split="train")
    assert sorted(t["perturbation"] for t in a) == ["none", "none", "wrong"]
    assert {t["goal_mode"] for t in a} == {"submit"} and a[0]["episode_id"] == "fam.v1.train.checked.000"
    everything = core.plan(tmp_path / "forms", tmp_path, 1)
    assert {t["split"] for t in everything} == {"train", "eval"}  # smoke fixtures only on request; --split never relabels
    assert [t["split"] for t in core.plan(tmp_path / "forms", tmp_path, 1, only=["fam/fx"])] == ["smoke"]


def test_parse_fills_keeps_only_offered_fields_and_options():
    fields = [
        {"node": 5, "widget": "text", "label": "", "hint": "姓 名", "part": "1/2"},
        {"node": 6, "widget": "select", "label": "City", "options": [{"id": "tp", "label": "臺北市"}]},
        {"node": 7, "widget": "check", "label": "News", "value": "off", "options": [{"id": "on", "label": "checked"}, {"id": "off", "label": "unchecked"}]},
    ]
    out = {"fills": [{"index": "1", "value": "佐藤"}, {"index": "1", "value": "dup"}, {"index": "2", "option": "臺北市"},
                     {"index": "3", "option": "off"}, {"index": "9", "value": "x"}, {"index": "2", "option": "nope"}]}
    assert core.parse_fills(out, fields) == [
        {"node": 5, "label": "姓 名 (part 1/2)", "value": "佐藤"},
        {"node": 6, "label": "City", "value": "臺北市", "option": "tp"},
    ]
    assert core.parse_fills({"fills": "bad"}, fields) == [] and core.parse_fills(None, fields) == []


def test_fill_goal_switches_finish_line_by_mode():
    planned = [{"label": "Name", "value": "Dana"}]
    assert "Do not submit" in core.fill_goal(planned, "ctx", "fill")
    assert "CLICK the button that submits" in core.fill_goal(planned, "ctx", "submit")
    assert "- Name: Dana" in core.fill_goal(planned, "ctx", "fill")


def test_personas_follow_the_corpus_contract_and_stay_in_their_split(tmp_path):
    form = tmp_path / "forms" / "fam" / "v"
    form.mkdir(parents=True)
    raw = {"family": "fam", "variant": "v", "contexts": ["a.md"], "split": "train", "success": {"require_submitted": True},
           "goal": "Fill and submit.", "personas": ["a", "fam/t-b", "fam/e-c"],
           "fields": [{"key": "name", "kind": "text", "normalization": "text", "expected_value_from_context": "x", "required": True},
                      {"key": "pin", "kind": "text", "normalization": "exact", "expected_value_from_context": "x", "required": True}]}
    (form / "meta.json").write_text(json.dumps(raw))
    (tmp_path / "fam").mkdir()
    people = {"a": ("train", {"name": "Ann", "pin": "1"}, [], True), "fam/t-b": ("train", {"name": ["Bo", "Bo Li"], "pin": ""}, ["pin"], False),
              "fam/e-c": ("eval", {"name": "Cy", "pin": "3"}, [], True)}
    for pid, (split, fields, infeasible, submit) in people.items():
        (tmp_path / f"{pid}.md").write_text(pid)
        (tmp_path / f"{pid}.expected.json").write_text(json.dumps({"persona": pid, "context": pid + ".md", "split": split, "variants": {
            "fam/v": {"submit": submit, "fields": fields, "infeasible": infeasible, "hidden": [], "prefill": {"right": {}, "wrong": {}}}}}))
    tasks = core.plan(tmp_path / "forms", tmp_path, 8, perturb=("none", "wrong", "reject"))
    assert sorted(t["persona"] for t in tasks) == ["a"] * 4 + ["fam/t-b"] * 4  # balanced; the eval persona never enters train
    assert {t["perturbation"] for t in tasks} == {"none", "wrong"}  # the variant has no rejected first submit
    assert [t["k"] for t in tasks] == list(range(8))
    b = core.load_meta(form / "meta.json", core.persona_expected(tmp_path, "fam/t-b"))
    assert b["fields"][0]["expected"] == ["Bo", "Bo Li"] and not b["fields"][1]["feasible"] and not b["expect_submitted"]
    state = {"values": {"name": "bo li", "pin": ""}, "submitted": False}
    assert core.verify(b, state["values"], False, "submit", state)[0]  # stopping without submit is this persona's success


def test_label_order_is_seeded_and_a_permutation():
    import random

    kinds = {core.order_for(12, random.Random(i))[0] for i in range(60)}
    assert kinds == {"top_down", "local_swaps", "shuffled"}
    assert core.order_for(12, random.Random(7)) == core.order_for(12, random.Random(7))
    assert sorted(core.order_for(12, random.Random(3))[1]) == list(range(12))
