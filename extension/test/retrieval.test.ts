import { afterEach, describe, expect, it, vi } from "vitest";
import { buildQueries, fetchPassages, mergeContext, type Passage } from "../src/background/retrieval";
import { DEFAULT_ENV } from "../src/shared/storage";

const field = (label: string, filled = false, hint = "") => ({ label, hint, filled });
const passage = (title: string, content: string): Passage => ({ title, source: "file", link: null, content });

describe("buildQueries", () => {
  it("uses only empty fields, strips required marks, and drops duplicates", () => {
    expect(buildQueries([field("会社名 *必須"), field("Email (required)"), field("会社名"), field("電話番号", true), field("", false, "部署")]))
      .toEqual(["会社名 Email 部署"]);
  });
  it("never sends more than four queries", () => {
    const queries = buildQueries(Array.from({ length: 30 }, (_, i) => field("field " + i)));
    expect(queries).toHaveLength(4);
    expect(queries.join(" ")).toContain("field 29");
  });
  it("sends nothing when every field is filled", () => {
    expect(buildQueries([field("Name", true)])).toEqual([]);
  });
});

describe("mergeContext", () => {
  it("returns the Markdown unchanged when nothing was retrieved", () => {
    expect(mergeContext("# Me\nName: A", [])).toBe("# Me\nName: A");
  });
  it("puts the Markdown first and the passages after it", () => {
    expect(mergeContext("# Me", [passage("会社概要.pdf", " 資本金 1 億円 ")]))
      .toBe("# Me\n\n# Retrieved from connected sources\n\n## 会社概要.pdf (file)\n資本金 1 億円");
  });
  it("works without a Markdown file and stays within the size bound", () => {
    const merged = mergeContext("", [passage("a", "x".repeat(60)), passage("b", "y".repeat(60)), passage("c", "z".repeat(10))], 100);
    expect(merged).toContain("## a (file)");
    expect(merged).not.toContain("## b (file)"); // would exceed the bound
    expect(merged).toContain("## c (file)");
  });
});

describe("fetchPassages", () => {
  afterEach(() => vi.unstubAllGlobals());
  const env = { ...DEFAULT_ENV, FORMFORM_SERVER_URL: "http://onyx.internal:3080/", FORMFORM_SERVER_API_KEY: "k" };
  it("posts the queries with the bearer key and keeps only well-formed passages", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ passages: [passage("t", "c"), { title: "bad" }] })));
    vi.stubGlobal("fetch", fetch);
    expect(await fetchPassages(env, ["会社名"])).toEqual([passage("t", "c")]);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://onyx.internal:3080/api/formform/context");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer k");
    expect(JSON.parse(init.body as string).queries).toEqual(["会社名"]);
  });
  it("reports an HTTP error instead of returning an empty context", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })));
    await expect(fetchPassages(env, ["x"])).rejects.toThrow("HTTP 401");
  });
});
