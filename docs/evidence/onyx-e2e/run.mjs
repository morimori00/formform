// End-to-end check: real extension build in Chromium, real Onyx server, real text model. Prints no secrets.
// Not part of `npm test` (it calls the paid text model once per run).
//   npm i --no-save playwright-core && npm run build
//   MODEL_ENV=/path/to/jev-ultrafast/.env CHROMIUM=/path/to/chrome node docs/evidence/onyx-e2e/run.mjs <mode> [--popup out.png] [--shot out.png]
// modes: server (no Markdown) | both | markdown (no server) | none | down | badkey
// server/.env.admin must hold FORMFORM_SERVER_URL and FORMFORM_SERVER_API_KEY (gitignored).
import { chromium } from "playwright-core";
import http from "node:http";
import { readFileSync, mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, extname } from "node:path";

const repo = new URL("../../..", import.meta.url).pathname.replace(/\/$/, "");
const mode = process.argv[2] ?? "server";
const env = path => Object.fromEntries(readFileSync(path, "utf8").split(/\r?\n/).map(l => l.match(/^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/)).filter(Boolean).map(m => [m[1], m[2].replace(/^(['"])(.*)\1$/, "$2")]));
const model = env(process.env.MODEL_ENV);
const server = env(repo + "/server/.env.admin");

const fixtures = repo + "/extension/fixtures";
const web = http.createServer((req, res) => {
  const file = join(fixtures, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(fixtures) || !existsSync(file)) return res.writeHead(404).end();
  res.writeHead(200, { "Content-Type": extname(file) === ".html" ? "text/html; charset=utf-8" : "text/plain" }).end(readFileSync(file));
}).listen(8793, "127.0.0.1");

const dist = repo + "/extension/dist";
const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "ff-e2e-")), {
  executablePath: process.env.CHROMIUM, // full Chromium / Chrome for Testing (extensions need the new headless mode)
  headless: false, args: ["--headless=new", `--disable-extensions-except=${dist}`, `--load-extension=${dist}`], viewport: { width: 1100, height: 1500 },
});
const sw = ctx.serviceWorkers()[0] ?? await ctx.waitForEvent("serviceworker");
const id = new URL(sw.url()).host;
const pick = (o, keys) => Object.fromEntries(keys.filter(k => o[k] !== undefined).map(k => [k, o[k]]));
const settingsEnv = {
  ...pick(model, ["TYPESAFE_API_KEY", "TYPESAFE_MODEL", "TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL", "TEXT_MODEL", "TEXT_MODEL_REASONING"]),
  ...(mode === "server" || mode === "both" ? pick(server, ["FORMFORM_SERVER_URL", "FORMFORM_SERVER_API_KEY"]) : {}),
  ...(mode === "down" ? { FORMFORM_SERVER_URL: "http://127.0.0.1:9", FORMFORM_SERVER_API_KEY: "x" } : {}),
  ...(mode === "badkey" ? { FORMFORM_SERVER_URL: server.FORMFORM_SERVER_URL, FORMFORM_SERVER_API_KEY: "on_wrong" } : {}),
};
const markdown = mode === "markdown" || mode === "both" ? "# 担当者\n氏名: 相良 透\n携帯電話: 090-5555-0199\n" +
  (mode === "markdown" ? "# 会社\n商号: 株式会社アオバ精密\n法人番号: 7010401098765\n" : "") : null;
await sw.evaluate(async ([env, md]) => {
  await chrome.storage.local.set({
    settings: { locale: "ja", autoSubmit: false, disabledSites: [], consented: true, env },
    sources: md ? [{ id: "md", type: "markdown", name: "me.md", content: md, updatedAt: Date.now() }] : [],
  });
}, [settingsEnv, markdown]);

const out = { mode };
if (process.argv.includes("--popup")) {
  const popup = await ctx.newPage();
  await popup.setViewportSize({ width: 380, height: 900 });
  await popup.goto(`chrome-extension://${id}/popup.html?view=context`);
  await popup.waitForSelector("#sources .connector, #serverResult:not([hidden])", { timeout: 15000 });
  await popup.waitForTimeout(1500);
  out.popup = { cards: await popup.$$eval("#sources .connector", els => els.map(e => ({ cls: e.className.trim(), text: e.innerText.replace(/\n+/g, " | ") }))),
    result: await popup.$eval("#serverResult", e => e.hidden ? null : e.textContent) };
  await popup.screenshot({ path: process.argv[process.argv.indexOf("--popup") + 1] ?? "popup.png", fullPage: true });
  await popup.close();
}

const page = await ctx.newPage();
await page.goto("http://127.0.0.1:8793/e-ja-vendor.html");
const fab = await page.waitForSelector("[data-formform-ui]", { state: "attached", timeout: 15000 });
await page.waitForTimeout(500);
const box = await fab.boundingBox();
const t0 = Date.now();
await page.mouse.click(box.x + 45, box.y + 22);
let run;
for (let i = 0; i < 120 && !run; i++) {
  await page.waitForTimeout(500);
  run = await sw.evaluate(async t => ((await chrome.storage.local.get("runs")).runs ?? []).find(r => r.startedAt >= t - 2000), t0);
}
out.values = await page.evaluate(() => window.__values());
out.run = run && { result: run.result, modelCalls: run.modelCalls, elapsedMs: run.elapsedMs, fills: run.fills.length, missing: run.missing, error: run.error, debug: (run.debug ?? "").slice(0, 160) };
if (process.argv.includes("--shot")) await page.screenshot({ path: process.argv[process.argv.indexOf("--shot") + 1], fullPage: true });

const expected = { company: "株式会社アオバ精密", corporate_number: "7010401098765", zip: "1430016", address: "東京都大田区大森北四丁目18番7号",
  representative: "朝比奈澄江", founded: "1987-04-21", capital: "8500", employees: "214", bank: "みなと信用銀行", branch: "大森駅前",
  account_type: "toza", account_number: "0428817", account_kana: "アオバセイミツ", invoice_number: "T7010401098765", isms: "804512",
  security_email: "security@aoba-seimitsu.example" };
const norm = s => String(s ?? "").replace(/[\s,，]/g, "").normalize("NFKC");
out.check = Object.fromEntries(Object.entries(expected).map(([k, v]) => [k, norm(out.values[k]).includes(norm(v)) ? "ok" : `MISMATCH (${out.values[k]})`]));
out.correct = Object.values(out.check).filter(v => v === "ok").length + "/" + Object.keys(expected).length;
out.mobileLeftEmpty = mode === "both" ? out.values.mobile : out.values.mobile === "";
console.log(JSON.stringify(out, null, 1));
await ctx.close();
web.close();
