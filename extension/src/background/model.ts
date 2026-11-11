// Port of jev-ultrafast/jev_ultrafast/model.py plus the Bulk Fill request.
import type { Env } from "../shared/storage";
import type { Action, Field, Snapshot } from "../shared/types";
import { BULK, NEXT_ACTION, TARGET, TEXT_VALUE } from "./prompts";

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export async function postJson(url: string, key: string, body: unknown): Promise<any> {
  for (let attempt = 0; attempt < 3; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(25000),
      });
    } catch {
      throw new Error("Model connection failed; no action executed.");
    }
    // Model calls do not touch the page, so a bounded retry is allowed here (never for browser input).
    if ([429, 503, 529].includes(response.status) && attempt < 2) {
      await sleep(500 * 2 ** attempt);
      continue;
    }
    if (!response.ok) throw new Error(`Model provider returned HTTP ${response.status}; no action executed.`);
    return response.json();
  }
  throw new Error("Model unavailable");
}

export type Choice = { choice: string; confidence: number; probabilities: Record<string, number> };

export function validateChoice(answer: any, ids: Record<string, unknown>): Choice {
  const keys = Object.keys(ids);
  try {
    const p = answer.probabilities as Record<string, number>;
    const numbers = [...Object.values(p), answer.confidence];
    const valid =
      keys.includes(answer.choice) &&
      Object.keys(p).length === keys.length && keys.every(k => k in p) &&
      numbers.every(n => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1) &&
      Math.abs(Object.values(p).reduce((a, b) => a + b, 0) - 1) < 0.02 &&
      p[answer.choice] >= Math.max(...Object.values(p)) - 1e-6;
    if (valid) return answer;
  } catch {}
  throw new Error("Invalid TypeSafe response; no action executed.");
}

type Element = { index: string; label: string; operations: string[]; options?: { index: string; label: string; value?: string }[]; [k: string]: unknown };

/** One index per observed element; each operation has its own valid target choices. */
export function actionSpace(actions: Action[]) {
  const elements: Element[] = [];
  const indices = new Map<number, string>();
  const targets: Record<string, Record<string, Action>> = {};
  const controls: Record<string, Action> = {};
  const operations: Record<string, string> = { click: "CLICK", fill: "TYPE_TEXT", select: "SELECT" };
  for (const action of actions) {
    if (!(action.kind in operations)) {
      controls[action.id.toUpperCase()] = action;
      continue;
    }
    if (!indices.has(action.node)) {
      const index = String(elements.length + 1);
      indices.set(action.node, index);
      const element: Element = { index, label: action.label.split(" → ")[0], operations: [] };
      for (const k of ["role", "value", "checked", "selected", "expanded"] as const) if (action[k] !== undefined) element[k] = action[k];
      if (action.kind === "select") {
        element.value = action.current_value ?? "";
        element.options = [];
      }
      elements.push(element);
    }
    const index = indices.get(action.node)!;
    const operation = operations[action.kind];
    const element = elements[Number(index) - 1];
    if (!element.operations.includes(operation)) element.operations.push(operation);
    let target = index;
    if (action.kind === "select") {
      target = `${index}:${element.options!.length + 1}`;
      element.options!.push({ index: target, label: action.label, value: action.value });
    }
    (targets[operation] ??= {})[target] = action;
  }
  return { elements, targets, controls };
}

export type HistoryItem = { action: string; kind: string; text: string | null; page_changed: boolean | null };

export type Decision = { choice: string; operation: string; target: string | null; confidence: number; latencyMs: number };

export async function choose(page: Snapshot, goal: string, history: HistoryItem[], env: Env): Promise<Decision> {
  const { elements, targets, controls } = actionSpace(page.actions);
  const labels: Record<string, string> = {
    CLICK: "Click an element, button, menu option, autocomplete suggestion, or calendar day.",
    TYPE_TEXT: "Enter or replace text in an editable field. A small LLM will supply the value from the goal.",
    SELECT: "Select an observed dropdown value.",
  };
  const operations: Record<string, string> = {};
  for (const k of Object.keys(targets)) operations[k] = labels[k];
  for (const [k, v] of Object.entries(controls)) operations[k] = v.label;
  operations.DONE = "Every requirement is visibly satisfied.";
  operations.BLOCKED = "No supported operation can progress.";
  const questions: Record<string, unknown> = {
    operation: { type: "choice", criteria: operations, instructions: { goal, rules: NEXT_ACTION } },
  };
  for (const [operation, candidates] of Object.entries(targets)) {
    const criteria: Record<string, unknown> = {};
    for (const [index, a] of Object.entries(candidates)) {
      criteria[index] = {
        element: `[${index}] ${a.label}`,
        current_value: a.current_value ?? a.value ?? "",
        ...Object.fromEntries((["role", "checked", "selected", "expanded"] as const).filter(k => a[k] !== undefined).map(k => [k, a[k]])),
      };
    }
    questions[operation.toLowerCase() + "_target"] = {
      type: "choice", criteria, instructions: { goal, operation, rules: [NEXT_ACTION, TARGET] },
    };
  }
  const body = {
    model: env.TYPESAFE_MODEL || "jev-latest",
    state: {
      page: { url: page.url, title: page.title, text: page.text },
      elements,
      recent_actions: history.slice(-10),
    },
    questions,
  };
  const started = performance.now();
  const result = await postJson("https://api.typesafe.ai/v1/systemone", env.TYPESAFE_API_KEY, body);
  const op = validateChoice(result.answers?.operation ?? {}, operations);
  let choice: string;
  let target: string | null = null;
  if (op.choice in targets) {
    // Unused target heads cannot cause an action. Validate only the head the operation selected.
    const t = validateChoice(result.answers?.[op.choice.toLowerCase() + "_target"] ?? {}, targets[op.choice]);
    target = t.choice;
    choice = targets[op.choice][target].id;
  } else {
    choice = op.choice in controls ? controls[op.choice].id : op.choice;
  }
  return { choice, operation: op.choice, target, confidence: op.confidence, latencyMs: Math.round(performance.now() - started) };
}

function reasoning(env: Env) {
  if (env.TEXT_MODEL_REASONING === "none") return { reasoning: { enabled: false } };
  if (env.TEXT_MODEL_BASE_URL.includes("api.deepseek.com/")) return { thinking: { type: "disabled" } };
  return { reasoning: { effort: "low" } };
}

async function chatJson(env: Env, system: string, user: unknown, maxTokens: number) {
  if (!env.TEXT_MODEL_API_KEY && !/localhost|127\.0\.0\.1/.test(env.TEXT_MODEL_BASE_URL)) {
    throw new Error("TEXT_MODEL_API_KEY is not set.");
  }
  const result = await postJson(env.TEXT_MODEL_BASE_URL.replace(/\/$/, "") + "/chat/completions", env.TEXT_MODEL_API_KEY, {
    model: env.TEXT_MODEL,
    max_tokens: maxTokens,
    response_format: { type: "json_object" },
    ...reasoning(env),
    messages: [
      { role: "system", content: system },
      { role: "user", content: JSON.stringify(user) },
    ],
  });
  const content: string = result.choices?.[0]?.message?.content ?? "";
  return JSON.parse(content.replace(/^```(?:json)?\s*|\s*```$/g, ""));
}

export function fieldContext(goal: string, action: Action, page: Snapshot, history: HistoryItem[]) {
  return {
    goal,
    field: { label: action.label, role: action.role, value: action.value },
    page: { title: page.title, text: page.text.slice(0, 6000) },
    recent_actions: history.slice(-6).map(h => ({ action: h.action, text: h.text })),
  };
}

export async function fieldText(context: ReturnType<typeof fieldContext>, env: Env): Promise<string> {
  let value: unknown;
  for (let attempt = 0; attempt < 2 && typeof value !== "string"; attempt++) {
    try {
      const output = await chatJson(env, TEXT_VALUE, context, 1024);
      value = Object.keys(output).length === 1 ? output.text : undefined;
    } catch (e) {
      if (String(e).includes("HTTP") || String(e).includes("not set")) throw e;
    }
  }
  if (typeof value !== "string" || !value.trim() || value.length > 2000) {
    throw new Error("Text helper returned no valid field value; nothing typed.");
  }
  return value;
}

export type Fill = { field: Field; value?: string; option?: string };

/** One request for every simple field. Returns only fills that map to an offered field and option. */
export async function bulkFill(context: string, page: Snapshot, fields: Field[], env: Env): Promise<Fill[]> {
  const byIndex = new Map(fields.map((f, i) => [String(i + 1), f]));
  const output = await chatJson(env, BULK, {
    context,
    page: { title: page.title, url: page.url, form_text: page.formText || page.text },
    fields: fields.map((f, i) => ({
      index: String(i + 1),
      widget: f.widget,
      label: f.label,
      hint: f.hint !== f.label ? f.hint : undefined,
      type: f.type,
      autocomplete: f.autocomplete,
      name: f.name,
      required: f.required || undefined,
      part: f.part,
      options: f.options?.map(o => ({ id: o.id, label: o.label })),
    })),
  }, 4096);
  lastBulkRaw = JSON.stringify(output).slice(0, 600);
  return parseFills(output, byIndex);
}

/** Raw text of the last Bulk answer, kept in the run log for diagnosis. */
export let lastBulkRaw = "";

export function parseFills(output: any, byIndex: Map<string, Field>): Fill[] {
  const fills: Fill[] = [];
  const used = new Set<string>();
  for (const f of Array.isArray(output?.fills) ? output.fills : []) {
    const field = byIndex.get(String(f?.index));
    if (!field || used.has(String(f.index))) continue;
    if (field.options && field.widget !== "custom") {
      const option = String(f.option ?? f.value ?? "");
      const match = field.options.find(o => o.id === option) ?? field.options.find(o => o.label === option);
      if (match) fills.push({ field, option: match.id });
    } else if (typeof f.value === "string" && f.value.trim() && f.value.length <= 2000) {
      fills.push({ field, value: f.value });
    } else continue;
    used.add(String(f.index));
  }
  return fills;
}
