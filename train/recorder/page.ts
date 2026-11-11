// Recorder page bundle: the extension's own snapshot (shadow-crossing element table) plus the few
// content-script handlers the service worker uses to execute a decision. Built to page.js by record.py.
// The model still only names node numbers from this table; selectors below come from meta.json (verifier/perturbation only).
import { allRoots, containsDeep, deepElementFromPoint, errorNear, nameOf, parentOf, qsa, visible } from "../../extension/src/content/dom";
import { guard, identity, nodes, snapshot } from "../../extension/src/content/snapshot";

// The extension reaches closed shadow roots through chrome.dom; a page script cannot, so remember each root
// as it is attached (this bundle is an init script and runs before the page's own scripts).
const shadowRoots = new WeakMap<Element, ShadowRoot>();
const attachShadow = Element.prototype.attachShadow;
Element.prototype.attachShadow = function (init: ShadowRootInit) {
  const root = attachShadow.call(this, init);
  shadowRoots.set(this, root);
  return root;
};
const w = window as any;
w.chrome ??= {};
w.chrome.dom = { openOrClosedShadowRoot: (e: Element) => shadowRoots.get(e) ?? e.shadowRoot };

function el(node: number): HTMLElement {
  const e = nodes.get(node) as HTMLElement | undefined;
  if (!e?.isConnected) throw new Error("stale");
  return e;
}

const DATE_TYPES = ["date", "time", "month", "week", "datetime-local", "color", "range"];
const usable = (e: HTMLElement) => visible(e) && !e.matches(":disabled") && !e.closest('[aria-disabled="true"],[inert]');

function reveal(e: HTMLElement) {
  const r = e.getBoundingClientRect();
  if (r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth) e.scrollIntoView({ block: "center", behavior: "instant" });
  else e.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
}

function setNative(e: HTMLElement, value: string) {
  const proto = e instanceof HTMLSelectElement ? HTMLSelectElement.prototype : e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(e, value);
  e.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  e.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
}

function setValue(e: HTMLElement, value: string) {
  if (e.isContentEditable) {
    e.focus();
    getSelection()?.selectAllChildren(e);
    document.execCommand("insertText", false, value);
    return;
  }
  if (e instanceof HTMLSelectElement) {
    const o = [...e.options].find(o => (o.value === value || o.label === value) && !o.disabled);
    if (!o) throw new Error("option");
    value = o.value;
  }
  setNative(e, value);
}

/** Same as content/index.ts: two frames (50 ms cap), up to 200 ms for autocomplete options after a combobox fill. */
function settle(node?: number, fill = false): Promise<void> {
  return new Promise(resolve => {
    const field = node ? nodes.get(node) : undefined;
    const autocomplete = fill && field?.getAttribute("role") === "combobox";
    let frames = 0, stopped = false;
    const finish = () => { stopped = true; resolve(); };
    setTimeout(finish, autocomplete ? 200 : 50);
    const ready = () => {
      if (stopped) return;
      if (++frames >= 2 && (!autocomplete || qsa('[role="option"]').some(o => visible(o)))) finish();
      else requestAnimationFrame(ready);
    };
    requestAnimationFrame(ready);
  });
}

/** Verifier/perturbation lookup by a meta.json selector, across open and closed shadow roots. */
function find(selector: string): HTMLElement | null {
  for (const root of allRoots()) {
    const e = root.querySelector(selector);
    if (e) return e as HTMLElement;
  }
  return null;
}

/** The extension's snapshot; fields also carry a visible validation error (used by --teacher plan/checked re-planning). */
function annotatedSnapshot() {
  const snap = snapshot();
  for (const f of snap.fields) (f as any).error = errorNear(nodes.get(f.node)!) || undefined;
  return snap;
}

// ---- Oracle/verifier probe. Selectors come from meta.json; nothing here is shown to or produced by a model.

type Mini = { node: number; shown: boolean; pos: "above" | "in" | "below" | "hidden"; [k: string]: unknown };

function mini(e: Element, extra: Record<string, unknown> = {}): Mini {
  const shown = visible(e);
  const r = e.getBoundingClientRect(), y = r.y + r.height / 2, x = r.x + r.width / 2;
  const pos = !shown || !r.width || !r.height ? "hidden" : y < 0 ? "above" : y >= innerHeight ? "below" : x < 0 || x >= innerWidth ? "hidden" : "in";
  return { node: identity(e), shown, pos, ...extra };
}

const text = (e: Element) => ((e as HTMLElement).innerText ?? e.textContent ?? "").replace(/\s+/g, " ").trim();
const selectOf = (s: HTMLSelectElement) => mini(s, { value: s.value, label: s.selectedOptions[0]?.label ?? "", disabled: s.disabled,
  options: [...s.options].map(o => ({ value: o.value, label: o.label, disabled: o.disabled })) });

/** Why an element is not rendered: an inactive tab panel, a show-if condition, or another page/step. */
function hiddenBy(e: Element) {
  for (let n: Element | null = e; n; n = parentOf(n)) {
    const h = n as HTMLElement;
    if (!(h.hidden || getComputedStyle(h).display === "none")) continue;
    if (n.getAttribute("role") === "tabpanel" && n.id) {
      const tab = qsa(`[role=tab][aria-controls="${CSS.escape(n.id)}"]`)[0];
      if (tab) return { by: "tab", tab: mini(tab) };
    }
    return { by: h.dataset.ffShowIf ? "cond" : "page" };
  }
  return { by: "page" };
}

function describe(selector: string) {
  const e = find(selector);
  if (!e) return null;
  const i = e as any;
  const aria = e.getAttribute("aria-checked");
  const d: Record<string, any> = mini(e, {
    tag: e.tagName, type: i.type ?? "", role: e.getAttribute("role") ?? "", disabled: e.matches(":disabled"), readOnly: !!i.readOnly,
    value: e.tagName === "SELECT" ? i.value : "value" in e && e.tagName !== "BUTTON" ? String(i.value) : text(e),
    text: text(e).slice(0, 500), checked: aria !== null ? aria === "true" : ["checkbox", "radio"].includes(i.type) ? i.checked : null,
    expanded: e.getAttribute("aria-expanded") === "true", error: errorNear(e), data: { ...e.dataset },
  });
  if (!d.shown) d.hidden = hiddenBy(e);
  d.selects = (e.tagName === "SELECT" ? [e] : [...e.querySelectorAll("select")]).map(s => selectOf(s as HTMLSelectElement));
  // Native radio/checkbox group: descendants, or every input sharing the name when the selector hits one radio.
  const root = e.getRootNode() as Document | ShadowRoot;
  const group = i.type === "radio" && i.name ? [...root.querySelectorAll(`input[type=radio][name="${CSS.escape(i.name)}"]`)]
    : [...e.querySelectorAll("input[type=radio],input[type=checkbox]")];
  d.inputs = group.map(x => mini(x, { value: (x as HTMLInputElement).value, checked: (x as HTMLInputElement).checked, label: nameOf(x) }));
  d.radios = [...e.querySelectorAll("[role=radio]")].map(x => mini(x, { value: (x as HTMLElement).dataset.value ?? text(x), label: text(x),
    checked: x.getAttribute("aria-checked") === "true" }));
  if (e.getAttribute("aria-haspopup") === "listbox" || e.getAttribute("role") === "combobox") {
    const id = e.getAttribute("aria-controls");
    const list = (id && (root as Document).getElementById?.(id)) || e.parentElement?.querySelector("[role=listbox]") || null;
    // A portal listbox (rendered on <body>) is not reachable from the widget: while expanded, take the visible options.
    const options = list ? [...list.querySelectorAll("[role=option]")] : d.expanded ? qsa("[role=option]").filter(visible) : [];
    d.popup = { open: list ? visible(list) : d.expanded,
      options: options.map(o => mini(o, { value: (o as HTMLElement).dataset.value ?? text(o), label: text(o) })) };
  }
  const dp = e.closest(".ff-dp");
  if (dp) {
    const pop = dp.querySelector(".ff-cal")!;
    d.cal = { open: visible(pop), btn: mini(dp.querySelector(".ff-cal-btn")!), y: selectOf(dp.querySelector(".ff-cal-y")!), m: selectOf(dp.querySelector(".ff-cal-m")!),
      cells: [...pop.querySelectorAll("[role=gridcell]")].map(c => mini(c, { iso: c.getAttribute("aria-label") })) };
  }
  return d;
}

const api = {
  snapshot: annotatedSnapshot,
  /** One atomic read for a step: element table + oracle probe + the page's own state hook. */
  observe(fields: string[], buttons: string[]) {
    const snap = annotatedSnapshot();
    const hook = (window as any).__formState;
    return { snap, probe: fields.map(describe), state: hook ? JSON.parse(JSON.stringify(hook())) : null,
      buttons: buttons.map(sel => { const e = allRoots().flatMap(r => [...r.querySelectorAll(sel)]).find(visible); return e ? mini(e) : null; }),
      submitted: JSON.parse(JSON.stringify((window as any).__submitted ?? null)) };
  },
  guard: (node: number) => guard(nodes.get(node)) ?? "",
  point(node: number) {
    const e = el(node);
    if (!usable(e)) return null;
    reveal(e);
    const r = e.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
    if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
    if (!containsDeep(e, deepElementFromPoint(x, y))) return null;
    return { x, y };
  },
  focusText(node: number) {
    const e = el(node);
    if (!usable(e)) throw new Error("stale");
    reveal(e);
    e.focus();
    if (e instanceof HTMLInputElement || e instanceof HTMLTextAreaElement) e.select();
    else getSelection()?.selectAllChildren(e);
    // Date-like inputs ignore inserted text; the caller sets their value instead (as Bulk Fill does).
    return e instanceof HTMLInputElement && DATE_TYPES.includes(e.type) ? "date" : "text";
  },
  setValue(node: number, value: string) {
    const e = el(node);
    if (!usable(e)) throw new Error("stale");
    setValue(e, value);
    return true;
  },
  scroll: (delta: number) => scrollBy(0, delta),
  settle,
  submitted: () => JSON.parse(JSON.stringify((window as any).__submitted ?? null)),
  /** Perturbation: put a value into a field as if the user typed it earlier. */
  prefill(selector: string, value: string | boolean) {
    const e = find(selector);
    if (!e) return false;
    const checkbox = (e as HTMLInputElement).type === "checkbox" || e.getAttribute("role") === "checkbox" || e.getAttribute("role") === "radio" || (e as HTMLInputElement).type === "radio";
    if (checkbox) {
      const on = e.getAttribute("aria-checked") !== null ? e.getAttribute("aria-checked") === "true" : (e as HTMLInputElement).checked;
      if (on !== Boolean(value)) e.click();
    } else setValue(e, String(value));
    return true;
  },
  /** Perturbation: a visible validation error next to the field, removed once the user edits it. */
  markError(selector: string, message: string) {
    const e = find(selector);
    if (!e) return false;
    e.setAttribute("aria-invalid", "true");
    const m = document.createElement("div");
    m.setAttribute("role", "alert");
    m.className = "ff-error";
    m.style.cssText = "color:#c00;font-size:12px;margin-top:4px";
    m.textContent = message;
    e.insertAdjacentElement("afterend", m);
    e.addEventListener("input", () => { e.removeAttribute("aria-invalid"); m.remove(); }, { once: true });
    return true;
  },
};

(window as any).__ff = api;
