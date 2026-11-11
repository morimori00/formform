// Context from the self-hosted formform server (Onyx + server/formform_onyx). Called only from the service worker.
import type { Env } from "../shared/storage";
import type { Field } from "../shared/types";

export type Passage = { title: string; source: string; link: string | null; content: string };
export type SourceStatus = { id: number; name: string; source: string; status: string; docs: number; last_indexed: string | null };

/** Upper bound on retrieved text added to the prompt context (characters). */
export const MAX_RETRIEVED = 12000;
const MAX_QUERIES = 4;
const NOISE = /[*＊※:：]|必須|任意|必填|選填|\(?\b(?:required|optional)\b\)?/gi;

/** Search queries made of the labels of the fields that are still empty: at most `max`, a few labels each. */
export function buildQueries(fields: Pick<Field, "label" | "hint" | "filled">[], max = MAX_QUERIES): string[] {
  const labels = [...new Set(fields.filter(f => !f.filled)
    .map(f => (f.label || f.hint).replace(NOISE, " ").replace(/\s+/g, " ").trim().slice(0, 60))
    .filter(Boolean))];
  const per = Math.max(4, Math.ceil(labels.length / max));
  const queries: string[] = [];
  for (let i = 0; i < labels.length; i += per) queries.push(labels.slice(i, i + per).join(" "));
  return queries;
}

/** The Markdown file first, then retrieved passages up to `max` characters. Without passages the Markdown is returned unchanged. */
export function mergeContext(markdown: string, passages: Passage[], max = MAX_RETRIEVED): string {
  const blocks: string[] = [];
  let used = 0;
  for (const p of passages) {
    const block = `## ${p.title} (${p.source})\n${p.content.trim()}`;
    if (used + block.length > max) continue;
    used += block.length;
    blocks.push(block);
  }
  if (!blocks.length) return markdown;
  return [markdown.trim(), "# Retrieved from connected sources\n\n" + blocks.join("\n\n")].filter(Boolean).join("\n\n");
}

export const serverUrl = (env: Env) => env.FORMFORM_SERVER_URL.trim().replace(/\/+$/, "");

async function call<T>(env: Env, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(serverUrl(env) + "/api/formform/" + path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.FORMFORM_SERVER_API_KEY}` },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    throw new Error("Context server unreachable");
  }
  if (!response.ok) throw new Error(`Context server returned HTTP ${response.status}`);
  return response.json();
}

export async function fetchPassages(env: Env, queries: string[]): Promise<Passage[]> {
  const r = await call<{ passages: Passage[] }>(env, "context", { queries, limit: 5, max_chars: MAX_RETRIEVED });
  return Array.isArray(r.passages) ? r.passages.filter(p => typeof p?.content === "string") : [];
}

export const fetchSources = (env: Env) => call<SourceStatus[]>(env, "sources");
