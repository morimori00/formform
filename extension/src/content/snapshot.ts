// Port of jev-ultrafast/jev_ultrafast/snapshot.js, run in the content script so it can cross closed shadow roots.
// Model output can only name a node number from this table; it never becomes a selector or code.
import type { Action, Field, Snapshot, Widget } from "../shared/types";
import { SENSITIVE, detect, labelOf } from "./detector";
import { allRoots, clean, closestDeep, hintOf, nameOf, parentOf, qsa, visible } from "./dom";

const ids = new WeakMap<Element, number>();
export const nodes = new Map<number, Element>();
let next = 1;

export function identity(e: Element): number {
  if (!ids.has(e)) ids.set(e, next++);
  const id = ids.get(e)!;
  nodes.set(id, e);
  return id;
}

const ROLES = ["button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "menuitemradio",
  "option", "gridcell", "combobox", "textbox", "searchbox", "spinbutton"];
const SELECTOR = 'a[href],button,input,textarea,select,summary,[contenteditable="true"],' +
  ROLES.map(r => `[role="${r}"]`).join(",");
const DATE_TYPES = ["date", "time", "month", "week", "datetime-local", "color", "range"];

const safe = (e: Element) => {
  const i = e as HTMLInputElement;
  if (["password", "file", "hidden"].includes(i.type)) return false;
  return !SENSITIVE.test(i.getAttribute?.("autocomplete") ?? "") && !SENSITIVE.test(i.name ?? "");
};

function role(e: Element): string | null {
  const explicit = e.getAttribute("role");
  if (explicit && ROLES.includes(explicit)) return explicit;
  const i = e as HTMLInputElement;
  if (e.tagName === "BUTTON" || e.tagName === "SUMMARY") return "button";
  if (e.tagName === "A") return "link";
  if (e.tagName === "SELECT") return "combobox";
  if (e.tagName === "TEXTAREA" || (e as HTMLElement).isContentEditable) return "textbox";
  if (e.tagName === "INPUT") {
    if (["checkbox", "radio"].includes(i.type)) return i.type;
    if (["button", "submit", "reset", "image"].includes(i.type)) return "button";
    if (i.type === "search") return "searchbox";
    if (i.type === "number") return "spinbutton";
    if (["text", "email", "url", "tel", "", ...DATE_TYPES].includes(i.type)) return "textbox";
  }
  return null;
}

export function guard(e: Element | undefined): string | null {
  if (!e?.isConnected || !visible(e)) return null;
  const i = e as HTMLInputElement & HTMLSelectElement;
  return JSON.stringify([role(e), nameOf(e), i.value ?? (e as HTMLElement).innerText ?? null, i.checked ?? null,
    i.selectedIndex ?? null, e.matches(":disabled"), e.getAttribute("aria-expanded"),
    e.getAttribute("aria-checked"), e.getAttribute("aria-selected")]);
}

function inViewport(e: Element) {
  const r = e.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  return r.width > 0 && r.height > 0 && x >= 0 && y >= 0 && x < innerWidth && y < innerHeight;
}

/** jev's action table: visible, enabled controls in the viewport. */
function actions(): Action[] {
  const out: Action[] = [];
  for (const e of qsa(SELECTOR)) {
    if (!safe(e) || !visible(e) || e.matches(":disabled") || closestDeep(e, '[aria-disabled="true"]')) continue;
    const r = role(e);
    if (!r || !inViewport(e)) continue;
    if (r === "gridcell" && e.querySelector('button,[role="button"]')) continue;
    const base: Action = { id: "", node: identity(e), kind: "click", role: r, label: nameOf(e) || r };
    for (const key of ["checked", "selected", "expanded"] as const) {
      const v = e.getAttribute("aria-" + key);
      if (v !== null) base[key] = v;
    }
    const i = e as HTMLInputElement;
    if (["checkbox", "radio"].includes(i.type)) base.checked = String(i.checked);
    if (e.tagName === "SELECT") {
      const s = e as HTMLSelectElement;
      for (const o of s.options) {
        if (o.selected || o.disabled || o.closest("optgroup[disabled]")) continue;
        out.push({ ...base, kind: "select", value: o.value, current_value: [...s.selectedOptions].map(o => o.label).join(", "),
          label: base.label + " → " + o.label });
      }
      continue;
    }
    const editable = !i.readOnly && e.getAttribute("aria-readonly") !== "true" &&
      (["textbox", "searchbox", "spinbutton"].includes(r) || (r === "combobox" && ["INPUT", "TEXTAREA"].includes(e.tagName)));
    const value = "value" in e ? String(i.value) : (e as HTMLElement).isContentEditable || r === "combobox" ? (e as HTMLElement).innerText.trim() : "";
    out.push({ ...base, kind: editable ? "fill" : "click", value });
    if (editable) out.push({ ...base, kind: "click", value, label: "Open " + base.label });
  }
  out.splice(250);
  out.forEach((a, i) => (a.id = "e" + (i + 1)));
  const height = document.documentElement.scrollHeight;
  if (scrollY + innerHeight < height - 2) out.push({ id: "scroll_down", node: 0, kind: "scroll", label: "Scroll down", delta: 560 });
  if (scrollY > 0) out.push({ id: "scroll_up", node: 0, kind: "scroll", label: "Scroll up", delta: -560 });
  out.push({ id: "wait", node: 0, kind: "wait", label: "Wait for the page to update" });
  return out;
}

const REQ = /\*|必須|必填|required/i;

function required(e: Element, label: string) {
  return (e as HTMLInputElement).required || e.getAttribute("aria-required") === "true" || REQ.test(label);
}

/** Fields of the detected form for Bulk Fill. Groups radios; marks values the user already entered. */
export function fields(region: Element | null): Field[] {
  const out: Field[] = [];
  const radios = new Map<string, Field>();
  const roots = allRoots();
  const inRegion = (e: Element) => !region || region.contains(e) || containsAcrossShadow(region, e);
  const all = qsa("input,select,textarea,[contenteditable=true],[role=textbox],[role=combobox],[role=radiogroup],[role=checkbox],[role=switch],[aria-haspopup=listbox]", roots);
  for (const e of all) {
    if (!safe(e) || !inRegion(e) || !visible(e) || e.matches(":disabled") || (e as HTMLInputElement).readOnly) continue;
    const i = e as HTMLInputElement;
    const r = e.getAttribute("role");
    if (["submit", "button", "reset", "image", "search"].includes(i.type) && e.getAttribute("aria-haspopup") !== "listbox") continue;
    if (closestDeep(e, "[role=radiogroup]") && r !== "radiogroup") continue; // counted via the group
    if (offscreen(e)) continue; // honeypots: parked off-page or 1px wide
    const label = nameOf(e) || labelOf(e);
    const base = { node: identity(e), label, hint: hintOf(e), type: i.type || e.tagName.toLowerCase(),
      autocomplete: e.getAttribute("autocomplete") || undefined, name: i.name || undefined, native: !r };
    if (i.type === "radio") {
      const key = (i.form ? "f" : "") + i.name;
      const group = closestDeep(e, "fieldset");
      let f = i.name ? radios.get(key) : undefined;
      if (!f) {
        f = { ...base, widget: "choice", label: clean(group?.querySelector("legend")?.textContent ?? "") || hintOf(group ?? parentOf(e)!),
          hint: hintOf(group ?? e), required: REQ.test(hintOf(group ?? parentOf(e)!)), value: "", filled: false, options: [] };
        if (i.name) radios.set(key, f);
        out.push(f);
      }
      f.options!.push({ id: String(identity(e)), label });
      f.required ||= i.required;
      if (i.checked) Object.assign(f, { value: label, filled: true });
      continue;
    }
    if (r === "radiogroup") {
      const options = [...e.querySelectorAll("[role=radio]")];
      const checked = options.find(o => o.getAttribute("aria-checked") === "true");
      out.push({ ...base, widget: "choice", required: required(e, label + " " + base.hint), value: checked ? nameOf(checked) : "", filled: !!checked,
        options: options.map(o => ({ id: String(identity(o)), label: nameOf(o) })) });
      continue;
    }
    if (i.type === "checkbox" || r === "checkbox" || r === "switch") {
      const on = r ? e.getAttribute("aria-checked") === "true" : i.checked;
      out.push({ ...base, widget: "check", required: required(e, label + " " + base.hint), value: on ? "on" : "off", filled: false,
        options: [{ id: "on", label: "checked" }, { id: "off", label: "unchecked" }] });
      continue;
    }
    if (e.tagName === "SELECT") {
      const s = e as HTMLSelectElement;
      const opts = [...s.options].filter(o => !o.disabled);
      const placeholder = s.selectedIndex <= 0 && (!s.value || /^(-+|選択|請選擇|select|choose)/i.test(s.options[s.selectedIndex]?.label ?? ""));
      out.push({ ...base, widget: "select", required: required(e, label + " " + base.hint), value: placeholder ? "" : s.options[s.selectedIndex]?.label ?? "",
        filled: !placeholder, options: opts.map(o => ({ id: o.value, label: o.label })) });
      continue;
    }
    const custom = r === "combobox" || e.getAttribute("aria-haspopup") === "listbox";
    const value = e.tagName === "INPUT" || e.tagName === "TEXTAREA" ? String(i.value) : (e as HTMLElement).innerText.trim();
    const widget: Widget = custom ? "custom" : DATE_TYPES.includes(i.type) ? "date" : "text";
    const placeholder = custom && e.tagName === "BUTTON" && /^(select|choose|pick|選択|選ぶ|請選擇|选择)/i.test(value);
    out.push({ ...base, widget, required: required(e, label + " " + base.hint), value: placeholder ? "" : value, filled: !!value.trim() && !placeholder });
  }
  // Split fields (postal code 3+4, phone 3 parts) share one label; tell the model which part each box is.
  const byParent = new Map<Element, Field[]>();
  for (const f of out) {
    if (f.widget !== "text") continue;
    const p = parentOf(nodes.get(f.node)!)!;
    byParent.set(p, [...(byParent.get(p) ?? []), f]);
  }
  for (const group of byParent.values()) {
    if (group.length > 1 && new Set(group.map(f => f.label)).size < group.length) {
      group.forEach((f, i) => (f.part = `${i + 1}/${group.length}`));
    }
  }
  return out;
}

function offscreen(e: Element) {
  const r = (e.closest("label") ?? e).getBoundingClientRect();
  if (e.matches("input[type=radio],input[type=checkbox]")) return r.right + scrollX <= 0 || r.bottom + scrollY <= 0;
  return r.width <= 2 || r.height <= 2 || r.right + scrollX <= 0 || r.bottom + scrollY <= 0;
}

function containsAcrossShadow(outer: Element, e: Element) {
  for (let n: Element | null = e; n; n = parentOf(n)) if (n === outer) return true;
  return false;
}

function visibleText(): string {
  const words: string[] = [];
  let length = 0;
  for (const root of allRoots()) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let node: Node | null;
    while ((node = walker.nextNode()) && length < 6000) {
      const value = node.textContent!.trim();
      const parent = node.parentElement;
      if (!value || !parent || parent.closest("script,style,noscript,template") || !visible(parent)) continue;
      range.selectNodeContents(node);
      const r = range.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth) {
        words.push(value);
        length += value.length;
      }
    }
  }
  return words.join("\n").slice(0, 6000);
}

function formText(region: Element | null): string {
  if (!region) return "";
  const parts = [(region as HTMLElement).innerText ?? ""];
  for (const root of allRoots()) if (root !== document && containsAcrossShadow(region, (root as ShadowRoot).host)) {
    parts.push(((root as ShadowRoot).host as HTMLElement).innerText ?? "", [...root.children].map(c => (c as HTMLElement).innerText ?? "").join("\n"));
  }
  return parts.join("\n").replace(/\n{3,}/g, "\n\n").slice(0, 6000);
}

export function snapshot(): Snapshot {
  for (const [id, e] of nodes) if (!e.isConnected) nodes.delete(id);
  const region = detect().region;
  const acts = actions();
  const flds = fields(region);
  const guards: Record<string, string> = {};
  for (const n of new Set([...acts.map(a => a.node), ...flds.map(f => f.node)])) if (n) guards[n] = guard(nodes.get(n)) ?? "";
  const text = visibleText();
  const fingerprint = JSON.stringify([location.href, scrollY, innerHeight, text.length, acts.map(({ id, ...a }) => a), flds.map(f => [f.node, f.value])]);
  return { url: location.href, title: document.title, text, formText: formText(region), top: window === window.top,
    actions: acts, fields: flds, guards, fingerprint: String(hash(fingerprint)) };
}

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h;
}
