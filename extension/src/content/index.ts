// Content script: detect forms, show the button, and execute the service worker's single-node requests.
import type { ContentRequest } from "../shared/types";
import { getSettings } from "../shared/storage";
import { FIELD, HIDE, SHOW, SUBMIT, detect, regionOf } from "./detector";
import { allRoots, containsDeep, deepElementFromPoint, errorNear, nameOf, qsa, visible } from "./dom";
import { Fab } from "./fab";
import { fields, guard, identity, nodes, snapshot } from "./snapshot";

const top = window === window.top;
const BUILDER_FRAME = /docs\.google\.com\/forms|forms\.(office|microsoft)\.com|typeform\.com|hsforms|jotform|tally\.so/i;
let fab: Fab | null = null;
let shown = false;
let childFrameWantsButton = false;

async function fill() {
  const s = await getSettings();
  if (!s.consented) return fab?.askConsent();
  chrome.runtime.sendMessage({ type: "fill" });
}

async function scan() {
  watchShadowRoots();
  const s = await getSettings();
  if (s.disabledSites.includes(location.hostname)) return fab?.show(false);
  const d = detect();
  if (!top) {
    const big = innerWidth >= 200 && innerHeight >= 150;
    if (big && d.score >= SHOW) chrome.runtime.sendMessage({ type: "detected", score: d.score }).catch(() => {});
    return;
  }
  const builder = qsa("iframe").some(f => BUILDER_FRAME.test((f as HTMLIFrameElement).src) && visible(f));
  shown = childFrameWantsButton || builder || (shown ? d.score >= HIDE : d.score >= SHOW);
  if (shown) (fab ??= new Fab(fill, () => void scan())).show(true);
  else fab?.show(false);
}

// Rescan on relevant DOM changes: 400 ms trailing debounce, at most 2 s apart.
let timer = 0, first = 0;
function schedule() {
  const now = Date.now();
  first ||= now;
  clearTimeout(timer);
  timer = window.setTimeout(() => {
    first = 0;
    void scan();
  }, Math.max(0, Math.min(400, first + 2000 - now)));
}
const observer = new MutationObserver(records => {
  for (const r of records) for (const n of r.addedNodes) {
    if (n.nodeType === 1 && ((n as Element).matches(FIELD + ",iframe") || (n as Element).querySelector(FIELD + ",iframe") ||
        (n as Element).tagName.includes("-"))) return schedule();
  }
});
observer.observe(document.documentElement, { childList: true, subtree: true });
// Shadow roots do not report to the document observer; watch each one the scanner finds (closed ones too).
const watched = new WeakSet<Node>();
function watchShadowRoots() {
  for (const root of allRoots()) if (root !== document && !watched.has(root)) {
    watched.add(root);
    observer.observe(root, { childList: true, subtree: true });
  }
}
(window as any).navigation?.addEventListener("navigate", schedule);
addEventListener("hashchange", schedule);
addEventListener("focusin", e => (e.target as Element)?.matches?.(FIELD) && !shown && schedule(), { once: true });
requestIdleCallback(() => void scan(), { timeout: 1000 });
chrome.storage.onChanged.addListener(c => {
  if (c.settings) {
    void fab?.localize();
    void scan();
  }
});

// ---- Execution helpers. Every request names a node from the last snapshot; nothing else is addressable.

function el(node: number): HTMLElement {
  const e = nodes.get(node) as HTMLElement | undefined;
  if (!e?.isConnected) throw new Error("stale");
  return e;
}

function usable(e: HTMLElement) {
  return visible(e) && !e.matches(":disabled") && !e.closest('[aria-disabled="true"],[inert]');
}

function reveal(e: HTMLElement) {
  const r = e.getBoundingClientRect();
  if (r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth) e.scrollIntoView({ block: "center", behavior: "instant" });
  // Also scroll clipped options inside their own scroll container (listboxes); a no-op when already visible.
  else e.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
}

function setNative(e: HTMLElement, value: string) {
  const proto = e instanceof HTMLSelectElement ? HTMLSelectElement.prototype : e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  // The prototype setter bypasses React's value tracker so frameworks see the change.
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(e, value);
  e.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
  e.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
}

const highlighted = new Set<HTMLElement>();
function highlight(es: HTMLElement[]) {
  for (const e of highlighted) e.style.removeProperty("outline");
  highlighted.clear();
  for (const e of es) {
    e.style.setProperty("outline", "2px solid #e52020", "important");
    highlighted.add(e);
    e.addEventListener("input", () => e.style.removeProperty("outline"), { once: true });
    e.addEventListener("click", () => e.style.removeProperty("outline"), { once: true });
  }
}

function settle(node?: number, fillCombobox = false): Promise<void> {
  // jev's post-input wait: two frames (50 ms cap), or up to 200 ms for autocomplete options to appear.
  return new Promise(resolve => {
    const field = node ? nodes.get(node) : undefined;
    const autocomplete = fillCombobox && field?.getAttribute("role") === "combobox";
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

async function handle(m: ContentRequest): Promise<unknown> {
  switch (m.type) {
    case "snapshot":
      return snapshot();
    case "detect": {
      const d = detect();
      return { score: d.score, signature: d.signature, url: location.href,
        alerts: qsa('[role=alert],[aria-invalid="true"]').filter(visible).map(e => nameOf(e)).filter(Boolean).slice(0, 5) };
    }
    case "guard":
      return guard(nodes.get(m.node));
    case "focusText": {
      const e = el(m.node);
      if (!usable(e)) throw new Error("stale");
      reveal(e);
      e.focus();
      if (e instanceof HTMLInputElement || e instanceof HTMLTextAreaElement) e.select();
      else getSelection()?.selectAllChildren(e);
      return true;
    }
    case "point": {
      const e = el(m.node);
      if (!usable(e)) return null;
      reveal(e);
      const r = e.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
      if (!r.width || !r.height || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
      // Reject covered targets: the element under the center point must be the target or inside it.
      if (!containsDeep(e, deepElementFromPoint(x, y))) return null;
      return { x, y };
    }
    case "setValue": {
      const e = el(m.node);
      if (!usable(e)) throw new Error("stale");
      if (e.isContentEditable) {
        e.focus();
        getSelection()?.selectAllChildren(e);
        document.execCommand("insertText", false, m.value); // fires beforeinput/input like typing
        return true;
      }
      if (e instanceof HTMLSelectElement && ![...e.options].some(o => o.value === m.value && !o.disabled)) throw new Error("option");
      setNative(e, m.value);
      return true;
    }
    case "domClick": {
      // Full pointer sequence: many widgets open or commit on pointerdown/mousedown, not on click.
      const e = el(m.node);
      reveal(e);
      const r = e.getBoundingClientRect();
      const at = { bubbles: true, cancelable: true, composed: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2, button: 0 };
      e.dispatchEvent(new PointerEvent("pointerdown", { ...at, pointerId: 1, isPrimary: true }));
      e.dispatchEvent(new MouseEvent("mousedown", at));
      if (e.matches("input,textarea,select,button,[tabindex],[contenteditable=true]")) e.focus();
      e.dispatchEvent(new PointerEvent("pointerup", { ...at, pointerId: 1, isPrimary: true }));
      e.dispatchEvent(new MouseEvent("mouseup", at));
      e.click();
      return true;
    }
    case "blur":
      (nodes.get(m.node) as HTMLElement | undefined)?.blur?.();
      return true;
    case "scroll":
      scrollBy(0, m.delta);
      return true;
    case "settle":
      await settle(m.node, m.fill);
      return true;
    case "verify": {
      const region = detect().region;
      const missing = fields(region).filter(f => (f.required && !(f.widget === "check" ? f.value === "on" : f.filled)) ||
        (f.filled && errorNear(nodes.get(f.node)!)));
      highlight(missing.map(f => {
        const e = nodes.get(f.node) as HTMLElement;
        return f.widget === "choice" && e.getAttribute("role") !== "radiogroup" ? (e.closest("fieldset") as HTMLElement) ?? e.parentElement! : e;
      }));
      return missing.map(f => (f.hint && f.hint.length <= 40 ? f.hint : f.label || f.hint));
    }
    case "submitButton": {
      const region = detect().region;
      const scope = region ? [region, ...qsa("button,[type=submit],[role=button]").filter(b => regionOf(b) === region)] : [document.body];
      const buttons = [...new Set(scope.flatMap(r => [...r.querySelectorAll("button,input[type=submit],[role=button]")]))]
        .filter(b => usable(b as HTMLElement) && !/back|reset|cancel|戻る|リセット|返回|取消|上一步/i.test(nameOf(b)));
      const pick = buttons.find(b => (b as HTMLButtonElement).type === "submit" && SUBMIT.test(nameOf(b))) ??
        buttons.find(b => SUBMIT.test(nameOf(b))) ?? buttons.find(b => (b as HTMLButtonElement).type === "submit");
      if (!pick) return null;
      return { node: identity(pick), label: nameOf(pick) };
    }
    case "countdown":
      return fab ? fab.countdown(m.ms) : true;
    case "fab":
      if (top) (fab ??= new Fab(fill, () => void scan())).set(m.state, m.text, m.progress);
      return true;
    case "showFab":
      childFrameWantsButton = m.show;
      void scan();
      return true;
  }
}

chrome.runtime.onMessage.addListener((m: ContentRequest, _sender, reply) => {
  handle(m).then(
    value => reply({ ok: true, value }),
    error => reply({ ok: false, error: String(error?.message ?? error) }),
  );
  return true;
});
