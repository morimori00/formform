import * as esbuild from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

const here = new URL(".", import.meta.url).pathname;
const out = here + "dist";
mkdirSync(out, { recursive: true });
const copy = () => {
  cpSync(here + "manifest.json", out + "/manifest.json");
  cpSync(here + "assets", out + "/assets", { recursive: true });
  cpSync(here + "_locales", out + "/_locales", { recursive: true });
  cpSync(here + "src/popup/popup.html", out + "/popup.html");
  cpSync(here + "src/popup/popup.css", out + "/popup.css");
};
const options = {
  entryPoints: {
    background: here + "src/background/index.ts",
    content: here + "src/content/index.ts",
    popup: here + "src/popup/popup.ts",
  },
  bundle: true, outdir: out, format: "esm", target: "chrome120", logLevel: "info",
  plugins: [{ name: "copy", setup: b => b.onEnd(copy) }],
};
// The content script is a classic script; an IIFE keeps its globals private.
const content = { ...options, entryPoints: { content: options.entryPoints.content }, format: "iife" };
const rest = { ...options, entryPoints: { background: options.entryPoints.background, popup: options.entryPoints.popup } };
if (process.argv.includes("--watch")) {
  for (const o of [content, rest]) (await esbuild.context(o)).watch();
} else {
  await Promise.all([esbuild.build(content), esbuild.build(rest)]);
}
