// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { actionSpace, parseFills, validateChoice } from "../src/background/model";
import { detect, SHOW } from "../src/content/detector";
import { parseEnv } from "../src/shared/storage";
import type { Action, Field } from "../src/shared/types";

describe("parseEnv", () => {
  it("reads jev-ultrafast .env keys and ignores the rest", () => {
    const env = parseEnv('# c\nTYPESAFE_API_KEY="ts"\nexport TEXT_MODEL=qwen/x:nitro\nOTHER=1\nTEXT_MODEL_REASONING=none');
    expect(env).toEqual({ TYPESAFE_API_KEY: "ts", TEXT_MODEL: "qwen/x:nitro", TEXT_MODEL_REASONING: "none" });
  });
});

describe("validateChoice", () => {
  const ids = { A: 1, B: 1 };
  it("accepts a consistent answer", () => {
    expect(validateChoice({ choice: "A", confidence: 0.9, probabilities: { A: 0.9, B: 0.1 } }, ids).choice).toBe("A");
  });
  it.each([
    { choice: "C", confidence: 0.9, probabilities: { A: 0.9, B: 0.1 } },
    { choice: "B", confidence: 0.9, probabilities: { A: 0.9, B: 0.1 } },
    { choice: "A", confidence: 0.9, probabilities: { A: 0.5, B: 0.1 } },
    { choice: "A", confidence: 2, probabilities: { A: 0.9, B: 0.1 } },
  ])("rejects %o", answer => expect(() => validateChoice(answer, ids)).toThrow());
});

describe("actionSpace", () => {
  it("indexes elements once and gives each operation its own targets", () => {
    const actions: Action[] = [
      { id: "e1", node: 7, kind: "fill", role: "textbox", label: "Name", value: "" },
      { id: "e2", node: 7, kind: "click", role: "textbox", label: "Open Name", value: "" },
      { id: "e3", node: 9, kind: "select", role: "combobox", label: "Size → L", value: "l", current_value: "M" },
      { id: "wait", node: 0, kind: "wait", label: "Wait" },
    ];
    const { elements, targets, controls } = actionSpace(actions);
    expect(elements.map(e => e.index)).toEqual(["1", "2"]);
    expect(Object.keys(targets.TYPE_TEXT)).toEqual(["1"]);
    expect(Object.keys(targets.SELECT)).toEqual(["2:1"]);
    expect(Object.keys(controls)).toEqual(["WAIT"]);
  });
});

describe("parseFills", () => {
  const f = (over: Partial<Field>): Field => ({ node: 1, widget: "text", label: "", hint: "", type: "text", required: false, value: "", filled: false, native: true, ...over });
  const byIndex = new Map([
    ["1", f({ label: "Company" })],
    ["2", f({ widget: "select", options: [{ id: "saas", label: "SaaS" }] })],
  ]);
  it("keeps only offered fields and options", () => {
    const fills = parseFills({ fills: [
      { index: "1", value: "Acme" }, { index: "1", value: "dup" }, { index: "2", option: "SaaS" },
      { index: "3", value: "ghost" }, { index: "2", option: "nope" },
    ] }, byIndex);
    expect(fills.map(x => x.value ?? x.option)).toEqual(["Acme", "saas"]);
  });
  it("survives junk", () => expect(parseFills({ fills: "x" }, byIndex)).toEqual([]));
});

describe("detector", () => {
  const score = (html: string) => {
    document.body.innerHTML = html;
    return detect().score;
  };
  it("shows on the Japanese event fixture", () => {
    const html = readFileSync(__dirname + "/../fixtures/a-ja-event.html", "utf8");
    document.documentElement.innerHTML = html.replace(/<script[\s\S]*?<\/script>/g, "");
    expect(detect().score).toBeGreaterThanOrEqual(SHOW);
  });
  it("hides on login, search, newsletter and comment boxes", () => {
    expect(score('<form><input type="email" placeholder="Email"><input type="password"><button>Log in</button></form>')).toBeLessThan(SHOW);
    expect(score('<form role="search"><input name="q"><button>Search</button></form>')).toBeLessThan(SHOW);
    expect(score('<form><input type="email" placeholder="you@x.com"><button>Subscribe</button></form>')).toBeLessThan(SHOW);
    expect(score('<form><input placeholder="Name"><input type="email" placeholder="Email"><textarea placeholder="Comment"></textarea><button>Post comment</button></form>')).toBeLessThan(SHOW);
  });
  it("shows a one-question step on a form builder", () => {
    history.replaceState(null, "", "/forms/d/e/x/viewform");
    const builder = location.href;
    Object.defineProperty(window, "location", { value: { ...location, href: "https://docs.google.com/forms/d/e/x/viewform", pathname: "/forms/d/e/x/viewform" }, configurable: true });
    const html = '<form><div role="heading">Are you applying? *</div><div role="radiogroup" aria-label="Are you applying?"><div role="radio" aria-checked="false">Mentor</div></div><div role="button">次へ</div></form>';
    expect(score(html)).toBeGreaterThanOrEqual(SHOW);
    Object.defineProperty(window, "location", { value: new URL(builder), configurable: true });
    expect(score(html)).toBeLessThan(SHOW); // the same single question elsewhere stays hidden
  });
  it("never shows on card forms", () => {
    expect(score('<form><input autocomplete="name"><input autocomplete="email"><input autocomplete="cc-number"><button>Pay</button></form>')).toBe(-Infinity);
  });
});
