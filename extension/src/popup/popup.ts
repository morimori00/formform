import { translator, type Key } from "../shared/i18n";
import { ENV_KEYS, getContext, getSettings, parseEnv, saveContext, saveSettings, type Env, type EnvKey, type Locale, type RunLog } from "../shared/storage";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
let t = translator("en");
let view = "home";
const MAX_MD = 64 * 1024;
const SECRET: EnvKey[] = ["TYPESAFE_API_KEY", "TEXT_MODEL_API_KEY", "FORMFORM_SERVER_API_KEY"];
const GROUPS: Record<string, EnvKey[]> = {
  decision: ["TYPESAFE_API_KEY", "TYPESAFE_MODEL"],
  text: ["TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL", "TEXT_MODEL", "TEXT_MODEL_REASONING"],
  server: ["FORMFORM_SERVER_URL", "FORMFORM_SERVER_API_KEY"],
};
const SOURCE_NAMES: Record<string, string> = { google_drive: "Google Drive", slack: "Slack", notion: "Notion", file: "Files", web: "Web" };
const SOURCE_STATES: Record<string, Key> = { ACTIVE: "sourceActive", SCHEDULED: "sourceIndexing", INITIAL_INDEXING: "sourceIndexing", PAUSED: "sourcePaused" };
type SourceStatus = { name: string; source: string; status: string; docs: number };

function toast(text: string) {
  const el = $("toast");
  el.textContent = text;
  el.hidden = false;
  setTimeout(() => (el.hidden = true), 1600);
}

function localize() {
  document.querySelectorAll<HTMLElement>("[data-t]").forEach(el => (el.textContent = t(el.dataset.t as Key)));
  $<HTMLTextAreaElement>("md").placeholder = t("editorPlaceholder");
  $("title").textContent = view === "home" ? "" : t(view as Key);
}

function go(next: string) {
  view = next;
  for (const v of ["home", "settings", "context"]) $(v).hidden = v !== next;
  $("back").hidden = next === "home";
  localize();
  if (next === "home") void renderHome();
}

async function renderHome() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const fill = $<HTMLButtonElement>("fill");
  const status = tab?.id ? await chrome.runtime.sendMessage({ type: "status", tabId: tab.id }).catch(() => null) : null;
  $("status").textContent = status?.detected ? "✓ " + t("detected") : t("notDetected");
  fill.disabled = !tab?.id || status?.running;
  fill.onclick = async () => {
    const s = await getSettings();
    if (!s.consented && !confirm(t("consentTitle") + "\n\n" + t("consentBody"))) return;
    await saveSettings({ consented: true });
    chrome.runtime.sendMessage({ type: "fill", tabId: tab!.id });
    window.close();
  };
  const { runs = [] } = await chrome.storage.local.get("runs");
  $("runs").replaceChildren(...(runs as RunLog[]).slice(0, 5).map(r => {
    const li = document.createElement("li");
    const host = (() => { try { return new URL(r.url).host + new URL(r.url).pathname; } catch { return r.url; } })();
    li.innerHTML = `<b></b><span></span>`;
    li.querySelector("b")!.textContent = host;
    const span = li.querySelector("span")!;
    span.className = r.result === "done" ? "ok" : r.result;
    span.textContent = `${r.result} · ${r.fills.length} fields · ${(r.elapsedMs / 1000).toFixed(1)}s · ${r.modelCalls} calls` +
      (r.missing.length ? ` · missing: ${r.missing.join(", ")}` : "") + (r.error ? ` · ${r.error}` : "");
    return li;
  }));
}

function renderEnv(env: Env) {
  for (const [group, keys] of Object.entries(GROUPS)) {
    const box = document.querySelector(`[data-group="${group}"]`)!;
    box.replaceChildren(...keys.map(key => {
      const label = document.createElement("label");
      label.innerHTML = `<code>${key}</code><input>`;
      const input = label.querySelector("input")!;
      input.name = key;
      input.type = SECRET.includes(key) ? "password" : "text";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.value = env[key];
      return label;
    }));
  }
  markPreset(env.TEXT_MODEL_BASE_URL);
}

function readEnv(): Env {
  const env = {} as Env;
  for (const key of ENV_KEYS) env[key] = (document.querySelector<HTMLInputElement>(`input[name="${key}"]`)?.value ?? "").trim();
  return env;
}

function markPreset(url: string) {
  document.querySelectorAll<HTMLButtonElement>("[data-preset]").forEach(b => b.classList.toggle("on", b.dataset.preset === url));
}

async function renderSites() {
  const s = await getSettings();
  $("sites").replaceChildren(...(s.disabledSites.length ? s.disabledSites.map(site => {
    const li = document.createElement("li");
    li.textContent = site;
    const b = document.createElement("button");
    b.textContent = t("remove");
    b.onclick = async () => {
      await saveSettings({ disabledSites: (await getSettings()).disabledSites.filter(x => x !== site) });
      void renderSites();
    };
    li.append(b);
    return li;
  }) : [Object.assign(document.createElement("li"), { className: "empty", textContent: t("none") })]));
}

/** Connected sources come from the server through the service worker; the key never leaves it. */
async function renderSources() {
  const out = $("serverResult"), list = $("sources");
  list.replaceChildren();
  out.hidden = !readEnv().FORMFORM_SERVER_URL;
  if (out.hidden) return;
  out.className = "result";
  out.textContent = t("testing");
  const r: { sources?: SourceStatus[]; error?: string } = await chrome.runtime.sendMessage({ type: "sources" });
  out.classList.toggle("bad", !r.sources);
  out.textContent = r.error ?? t("serverNoSources");
  out.hidden = !!r.sources?.length;
  list.replaceChildren(...(r.sources ?? []).map(s => {
    const card = document.createElement("div");
    card.className = "connector " + (s.status === "ACTIVE" ? "on" : s.status in SOURCE_STATES ? "" : "bad");
    card.innerHTML = `<i class="sq"></i><span></span><small></small>`;
    card.querySelector("span")!.textContent = s.name;
    card.querySelector("small")!.textContent =
      `${SOURCE_NAMES[s.source] ?? s.source} · ${t(SOURCE_STATES[s.status] ?? "sourceError")} · ${t("sourceDocs", { n: s.docs })}`;
    return card;
  }));
}

function applyEnvText(text: string) {
  const parsed = parseEnv(text);
  const env = { ...readEnv(), ...parsed };
  renderEnv(env);
  void saveSettings({ env });
  toast(`${t("saved")} · ${Object.keys(parsed).length} keys`);
}

function renderMeta(text: string) {
  $("mdMeta").textContent = t("chars", { n: text.length, t: Math.ceil(text.length / 3) });
}

async function loadMarkdown(file: File) {
  if (file.size > MAX_MD) return toast("> 64 KB");
  const text = await file.text();
  $<HTMLTextAreaElement>("md").value = text;
  $("mdName").textContent = file.name;
  renderMeta(text);
  await saveContext(file.name, text);
  toast(t("saved"));
}

async function init() {
  const s = await getSettings();
  t = translator(s.locale);
  $<HTMLSelectElement>("locale").value = s.locale;
  $<HTMLInputElement>("autoSubmit").checked = s.autoSubmit;
  renderEnv(s.env);
  const ctx = await getContext();
  $<HTMLTextAreaElement>("md").value = ctx?.content ?? "";
  $("mdName").textContent = ctx?.name ?? "";
  renderMeta(ctx?.content ?? "");
  go(new URLSearchParams(location.search).get("view") ?? "home");
  void renderSites();
  void renderSources();
  $("serverSave").onclick = async () => {
    await saveSettings({ env: readEnv() });
    void renderSources();
  };
  $("serverManage").onclick = () => {
    const url = readEnv().FORMFORM_SERVER_URL.replace(/\/+$/, "");
    if (/^https?:\/\//.test(url)) void chrome.tabs.create({ url: url + "/admin/indexing-status" });
  };

  document.querySelectorAll<HTMLButtonElement>("[data-go]").forEach(b => (b.onclick = () => go(b.dataset.go!)));
  $("back").onclick = () => go("home");
  $<HTMLSelectElement>("locale").onchange = async e => {
    const locale = (e.target as HTMLSelectElement).value as Locale;
    t = translator(locale);
    await saveSettings({ locale });
    localize();
    void renderSites();
  };
  $<HTMLInputElement>("autoSubmit").onchange = e => saveSettings({ autoSubmit: (e.target as HTMLInputElement).checked });
  $<HTMLInputElement>("envFile").onchange = async e => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) applyEnvText(await file.text());
  };
  $("envPasteToggle").onclick = () => {
    const area = $<HTMLTextAreaElement>("envPaste");
    if (!area.hidden && area.value.trim()) {
      applyEnvText(area.value);
      area.value = "";
    }
    area.hidden = !area.hidden;
  };
  document.querySelectorAll<HTMLButtonElement>("[data-preset]").forEach(b => (b.onclick = () => {
    document.querySelector<HTMLInputElement>('input[name="TEXT_MODEL_BASE_URL"]')!.value = b.dataset.preset!;
    markPreset(b.dataset.preset!);
  }));
  $("save").onclick = async () => {
    await saveSettings({ env: readEnv() });
    toast(t("saved"));
  };
  $("test").onclick = async () => {
    await saveSettings({ env: readEnv() });
    const out = $("testResult");
    out.hidden = false;
    out.className = "result";
    out.textContent = t("testing");
    const r = await chrome.runtime.sendMessage({ type: "testConnection" });
    out.textContent = `Decision (TypeSafe): ${r.decision}\nText (${readEnv().TEXT_MODEL}): ${r.text}`;
    out.classList.toggle("bad", r.decision !== "OK" || r.text !== "OK");
  };

  const drop = $("drop");
  drop.ondragover = e => (e.preventDefault(), drop.classList.add("over"));
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => {
    e.preventDefault();
    drop.classList.remove("over");
    const file = e.dataTransfer?.files[0];
    if (file) void loadMarkdown(file);
  };
  $<HTMLInputElement>("mdFile").onchange = e => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) void loadMarkdown(file);
  };
  $<HTMLTextAreaElement>("md").oninput = e => renderMeta((e.target as HTMLTextAreaElement).value);
  $("mdSave").onclick = async () => {
    const text = $<HTMLTextAreaElement>("md").value;
    if (text.length > MAX_MD) return toast("> 64 KB");
    await saveContext($("mdName").textContent || "context.md", text);
    if (!$("mdName").textContent) $("mdName").textContent = "context.md";
    toast(t("saved"));
  };
  $("mdRemove").onclick = async () => {
    await saveContext("", null);
    $<HTMLTextAreaElement>("md").value = "";
    $("mdName").textContent = "";
    renderMeta("");
  };
}

void init();
