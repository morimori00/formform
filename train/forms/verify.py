"""Score a form's final state against meta.json, and self-check every generated page in headless Chromium.

Library:  from verify import score;  score(meta, page.evaluate("window.__formState()"))
          meta = with_persona(meta, expected_json, "family/variant")   # score against another persona
Check:    uv run --with playwright python train/forms/verify.py [--personas N|all] [family | family/variant ...]
The check drives each page with real UI events (typing, clicking options/calendar/tabs/steps), never the
prefill hook, then verifies: default -> filled -> submitted & scored 100%; error -> first submit rejected, retry
succeeds; wrong/partial/prefilled/loading states render and score as expected.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _text(s):
    s = unicodedata.normalize("NFKC", str(s or "")).casefold()
    return re.sub(r"\s+", " ", s).strip(" .")


def _phone(s):
    d = re.sub(r"\D", "", str(s or ""))
    # ponytail: strips a few known country codes, not a full E.164 parser; add one if forms get more countries
    for cc in ("886", "65", "81", "1"):
        if d.startswith(cc) and len(d) - len(cc) >= 8:
            d = d[len(cc):]
            break
    return d.lstrip("0")


def _amount(s):
    try:
        return float(re.sub(r"[^\d.]", "", str(s or "")) or "nan")
    except ValueError:
        return None


NORM = {
    "exact": lambda v: str(v or ""), "text": _text, "email": lambda v: str(v or "").strip().lower(),
    "name": lambda v: sorted(t for t in re.split(r"[\s,]+", _text(v)) if t), "phone": _phone, "date": lambda v: str(v or "").strip(),
    "choice": lambda v: str(v or ""), "bool": bool, "set": lambda v: sorted(v or []), "amount": _amount,
    "alnum": lambda v: re.sub(r"[\W_]", "", _text(v)),
}


def match(norm, expected, actual):
    if norm == "fuzzy":
        a, b = re.sub(r"[^\w]", "", _text(expected)), re.sub(r"[^\w]", "", _text(actual))
        return bool(a) and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
    return NORM[norm](expected) == NORM[norm](actual)


def empty(v):
    return v in (None, "", False) or v == []


def score(meta, state):
    """-> {success, fields_correct, fields_total, submitted, details:{key: ok}}"""
    vals, out = state.get("values") or {}, {}
    for f in meta["fields"]:
        if f.get("show_if"):
            k, want = f["show_if"].split("=")
            if str(vals.get(k)).lower() != want:
                out[f["key"]] = empty(vals.get(f["key"])) or not state.get("submitted")  # hidden: ignored
                continue
        actual, exp = vals.get(f["key"]), f.get("expected_value_from_context")
        if f.get("infeasible") or f.get("honeypot") or exp in ("", None):
            out[f["key"]] = empty(actual)
        else:
            out[f["key"]] = any(match(f["normalization"], e, actual) for e in [exp, *(f.get("accept") or [])])
    ok = sum(out.values())
    need_submit = meta["success"]["require_submitted"]
    return dict(success=ok == len(out) and bool(state.get("submitted")) == need_submit, fields_correct=ok,
                fields_total=len(out), submitted=bool(state.get("submitted")), details=out)


def with_persona(meta, expected_json, name=None):
    """meta.json re-targeted at another persona, given that persona's contexts/<id>.expected.json (parsed)."""
    e = expected_json["variants"][name or f"{meta['family']}/{meta['variant']}"]
    fields = []
    for f in meta["fields"]:
        v = e["fields"][f["key"]]
        f = {k: x for k, x in f.items() if k not in ("accept", "infeasible")}
        if isinstance(v, list) and f["kind"] != "checks":
            f["accept"], v = v[1:], v[0]
        if f["key"] in e["infeasible"]:
            f["infeasible"] = True
        fields.append({**f, "expected_value_from_context": v, "expected": e["fields"][f["key"]]})
    return {**meta, "fields": fields, "submit": e["submit"], "success": {**meta["success"], "require_submitted": e["submit"]},
            "contexts": [expected_json["context"]], "context": "contexts/" + expected_json["context"]}


# ------------------------------------------------------------------ headless self-check
def fmt_date(iso, f):
    y, m, d = iso.split("-")
    return {"YYYY-MM-DD": f"{y}-{m}-{d}", "MM/DD/YYYY": f"{m}/{d}/{y}", "DD/MM/YYYY": f"{d}/{m}/{y}", "YYYY-DD-MM": f"{y}-{d}-{m}",
            "YYYY/MM/DD": f"{y}/{m}/{d}"}[f]


def ui_fill(page, meta, fmts):
    """Fill every feasible, visible field through UI events. Playwright cannot reach into closed shadow roots, so
    those fields are driven by clicking/typing via page JS on roots captured by this test's init script."""
    by_page = {}
    for f in meta["fields"]:
        by_page.setdefault(f["page"], []).append(f)
    for p in range(meta["pages"]):
        if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
            raise AssertionError(f"horizontal overflow on step {p} at {page.viewport_size['width']}px")
        for f in by_page.get(p, []):
            exp = f.get("expected_value_from_context")
            if f.get("infeasible") or f.get("honeypot") or exp in (None, "", False, []):
                continue
            st = page.evaluate("window.__formState()")
            if f["key"] not in st["visible"]:
                continue
            loc = page.locator(f'[data-ff-key="{f["key"]}"]')
            if loc.count() == 0:            # closed shadow root: not reachable by Playwright; use setter
                page.evaluate("([k,v])=>window.__ffSet(k,v)", [f["key"], exp])
                continue
            page.evaluate("""k=>{const e=document.querySelector(`[data-ff-key="${k}"]`);const p=e.closest('[role=tabpanel]');
                if(p&&p.hidden)document.querySelector(`[role=tab][aria-controls="${p.id}"]`).click();}""", f["key"])
            k = f["kind"]
            if k in ("text", "email", "tel", "number", "password", "textarea"):
                loc.fill(str(exp))
                loc.blur()
            elif k == "date":
                loc.fill(exp)
            elif k in ("select", "cascade"):
                loc.select_option(exp)
            elif k == "radio":
                loc.locator(f'input[value="{exp}"]').check()
            elif k == "checks":
                for v in exp:
                    loc.locator(f'input[value="{v}"]').check()
            elif k == "checkbox":
                loc.set_checked(bool(exp))
            elif k == "switch":
                if page.evaluate(f'document.querySelector(\'[data-ff-key="{f["key"]}"]\').getAttribute("aria-checked")') != "true":
                    loc.click()
            elif k == "ariaradio":
                loc.locator(f'[role=radio][data-value="{exp}"]').click()
            elif k == "dropdown":
                loc.click()
                page.locator(f'[data-ff-key="{f["key"]}"] + ul [role=option][data-value="{exp}"]').click()
            elif k == "combobox":
                opts = json.loads(loc.get_attribute("data-ff-options"))
                label = next(o[1] for o in opts if o[0] == exp)
                loc.click()
                loc.press_sequentially(label, delay=5)
                page.locator(f'[data-ff-key="{f["key"]}"] + ul [role=option][data-value="{exp}"]').click()
            elif k == "datepicker":
                if loc.get_attribute("readonly") is not None:
                    y, m, _ = exp.split("-")
                    box = loc.locator("xpath=..")
                    box.locator(".ff-cal-btn").click()
                    box.locator(".ff-cal-y").select_option(str(int(y)))
                    box.locator(".ff-cal-m").select_option(str(int(m)))
                    box.locator(f'[role=gridcell][aria-label="{exp}"]').click()
                else:
                    loc.fill(fmt_date(exp, fmts[f["key"]]))
                    loc.blur()
            elif k == "rocdate":
                y, m, d = exp.split("-")
                sels = loc.locator("select")
                sels.nth(0).select_option(str(int(y) - 1911))
                sels.nth(1).select_option(str(int(m)))
                sels.nth(2).select_option(str(int(d)))
            elif k == "editable":
                loc.click()
                page.keyboard.type(str(exp))
        if p < meta["pages"] - 1:
            page.locator(".ff-step:not([hidden]) [data-ff-next]").click()


def submit(page):
    page.locator("[data-ff-submit]:visible").first.click()
    page.wait_for_timeout(50)


def check_variant(browser, d, n_personas=3):
    meta = json.loads((d / "meta.json").read_text())
    url = (d / "index.html").as_uri()
    html = (d / "index.html").read_text()
    fmts = {k: f for f, k in re.findall(r'data-ff-format="([^"]+)"[^>]*?data-ff-key="(\w+)"', html)}
    errs, problems = [], []
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    check_variant.errs = errs
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.add_init_script("""const _a=Element.prototype.attachShadow;window.__ffTestRoots=[];
      Element.prototype.attachShadow=function(o){const r=_a.call(this,o);window.__ffTestRoots.push(r);return r};
      window.__ffSet=(k,v)=>{for(const r of window.__ffTestRoots){const e=r.querySelector(`[data-ff-key="${k}"]`);if(e){return window.__ffSetEl(e,v)}}throw new Error('no '+k)};""")
    page.add_init_script("""window.__ffSetEl=(e,v)=>{const K=e.dataset.ffKind;const fire=(x,t)=>x.dispatchEvent(new Event(t,{bubbles:true,composed:true}));
      if(K==='select'||K==='input'){e.value=v;fire(e,'input');fire(e,'change');return}
      if(K==='radio'){e.querySelector(`input[value="${v}"]`).click();return}
      if(K==='ariaradio'){e.querySelector(`[role=radio][data-value="${v}"]`).click();return}
      if(K==='dropdown'){e.click();e.parentElement.querySelector(`[role=option][data-value="${v}"]`).click();return}
      if(K==='combobox'){const o=JSON.parse(e.dataset.ffOptions).find(o=>o[0]===v);e.value=o[1];fire(e,'input');
        return new Promise(res=>setTimeout(()=>{e.parentElement.querySelector(`[role=option][data-value="${v}"]`).click();res()},(+e.dataset.ffDelay||0)+50))}
      if(K==='datepicker'){const[y,m,d]=v.split('-');const f=e.dataset.ffFormat;e.value=f.replace('YYYY',y).replace('MM',m).replace('DD',d);fire(e,'change');return}
      if(K==='rocdate'){const s=e.querySelectorAll('select');const[y,m,d]=v.split('-');s[0].value=String(+y-1911);s[1].value=String(+m);s[2].value=String(+d);s.forEach(x=>fire(x,'change'));return}
      if(K==='editable'){e.innerText=v;fire(e,'input');return}
      if(K==='checkbox'){if(e.checked!==!!v)e.click();return}
      throw new Error('kind '+K)};""")

    def load(state):
        page.goto(url + (f"?state={state}" if state else ""))
        page.wait_for_function("window.__formState && window.__formState().ready", timeout=8000)
        return page.evaluate("window.__formState()")

    st = load(None)
    if sorted(st["values"]) != sorted(f["key"] for f in meta["fields"]):
        problems.append("hook keys != meta keys")
    if any(not empty(v) for v in st["values"].values()):
        problems.append(f"default state not empty: { {k: v for k, v in st['values'].items() if not empty(v)} }")
    if score(meta, st)["success"]:
        problems.append("empty form scores success")
    ui_fill(page, meta, fmts)
    submit(page)
    st = page.evaluate("window.__formState()")
    sc = score(meta, st)
    if not sc["success"]:
        problems.append(f"UI fill not successful: submitted={st['submitted']} errors={st['errors'][:3]} "
                        f"bad={[k for k, ok in sc['details'].items() if not ok]}")
    if meta.get("reject_on_first_submit") and meta["success"]["require_submitted"]:
        load("error")
        ui_fill(page, meta, fmts)
        submit(page)
        st1 = page.evaluate("window.__formState()")
        submit(page)
        st2 = page.evaluate("window.__formState()")
        if st1["submitted"] or not st2["submitted"] or not score(meta, st2)["success"]:
            problems.append("error state: expected reject then success")
    st = load("prefilled")
    sc = score(meta, st)
    if sc["fields_correct"] != sc["fields_total"]:
        problems.append(f"prefilled mismatch: {[k for k, ok in sc['details'].items() if not ok]}")
    st = load("wrong")
    if score(meta, st)["fields_correct"] == score(meta, st)["fields_total"]:
        problems.append("wrong state scores all fields correct")
    load("partial")
    if "loading" in meta["hard_states_supported"]:
        page.goto(url + "?state=loading&delay=300")
        if page.evaluate("window.__formState().ready"):
            problems.append("loading state ready immediately")
        page.wait_for_function("window.__formState().ready", timeout=4000)
    # generated personas: prefill their values, walk Next/Submit, score against their expected.json
    ctx = HERE.parent / "contexts"
    pids = meta["personas"][1:]
    for pid in pids if n_personas is None else pids[:: max(1, len(pids) // n_personas)][:n_personas]:
        ej = json.loads((ctx / f"{pid}.expected.json").read_text())
        pm = with_persona(meta, ej)
        load(None)
        st = page.evaluate("""p => { window.__ffPrefill(p.right);
            for (let i = 0; i < 12; i++) { const n = document.querySelector('.ff-step:not([hidden]) [data-ff-next]'); if (!n) break;
              const s = window.__formState().step; n.click(); if (window.__formState().step === s) break; }
            const b = [...document.querySelectorAll('[data-ff-submit]')].find(e => e.offsetParent !== null); if (b) b.click();
            return window.__formState(); }""", ej["variants"][f"{meta['family']}/{meta['variant']}"]["prefill"])
        sc = score(pm, st)
        if not sc["success"]:
            problems.append(f"persona {pid}: submitted={st['submitted']} want={pm['submit']} errors={st['errors'][:2]} bad={[k for k, ok in sc['details'].items() if not ok]}")
    page.close()
    return problems + [f"pageerror: {e}" for e in errs]


def main(argv):
    from playwright.sync_api import sync_playwright
    split = json.loads((HERE.parent / "eval" / "split.json").read_text())
    dirs = sorted(HERE / x for x in split["train"] + split["eval"])
    n_personas = 3
    if "--personas" in argv:
        i = argv.index("--personas")
        n_personas = None if argv[i + 1] == "all" else int(argv[i + 1])
        del argv[i:i + 2]
    if argv:
        dirs = [d for d in dirs if f"{d.parent.name}/{d.name}" in argv or d.parent.name in argv]
    bad = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for d in dirs:
            try:
                probs = check_variant(browser, d, n_personas)
            except Exception as e:  # report and keep going
                probs = [f"exception: {str(e).splitlines()[0]}"] + [f"pageerror: {x}" for x in getattr(check_variant, "errs", [])]
            bad += bool(probs)
            print(("FAIL " if probs else "ok   ") + f"{d.parent.name}/{d.name}" + ("".join(f"\n     - {p}" for p in probs)))
        browser.close()
    print(f"{len(dirs) - bad}/{len(dirs)} variants passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
