// Settings use the same keys as jev-ultrafast's .env so one file configures both.
export const ENV_KEYS = [
  "TYPESAFE_API_KEY",
  "TYPESAFE_MODEL",
  "TEXT_MODEL_API_KEY",
  "TEXT_MODEL_BASE_URL",
  "TEXT_MODEL",
  "TEXT_MODEL_REASONING",
  "FORMFORM_SERVER_URL",
  "FORMFORM_SERVER_API_KEY",
] as const;
export type EnvKey = (typeof ENV_KEYS)[number];
export type Env = Record<EnvKey, string>;
export type Locale = "en" | "ja" | "zh_TW";

export type Settings = {
  locale: Locale;
  autoSubmit: boolean;
  env: Env;
  disabledSites: string[];
  consented: boolean;
};

// Other sources (Google Drive, Slack, Notion, files…) live on the self-hosted server and are read at Fill time,
// never copied into this browser (background/retrieval.ts).
export type Source = { id: string; type: "markdown"; name: string; content: string; updatedAt: number };

export type RunLog = {
  url: string;
  startedAt: number;
  fills: { label: string; value: string; via: "bulk" | "jev" }[];
  modelCalls: number;
  elapsedMs: number;
  result: "done" | "partial" | "blocked" | "error";
  missing: string[];
  error?: string;
  debug?: string;
};

export const DEFAULT_ENV: Env = {
  TYPESAFE_API_KEY: "",
  TYPESAFE_MODEL: "jev-latest",
  TEXT_MODEL_API_KEY: "",
  TEXT_MODEL_BASE_URL: "https://openrouter.ai/api/v1",
  TEXT_MODEL: "qwen/qwen3.8-27b:nitro",
  TEXT_MODEL_REASONING: "none",
  FORMFORM_SERVER_URL: "",
  FORMFORM_SERVER_API_KEY: "",
};

export function defaultLocale(language = navigator.language): Locale {
  if (/^zh-(TW|HK|Hant)/i.test(language)) return "zh_TW";
  if (/^ja/i.test(language)) return "ja";
  return "en";
}

export async function getSettings(): Promise<Settings> {
  const { settings } = (await chrome.storage.local.get("settings")) as { settings?: Partial<Settings> };
  return {
    locale: defaultLocale(),
    autoSubmit: false,
    disabledSites: [],
    consented: false,
    ...settings,
    env: { ...DEFAULT_ENV, ...settings?.env },
  };
}

export async function saveSettings(patch: Partial<Settings>) {
  await chrome.storage.local.set({ settings: { ...(await getSettings()), ...patch } });
}

export async function getContext(): Promise<Source | null> {
  const { sources = [] } = await chrome.storage.local.get("sources");
  return (sources as Source[]).find(s => s.type === "markdown") ?? null;
}

export async function saveContext(name: string, content: string | null) {
  const sources: Source[] = content === null ? [] : [{ id: "md", type: "markdown", name, content, updatedAt: Date.now() }];
  await chrome.storage.local.set({ sources });
}

export async function addRun(run: RunLog) {
  const { runs = [] } = (await chrome.storage.local.get("runs")) as { runs?: RunLog[] };
  await chrome.storage.local.set({ runs: [run, ...runs].slice(0, 20) });
}

/** Parse KEY=value lines (comments, quotes, export prefix). Unknown keys are ignored. */
export function parseEnv(text: string): Partial<Env> {
  const out: Partial<Env> = {};
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!m || !(ENV_KEYS as readonly string[]).includes(m[1])) continue;
    out[m[1] as EnvKey] = m[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return out;
}
