// DOM helpers shared by the detector and the snapshot. Everything crosses open and closed shadow roots.

export const UI_TAG = "formform-fab";

export function shadowOf(e: Element): ShadowRoot | null {
  if (e.tagName.toLowerCase() === UI_TAG) return null;
  // chrome.dom reaches closed roots from content scripts; tests fall back to open roots.
  return (globalThis.chrome?.dom?.openOrClosedShadowRoot?.(e as HTMLElement) as ShadowRoot | undefined) ?? e.shadowRoot;
}

/** The document plus every shadow root inside it. ponytail: only custom elements are probed; plain divs with attachShadow are missed. */
export function allRoots(doc: Document = document): (Document | ShadowRoot)[] {
  const roots: (Document | ShadowRoot)[] = [doc];
  for (let i = 0; i < roots.length; i++) {
    for (const e of roots[i].querySelectorAll("*")) {
      if (!e.tagName.includes("-")) continue;
      const root = shadowOf(e);
      if (root) roots.push(root);
    }
  }
  return roots;
}

export function qsa(selector: string, roots = allRoots()): Element[] {
  return roots.flatMap(r => [...r.querySelectorAll(selector)]);
}

export function parentOf(e: Element): Element | null {
  return e.parentElement ?? ((e.getRootNode() as ShadowRoot).host ?? null);
}

export function closestDeep(e: Element, selector: string): Element | null {
  for (let n: Element | null = e; n; n = parentOf(n)) if (n.matches(selector)) return n;
  return null;
}

export function visible(e: Element): boolean {
  if (closestDeep(e, '[aria-hidden="true"],[inert]')) return false;
  const check = (e as HTMLElement).checkVisibility;
  if (!check) return true; // jsdom
  const type = (e as HTMLInputElement).type;
  // Styled radios and checkboxes hide the native input; their label is what the user sees.
  if ((type === "radio" || type === "checkbox") && !check.call(e, { checkOpacity: true, checkVisibilityCSS: true })) {
    const label = (e as HTMLInputElement).labels?.[0] ?? e.parentElement;
    return !!label?.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  }
  return check.call(e, { checkOpacity: true, checkVisibilityCSS: true });
}

function byId(e: Element, id: string): Element | null {
  return (e.getRootNode() as Document | ShadowRoot).getElementById?.(id) ?? document.getElementById(id);
}

/** Accessible name, ported from jev-ultrafast's snapshot.js and made shadow-aware. */
export function nameOf(e: Element | null, seen = new Set<Element>()): string {
  if (!e || seen.has(e)) return "";
  seen.add(e);
  const referenced = (e.getAttribute("aria-labelledby") || "")
    .split(/\s+/).filter(Boolean).map(id => nameOf(byId(e, id), seen)).filter(Boolean).join(" ");
  const input = e as HTMLInputElement;
  return clean(
    referenced ||
      e.getAttribute("aria-label") ||
      [...(input.labels || [])].map(l => nameOf(l, seen)).filter(Boolean).join(" ") ||
      (["button", "submit", "reset"].includes(input.type) ? input.value : "") ||
      e.getAttribute("alt") ||
      (["INPUT", "SELECT", "TEXTAREA"].includes(e.tagName) ? "" : textOf(e, seen)) ||
      e.getAttribute("title") ||
      e.getAttribute("placeholder") ||
      "",
  );
}

function textOf(e: Element, seen: Set<Element>): string {
  const nodes = shadowOf(e)?.childNodes.length ? shadowOf(e)!.childNodes : e.childNodes;
  return [...nodes]
    .map(n => n.nodeType === 3 ? n.textContent : n.nodeType === 1 && (n as Element).getAttribute("aria-hidden") !== "true" &&
      !["SCRIPT", "STYLE"].includes((n as Element).tagName) ? nameOf(n as Element, seen) : "")
    .join(" ");
}

export const clean = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, 200);

/** Nearby text for fields without a real label: the first ancestor with text of its own. */
export function hintOf(e: Element): string {
  // Climb while the text stays short: a table row or field wrapper carries the real label of split boxes.
  let n: Element | null = e, best = "";
  for (let i = 0; i < 4 && (n = parentOf(n)); i++) {
    const text = clean((n as HTMLElement).innerText ?? n.textContent ?? "");
    if (text.length > 120) break;
    if (text) best = text;
  }
  return best;
}

/** A visible validation message right next to the field (role=alert, aria-invalid, or an error-classed node). */
export function errorNear(e: Element): string {
  if (e.getAttribute("aria-invalid") === "true") return "invalid";
  let n: Element | null = e;
  for (let i = 0; i < 2 && (n = parentOf(n)); i++) {
    for (const m of n.querySelectorAll('[role=alert],[class*="err"],[class*="invalid"]')) {
      const text = clean((m as HTMLElement).innerText ?? "");
      if (text && visible(m)) return text;
    }
  }
  return "";
}

export function deepElementFromPoint(x: number, y: number): Element | null {
  let hit = document.elementFromPoint(x, y);
  for (let root = hit && shadowOf(hit); root; root = hit && shadowOf(hit)) {
    const inner = root.elementFromPoint(x, y);
    if (!inner || inner === hit) break;
    hit = inner;
  }
  return hit;
}

export function containsDeep(outer: Element, inner: Element | null): boolean {
  for (let n = inner; n; n = parentOf(n)) if (n === outer) return true;
  return false;
}
