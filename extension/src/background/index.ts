// Service worker: owns credentials, model calls, and trusted input through chrome.debugger.
import { translator } from "../shared/i18n";
import { addRun, getContext, getSettings, type Env, type RunLog } from "../shared/storage";
import type { Action, BackgroundRequest, ContentRequest, FabState, Snapshot } from "../shared/types";
import { bulkFill, choose, fieldContext, fieldText, lastBulkRaw, postJson, type HistoryItem } from "./model";
import { fillGoal } from "./prompts";

const SHOW = 10;
const MAX_STEPS = 20;
const MAX_PAGES = 10;
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

class Stale extends Error {}

// ---- chrome.debugger: attached only while a fill runs.
const attached = new Set<number>();
chrome.debugger.onDetach.addListener(s => s.tabId && attached.delete(s.tabId));

async function attach(tabId: number) {
  if (attached.has(tabId)) return;
  await chrome.debugger.attach({ tabId }, "1.3");
  attached.add(tabId);
  // Keep rendering when the window loses focus (jev-ultrafast does the same).
  await chrome.debugger.sendCommand({ tabId }, "Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});
}

async function detach(tabId: number) {
  if (attached.delete(tabId)) await chrome.debugger.detach({ tabId }).catch(() => {});
}

async function cdp(tabId: number, method: string, params: object) {
  if (!attached.has(tabId)) await attach(tabId);
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

// ---- Content script requests
async function ask<T = any>(tabId: number, frameId: number, m: ContentRequest): Promise<T> {
  const r = await chrome.tabs.sendMessage(tabId, m, { frameId });
  if (!r) throw new Error("No response from page");
  if (!r.ok) throw r.error === "stale" ? new Stale("Page changed") : new Error(r.error);
  return r.value;
}

class Run {
  calls = 0;
  debug = "";
  /** False when chrome.debugger cannot attach (e.g. another extension's iframe is in the page); input is then synthetic. */
  trusted = true;
  fills: RunLog["fills"] = [];
  started = Date.now();
  t = translator("en");
  constructor(readonly tabId: number, public frameId: number, readonly env: Env, readonly context: string) {}

  ask<T = any>(m: ContentRequest) {
    return ask<T>(this.tabId, this.frameId, m);
  }

  fab(state: FabState, text = "", progress = "") {
    return ask(this.tabId, 0, { type: "fab", state, text, progress }).catch(() => {});
  }

  /** Fresh check immediately before a mutation. A stale node is re-decided, never retried blindly. */
  async fresh(snap: Snapshot, node: number) {
    const now = await this.ask({ type: "guard", node });
    if (now !== snap.guards[node]) throw new Stale("Target changed since the snapshot");
  }

  async click(node: number) {
    const p = await this.ask<{ x: number; y: number } | null>({ type: "point", node });
    if (!p) throw new Stale("Target moved or is covered");
    if (this.frameId !== 0 || !this.trusted) return void (await this.ask({ type: "domClick", node }));
    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
      await cdp(this.tabId, "Input.dispatchMouseEvent", { type, x: p.x, y: p.y, button: "left", clickCount: 1 });
    }
  }

  async type(node: number, text: string) {
    await this.ask({ type: "focusText", node });
    if (this.frameId !== 0 || !this.trusted) return void (await this.ask({ type: "setValue", node, value: text }));
    await cdp(this.tabId, "Input.insertText", { text });
  }

  async execute(action: Action, text: string | null) {
    if (action.kind === "wait") return sleep(100);
    if (action.kind === "scroll") return void (await this.ask({ type: "scroll", delta: action.delta! }));
    if (action.kind === "select") return void (await this.ask({ type: "setValue", node: action.node, value: action.value! }));
    if (action.kind === "fill") return this.type(action.node, text!);
    return this.click(action.node);
  }

  /** Phase 1: one text-model request for every empty field, then type them in order. */
  async bulk(snap: Snapshot) {
    const targets = snap.fields.filter(f => !f.filled);
    if (!targets.length) return [];
    await this.fab("filling", "", `0/${targets.length}`);
    let fills = await bulkFill(this.context, snap, targets, this.env);
    this.calls++;
    if (!fills.length) {
      // An empty answer is usually provider variance. Model calls never touch the page, so one retry is safe.
      fills = await bulkFill(this.context, snap, targets, this.env);
      this.calls++;
    }
    this.debug = (this.trusted ? "" : "synthetic input · ") + lastBulkRaw;
    const planned: { label: string; value: string }[] = [];
    let done = 0;
    for (const { field: f, value, option } of fills) {
      const label = f.label || f.hint;
      const shown = option ? f.options!.find(o => o.id === option)!.label : value!;
      try {
        if (f.widget === "custom") {
          planned.push({ label, value: value! });
          continue;
        }
        await this.fresh(snap, f.node);
        if (f.widget === "text") {
          await this.type(f.node, value!);
          await this.ask({ type: "blur", node: f.node });
        } else if (f.widget === "date") {
          await this.ask({ type: "setValue", node: f.node, value: value! });
        } else if (f.widget === "select") {
          await this.ask({ type: "setValue", node: f.node, value: option! });
        } else if (f.widget === "choice") {
          const node = Number(option);
          if (f.native) await this.ask({ type: "domClick", node });
          else await this.click(node);
        } else if (f.widget === "check") {
          if (option === f.value) continue;
          if (f.native) await this.ask({ type: "domClick", node: f.node });
          else await this.click(f.node);
        }
        this.fills.push({ label, value: shown, via: "bulk" });
        await this.fab("filling", "", `${++done}/${targets.length}`);
        await this.ask({ type: "settle", node: f.node });
      } catch (e) {
        if (!(e instanceof Stale)) throw e;
        planned.push({ label, value: shown });
      }
    }
    return planned;
  }

  /** Phase 2: jev-ultrafast's loop for widgets that need several interactions. */
  async jev(goal: string, planned: { label: string; value: string }[] = []) {
    const norm = (x: string) => x.replace(/[\s*＊必須必填]|required/gi, "");
    const plannedFor = (label: string) => planned.find(p => norm(p.label) && (norm(label).includes(norm(p.label)) || norm(p.label).includes(norm(label))))?.value;
    const history: HistoryItem[] = [];
    let pending = null as { key: string; text: string } | null;
    let previous = "";
    for (let step = 0; step < MAX_STEPS; step++) {
      const snap = await this.ask<Snapshot>({ type: "snapshot" });
      if (history.length) history[history.length - 1].page_changed = snap.fingerprint !== previous;
      const recent = history.slice(-3);
      if (recent.length === 3 && recent.every(h => h.page_changed === false && h.kind !== "wait")) return "blocked";
      previous = snap.fingerprint;
      const d = await choose(snap, goal, history, this.env);
      this.calls++;
      if (d.choice === "DONE") return "done";
      if (d.choice === "BLOCKED") return "blocked";
      const action = snap.actions.find(a => a.id === d.choice);
      if (!action) return "blocked";
      let text: string | null = null;
      if (action.kind === "fill") {
        const context = fieldContext(goal, action, snap, history);
        const key = JSON.stringify(context);
        // Reuse a generated value only while the helper input is identical (stale retry).
        if (pending?.key === key) text = pending.text;
        else if (plannedFor(action.label)) text = plannedFor(action.label)!; // Bulk already generated this value
        else {
          text = await fieldText(context, this.env);
          this.calls++;
          pending = { key, text };
        }
      }
      try {
        if (action.node) await this.fresh(snap, action.node);
        await this.execute(action, text);
      } catch (e) {
        if (e instanceof Stale) continue;
        throw e;
      }
      pending = null;
      // Record execution before observing its result.
      history.push({ action: action.label, kind: action.kind, text, page_changed: null });
      if (text) this.fills.push({ label: action.label, value: text, via: "jev" });
      else if (action.kind !== "wait" && action.kind !== "scroll") this.fills.push({ label: action.label, value: action.kind, via: "jev" });
      await this.ask({ type: "settle", node: action.node || undefined, fill: action.kind === "fill" });
    }
    return "blocked";
  }

  async page(): Promise<string[]> {
    // A second round catches fields that appear or gain options after the first fills (dependent selects).
    const attempted = new Set<string>();
    const planned: { label: string; value: string }[] = [];
    for (let round = 0; round < 2; round++) {
      const snap = await this.ask<Snapshot>({ type: "snapshot" });
      const key = (f: Snapshot["fields"][number]) => `${f.node}:${f.options?.length ?? 0}`;
      snap.fields = snap.fields.filter(f => !attempted.has(key(f)));
      if (!snap.fields.some(f => !f.filled)) break;
      snap.fields.forEach(f => attempted.add(key(f)));
      planned.push(...(await this.bulk(snap)));
    }
    if (planned.length) {
      await this.fab("filling");
      await this.jev(fillGoal(planned, this.context), planned);
    }
    return this.ask<string[]>({ type: "verify" });
  }

  /** After a submit/next click, wait for the next form step, a page without a form, or visible errors. */
  async next(before: { url: string; signature: string }) {
    let last = "", stable = 0;
    for (let i = 0; i < 40; i++) {
      await sleep(300);
      let d: { score: number; signature: string; url: string; alerts: string[] };
      try {
        d = await ask(this.tabId, 0, { type: "detect" });
      } catch {
        continue; // navigating; the new content script is not ready yet
      }
      const changed = d.url !== before.url || d.signature !== before.signature;
      if (!changed) {
        if (d.alerts.length && i > 4) return { kind: "error" as const, alerts: d.alerts };
        continue;
      }
      stable = d.signature === last ? stable + 1 : 0;
      last = d.signature;
      if (stable >= 1) return d.score >= SHOW ? { kind: "form" as const, signature: d.signature } : { kind: "none" as const };
    }
    return { kind: "none" as const };
  }
}

const running = new Set<number>();
const bestFrame = new Map<number, { frameId: number; score: number }>();

async function fillTab(tabId: number) {
  if (running.has(tabId)) return;
  running.add(tabId);
  const settings = await getSettings();
  const context = await getContext();
  const run = new Run(tabId, bestFrame.get(tabId)?.frameId ?? 0, settings.env, context?.content ?? "");
  run.t = translator(settings.locale);
  const log: RunLog = { url: "", startedAt: run.started, fills: run.fills, modelCalls: 0, elapsedMs: 0, result: "done", missing: [] };
  try {
    if (!context?.content.trim()) {
      await run.fab("error", run.t("noContext"));
      chrome.action.openPopup?.().catch(() => {});
      return;
    }
    if (!settings.env.TEXT_MODEL_BASE_URL || !settings.env.TEXT_MODEL) {
      await run.fab("error", run.t("noKeys"));
      return;
    }
    log.url = (await chrome.tabs.get(tabId)).url ?? "";
    try {
      await attach(tabId);
    } catch (e) {
      // Chrome refuses to attach when the page holds another extension's frame. Fall back to DOM events instead of failing.
      run.trusted = false;
      run.debug = "synthetic input: " + String((e as Error).message ?? e);
    }
    const seen = new Set<string>();
    for (let pages = 1; ; pages++) {
      const missing = await run.page();
      log.missing = missing;
      if (missing.length) {
        log.result = "partial";
        await run.fab("warn", run.t("needYou", { n: missing.length }));
        return;
      }
      if (!settings.autoSubmit || pages >= MAX_PAGES) break;
      const submit = await run.ask<{ node: number; label: string } | null>({ type: "submitButton" });
      if (!submit) break;
      if (!(await ask<boolean>(tabId, 0, { type: "countdown", ms: 1500 }))) break;
      const before = await ask(tabId, 0, { type: "detect" });
      seen.add(before.signature);
      await run.click(submit.node);
      run.fills.push({ label: submit.label, value: "submit", via: "jev" });
      const next = await run.next(before);
      if (next.kind === "error") {
        log.result = "blocked";
        await run.fab("error", run.t("stopped", { reason: next.alerts[0] }));
        return;
      }
      if (next.kind === "none" || seen.has(next.signature)) break;
      run.frameId = 0;
    }
    await run.fab("done", run.t("filled", { n: run.fills.filter(f => f.value !== "submit").length }));
  } catch (e) {
    log.result = "error";
    log.error = String((e as Error).message ?? e);
    await run.fab("error", log.error.slice(0, 120));
  } finally {
    log.modelCalls = run.calls;
    log.debug = run.debug;
    log.elapsedMs = Date.now() - run.started;
    await addRun(log);
    await detach(tabId);
    running.delete(tabId);
  }
}

async function testConnection(env: Env) {
  const out: Record<string, string> = {};
  try {
    const r = await postJson(env.TEXT_MODEL_BASE_URL.replace(/\/$/, "") + "/chat/completions", env.TEXT_MODEL_API_KEY, {
      model: env.TEXT_MODEL, max_tokens: 20, response_format: { type: "json_object" },
      ...(env.TEXT_MODEL_REASONING === "none" ? { reasoning: { enabled: false } } : {}),
      messages: [{ role: "user", content: 'Reply with {"ok": true}' }],
    });
    out.text = r.choices?.[0]?.message ? "OK" : "Unexpected response";
  } catch (e) {
    out.text = String((e as Error).message);
  }
  try {
    const r = await postJson("https://api.typesafe.ai/v1/systemone", env.TYPESAFE_API_KEY, {
      model: env.TYPESAFE_MODEL || "jev-latest", state: { page: "ping" },
      questions: { q: { type: "choice", criteria: { A: "yes", B: "no" }, instructions: { goal: "Pick A" } } },
    });
    out.decision = r.answers?.q?.choice ? "OK" : "Unexpected response";
  } catch (e) {
    out.decision = String((e as Error).message);
  }
  return out;
}

chrome.runtime.onMessage.addListener((m: BackgroundRequest, sender, reply) => {
  const tabId = sender.tab?.id;
  if (m.type === "fill") {
    void fillTab(m.tabId ?? tabId!);
  } else if (m.type === "detected" && tabId !== undefined && sender.frameId !== undefined) {
    const best = bestFrame.get(tabId);
    if (!best || m.score >= best.score || best.frameId === sender.frameId) {
      bestFrame.set(tabId, { frameId: sender.frameId, score: m.score });
      ask(tabId, 0, { type: "showFab", show: true }).catch(() => {});
    }
  } else if (m.type === "status") {
    ask(m.tabId, 0, { type: "detect" }).then(
      d => reply({ detected: d.score >= SHOW || (bestFrame.get(m.tabId)?.score ?? 0) >= SHOW, running: running.has(m.tabId) }),
      () => reply({ detected: false, running: false }),
    );
    return true;
  } else if (m.type === "openPopup") {
    chrome.action.openPopup?.().catch(() => {});
  } else if (m.type === "testConnection") {
    getSettings().then(s => testConnection(s.env)).then(reply);
    return true;
  }
});

chrome.tabs.onUpdated.addListener((tabId, info) => info.status === "loading" && bestFrame.delete(tabId));
chrome.tabs.onRemoved.addListener(tabId => bestFrame.delete(tabId));
chrome.commands.onCommand.addListener(async command => {
  if (command !== "fill-form") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) void fillTab(tab.id);
});
