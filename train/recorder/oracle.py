"""Oracle: the set of acceptable next decisions for an observation, from meta.json expected values. No model calls.

decide() is a pure function of one observation (page.ts observe(): element table + probe + the page's own state)
and the normalized meta (core.load_meta). It returns every acceptable decision in preference order (meta field order):
any unfinished field in view is a valid next target; multi-step widgets contribute their next interaction.
"""

import json
import re

import core

TEXT_KINDS = {"text", "tel", "email", "number", "textarea", "password", "date", "editable"}
SELECT_KINDS = {"select", "cascade"}
DATE_FORMATS = {"YYYY-MM-DD": "{y}-{m}-{d}", "MM/DD/YYYY": "{m}/{d}/{y}", "DD/MM/YYYY": "{d}/{m}/{y}",
                "YYYY-DD-MM": "{y}-{d}-{m}", "YYYY/MM/DD": "{y}/{m}/{d}", "DD.MM.YYYY": "{d}.{m}.{y}"}


class Table:
    """Decision targets of the snapshot, by DOM node (jev action_space numbering)."""

    def __init__(self, snap, action_space):
        self.elements, targets, controls = action_space(snap["actions"])
        self.targets, self.control_actions = targets, controls
        self.click = {a["node"]: t for t, a in targets.get("CLICK", {}).items()}
        self.fill = {a["node"]: t for t, a in targets.get("TYPE_TEXT", {}).items()}
        self.select = {(a["node"], a["value"]): t for t, a in targets.get("SELECT", {}).items()}
        self.controls = set(controls)
        self.labels = {}
        for a in snap["actions"]:
            if a.get("node") and a["kind"] != "select":
                self.labels.setdefault(a["node"], a["label"].removeprefix("Open ") if a["kind"] == "click" and a["node"] in self.fill else a["label"])
            elif a.get("node"):
                self.labels.setdefault(a["node"], a["label"].split(" → ")[0])


def current(f, d, state):
    """Raw current value of a field: the page's state hook when it has one, else the DOM probe. None = not on the page."""
    if f["source"] == "hook":
        return ((state or {}).get("values") or {}).get(f["key"])
    if d is None:
        return None
    k = f["kind"]
    if k in SELECT_KINDS:
        return d["selects"][0]["label" if f.get("prop") == "label" else "value"] if d["selects"] else None
    if k == "radio":
        return next((x["value"] for x in d["inputs"] if x["checked"]), "")
    if k == "ariaradio":
        return next((x["value"] for x in d["radios"] if x["checked"]), "")
    if k in ("checkbox", "switch"):
        return bool(d["checked"])
    if k == "checks":
        return sorted(x["value"] for x in d["inputs"] if x["checked"])
    if k == "dropdown":
        return d["data"].get("value", d["text"])
    if k == "static":
        return d["text"]
    return d["value"]


def values(meta, obs, final=True):
    """Field id -> raw value. final=True prefers what the page actually submitted (source: submitted)."""
    out = {}
    for f, d in zip(meta["fields"], obs["probe"]):
        if final and f["source"] == "submitted" and obs["submitted"] is not None:
            out[f["id"]] = obs["submitted"].get(f["key"])
        else:
            out[f["id"]] = current(f, d, obs["state"])
    return out


def is_submitted(obs):
    return obs["submitted"] is not None or bool((obs["state"] or {}).get("submitted"))


def _option(options, value):
    return next((o for o in options if o["value"] == value), None) or next((o for o in options if o["label"] == value), None)


def _combobox_labels(f, d):
    """(text to type, strings a typed query may be a substring of) for an autocomplete field."""
    try:
        row = next(o for o in json.loads(d["data"].get("ffOptions", "[]")) if o[0] == f["value"])
        return row[1], [s for s in row[1:] if s]
    except (StopIteration, ValueError):
        return f["value"], [f["value"]]


def format_date(iso, fmt):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return DATE_FORMATS.get(fmt, "{y}-{m}-{d}").format(y=m[1], m=m[2], d=m[3]) if m else iso


def display(f, d):
    """How the expected value reads on the page (option label, formatted date) — for the product-shaped goal."""
    v, k = f["value"], f["kind"]
    if d is None:
        return str(v)
    if k in SELECT_KINDS:
        return (_option(d["selects"][0]["options"], v) or {"label": v})["label"] if d["selects"] else v
    if k in ("radio", "checks"):
        want = v if isinstance(v, list) else [v]
        return ", ".join(x["label"] or x["value"] for x in d["inputs"] if x["value"] in want) or str(v)
    if k == "ariaradio":
        return (_option(d["radios"], v) or {"label": v})["label"]
    if k in ("checkbox", "switch"):
        return "checked" if v else "unchecked"
    if k == "dropdown":
        return (_option((d.get("popup") or {}).get("options", []), v) or {"label": v})["label"]
    if k == "combobox":
        return _combobox_labels(f, d)[0]
    if k == "datepicker":
        return format_date(v, d["data"].get("ffFormat"))
    return str(v)


def wants(f, d, cur, clear):
    """Next widget interactions for an unfinished field: [(operation, probe element, argument, text check)]."""
    k, v = f["kind"], f["value"]
    if clear:  # must be empty/unchecked but is not
        if k in TEXT_KINDS or k in ("combobox", "datepicker"):
            return [("TYPE_TEXT", d, "", {"mode": "empty"})]
        if k in ("checkbox", "switch"):
            return [("CLICK", d, None, None)]
        if k == "checks":
            return [("CLICK", x, None, None) for x in d["inputs"] if x["checked"]]
        if k in SELECT_KINDS and d["selects"] and _option(d["selects"][0]["options"], ""):
            return [("SELECT", d["selects"][0], "", None)]
        return []
    if k in TEXT_KINDS:
        return [("TYPE_TEXT", d, str(v), {"mode": "field"})]
    if k in SELECT_KINDS:
        s = d["selects"][0] if d["selects"] else None
        o = s and _option(s["options"], v)
        return [("SELECT", s, o["value"], None)] if o and not o["disabled"] else [("WAIT", None, None, None)]
    if k == "radio":
        return [("CLICK", x, None, None) for x in d["inputs"] if x["value"] == v]
    if k == "ariaradio":
        o = _option(d["radios"], v)
        return [("CLICK", o, None, None)] if o else []
    if k in ("checkbox", "switch"):
        return [("CLICK", d, None, None)]
    if k == "checks":
        return [("CLICK", x, None, None) for x in d["inputs"] if x["checked"] != (x["value"] in v)]
    popup = d.get("popup") or {"open": False, "options": []}
    if k == "dropdown":
        o = _option(popup["options"], v)
        return [("CLICK", o, None, None)] if popup["open"] and o else [("CLICK", d, None, None)]
    if k == "combobox":
        typed, accepted = _combobox_labels(f, d)
        o = _option(popup["options"], v) or _option(popup["options"], typed)
        if popup["open"] and o:
            return [("CLICK", o, None, None)]
        if popup["open"] and core.normalize(d["value"], ["trim", "casefold"]) == typed.strip().casefold():
            return [("WAIT", None, None, None)]  # suggestions are still loading; retyping would restart the search
        return [("TYPE_TEXT", d, typed, {"mode": "substring", "of": accepted})]
    if k == "datepicker":
        cal, out = d.get("cal"), []
        y, m = str(v)[:4], str(int(str(v)[5:7]))
        if cal and cal["open"]:
            if cal["y"]["value"] != y:
                out.append(("SELECT", cal["y"], y, None))
            if cal["m"]["value"] != m:
                out.append(("SELECT", cal["m"], m, None))
            if not out:
                out += [("CLICK", c, None, None) for c in cal["cells"] if c["iso"] == v]
        if d["readOnly"]:
            return out or [("CLICK", cal["btn"], None, None)]
        text = format_date(v, d["data"].get("ffFormat"))
        return out + [("TYPE_TEXT", d, text, {"mode": "date", "text": text})]
    if k == "rocdate":
        want = [str(int(str(v)[:4]) - 1911), str(int(str(v)[5:7])), str(int(str(v)[8:10]))]
        return [("SELECT", s, w, None) for s, w in zip(d["selects"], want) if s["value"] != w]
    return []


def text_ok(item, text, meta):
    """Is the teacher's TYPE_TEXT string acceptable for this oracle item? Same normalization as the verifier."""
    check = item.get("check") or {"mode": "exact"}
    if not isinstance(text, str):
        return False
    if check["mode"] == "empty":
        return text == ""
    if check["mode"] == "field":
        return core.check_field(next(f for f in meta["fields"] if f["id"] == item["field"]), text)["ok"]
    if check["mode"] == "substring":
        q = text.strip().casefold()
        return bool(q) and any(q in s.casefold() for s in check["of"])
    if check["mode"] == "date":
        return re.split(r"[-/.]", text.strip()) == re.split(r"[-/.]", check["text"])
    return text == item.get("text")


def judge(items, operation, target, text, meta):
    """The acceptable item the teacher's decision matches, or None."""
    for item in items:
        if item["operation"] == operation and item.get("target") == target and (operation != "TYPE_TEXT" or text_ok(item, text, meta)):
            return item
    return None


def same_target(items, operation, target):
    return next((i for i in items if i["operation"] == operation and i.get("target") == target), None)


def decide(meta, obs, goal_mode, table, last_click=None):
    """Acceptable next decisions, best first: [{operation, target, text?, field?, node?, check?}]. Never empty.
    last_click: node of the previous executed click, so "click the field, then type" is accepted once, not as a loop."""
    control = lambda op: [{"operation": op, "target": None}]  # noqa: E731
    state = obs["state"]
    if is_submitted(obs):
        return control("DONE")
    rendered = any(d and (d["shown"] or d.get("hidden", {}).get("by") == "tab") for d in obs["probe"])
    if (state is not None and not state.get("ready", True)) or not rendered:
        return control("WAIT")  # delayed render, or between two views
    step = (state or {}).get("step")
    applicable = set(state["visible"]) if state and "visible" in state else None
    items, preludes, tabs, scrolls, waiting, earlier, blocked, closers, open_items = [], [], [], [], False, False, False, [], None

    def resolve(op, m, arg, check, f):
        """Map a wanted interaction to a decision target, or note why it is not possible right now."""
        nonlocal waiting
        if op == "WAIT" or m is None:
            waiting = True
            return None
        node = m["node"]
        target = table.select.get((node, arg)) if op == "SELECT" else (table.fill if op == "TYPE_TEXT" else table.click).get(node)
        if target is None:
            if m["pos"] in ("above", "below"):
                scrolls.append("SCROLL_UP" if m["pos"] == "above" else "SCROLL_DOWN")
            else:
                waiting = True  # disabled, covered, or not rendered yet
            return None
        item = {"operation": op, "target": target, "field": f["id"], "node": node}
        if op == "TYPE_TEXT":
            item.update(text=arg, check=check)
        return item

    for f, d in zip(meta["fields"], obs["probe"]):
        if f["kind"] == "static" or (applicable is not None and f.get("key") not in applicable):
            continue
        page = f.get("page")
        off_page = d is None or (step is not None and page is not None and page != step) or (
            step is None and not d["shown"] and d.get("hidden", {}).get("by") == "page")
        cur = current(f, d, state)
        ok = core.check_field(f, cur)["ok"]
        opened = d is not None and ((d.get("popup") or {}).get("open") or (d.get("cal") or {}).get("open"))
        if f["kind"] == "combobox" and f["source"] != "hook" and d is not None and (opened or d["error"]):
            ok = False  # typed but not committed by choosing a suggestion
        if ok or off_page:
            if not ok and f["feasible"] and step is not None and page is not None and page < step:
                earlier = True  # a field on a previous step is wrong: go back
            if ok and opened and f["kind"] != "combobox":  # a finished widget left open covers its neighbours
                closers.append({"operation": "CLICK", "target": table.click.get((d.get("cal") or {}).get("btn", d)["node"]), "field": f["id"]})
            if not f["feasible"] and f.get("required") and not off_page and core.empty(cur):
                blocked = True
            continue
        clear = core.empty(f["value"])
        if d.get("hidden", {}).get("by") == "cond":
            continue
        if not d["shown"] and d.get("hidden", {}).get("by") == "tab":
            tab = resolve("CLICK", d["hidden"]["tab"], None, None, f)
            tabs += [tab] if tab and tab["target"] not in [t["target"] for t in tabs] else []
            continue
        before = len(scrolls)
        got = [i for i in (resolve(*w, f) for w in wants(f, d, cur, clear)) if i]
        if opened and open_items is None:  # the wanted option may be below the fold of the window
            open_items = got or control(scrolls[before] if scrolls[before:] and scrolls[before] in table.controls else "WAIT")
        items += [i for i in got if i not in items]
        # Clicking into a plain text field before typing is harmless (focus only). Not for autocomplete/pickers,
        # where the click can open a list that then has to be dealt with.
        if f["kind"] in TEXT_KINDS and not opened:
            preludes += [{"operation": "CLICK", "target": table.click[i["node"]], "field": f["id"], "node": i["node"], "prelude": True}
                         for i in got if i["operation"] == "TYPE_TEXT" and i["node"] in table.click and i["node"] != last_click]

    if open_items:  # finish the open popup first: acting elsewhere closes it (and it may cover other fields)
        return open_items
    closers = [c for c in closers if c["target"]]
    if closers:
        return closers[:1]
    if items:
        return items + preludes
    if tabs:  # only once the open tab is finished, or tabs would ping-pong
        return tabs
    if scrolls and scrolls[0] in table.controls:
        return control(scrolls[0])
    if waiting:
        return control("WAIT")
    if earlier:
        return _button(obs["buttons"][len(meta["submit_selectors"]):], table) or control("BLOCKED")
    if blocked and goal_mode == "submit":
        return control("BLOCKED")  # a required value is not in the context
    if goal_mode != "submit":
        return control("DONE")
    return _button(obs["buttons"][:len(meta["submit_selectors"])], table) or control("WAIT")


def _button(buttons, table):
    for b in buttons:
        if b and b["node"] in table.click:
            return [{"operation": "CLICK", "target": table.click[b["node"]], "node": b["node"], "submit": True}]
    for b in buttons:
        if b and b["pos"] in ("above", "below"):
            op = "SCROLL_UP" if b["pos"] == "above" else "SCROLL_DOWN"
            if op in table.controls:
                return [{"operation": op, "target": None}]
    return None


def pick(items, teacher_node=None, avoid=(), rank=None):
    """The training label among acceptable decisions: the teacher's own field when it had the right idea, else the
    first in this episode's field order (rank: field id -> position). A focus-only click is never the label."""
    direct = [i for i in items if not i.get("prelude")]
    usable = [i for i in direct if (i["operation"], i.get("target")) not in avoid] or direct
    usable = sorted(usable, key=lambda i: (rank or {}).get(i.get("field"), -1))  # stable: ties keep page order
    return next((i for i in usable if teacher_node is not None and i.get("node") == teacher_node), usable[0])


def planned(meta, obs, table):
    """The fields of the current page/step with their correct values, as a perfect Bulk Fill would plan them (for
    fillGoal). Lists finished fields too, so the goal stays the same for a whole page."""
    out = []
    state = obs["state"] or {}
    applicable = set(state["visible"]) if "visible" in state else None
    for f, d in zip(meta["fields"], obs["probe"]):
        if d is None or not f["feasible"] or core.empty(f["value"]) or f["kind"] == "static":
            continue
        if (applicable is not None and f.get("key") not in applicable) or (
                f.get("page") != state["step"] if "step" in state and f.get("page") is not None
                else not d["shown"] and d.get("hidden", {}).get("by") != "tab"):
            continue
        out.append({"label": table.labels.get(d["node"]) or f.get("label") or f["id"], "value": display(f, d)})
    return out


def public(items):
    """The acceptable set as stored in a step record."""
    return [{k: i[k] for k in ("operation", "target", "text", "field", "prelude") if k in i} for i in items]


def field_nodes(obs):
    """Nodes that belong to a known field's widget. A wrong click on one of these is recoverable; other clicks may submit."""
    nodes = set()
    for d in obs["probe"]:
        if d:
            cal = d.get("cal") or {}
            parts = [d, *d["selects"], *d["inputs"], *d["radios"], *(d.get("popup") or {}).get("options", []), *cal.get("cells", [])]
            nodes.update(m["node"] for m in parts + ([cal["btn"]] if cal else []))
    return nodes
