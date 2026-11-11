// "Is this a fillable form?" — cheap local scoring, no model. See docs/SPEC.md §5.
import { allRoots, closestDeep, nameOf, parentOf, visible } from "./dom";

export const FIELD =
  "input:not([type=hidden],[type=submit],[type=button],[type=reset],[type=image],[type=file],[type=search],[type=password]),select,textarea,[role=textbox]:not([contenteditable]),[role=combobox],[role=listbox],[role=radiogroup],[role=checkbox],[role=spinbutton]";
const BUTTON = "button,[type=submit],[role=button],input[type=button]";
const ID_AC = /^(name|given-name|family-name|organization(-title)?|email|tel(-national)?|street-address|address-line\d|address-level\d|postal-code|country(-name)?|bday)$/;
const ID_LEX = /company|organi[sz]ation|(first|last|full|your)\s?name|e-?mail|phone|mobile|address|zip|postal|city|job\s?title|department|会社|企業名|氏名|お名前|フリガナ|メール|電話|住所|郵便番号|都道府県|部署|役職|公司|姓名|名稱|手機|地址|郵遞區號|職稱|部門|統一編號/i;
export const SUBMIT = /submit|register|apply|sign\s?up|rsvp|enrol|request|book|next|continue|申し?込|送信|確認|登録|応募|エントリー|次へ|提交|送出|報名|申請|註冊|下一步/i;
const CONTEXT = /contact|inquiry|registration|application|survey|questionnaire|問い合わせ|申込|応募|エントリー|アンケート|資料請求|聯絡|報名|申請|問卷|表單/i;
const NEG = /search|log\s?in|sign\s?in|subscribe|newsletter|comment|reply|検索|ログイン|メルマガ|コメント|搜尋|登入|訂閱|留言/i;
export const SENSITIVE = /^cc-|one-time-code|card.?(num|no)|cvv|cvc|security.?code|カード番号|セキュリティコード|信用卡|卡號/i;
const BUILDER = /docs\.google\.com\/forms|forms\.(office|microsoft)\.com|typeform\.com|hsforms|hs-form|hbspt|jotform|tally\.so|formrun|form-mailer|surveymonkey/i;
const REQ = /\*|必須|必填|required/i;
const EDITOR = ".ProseMirror,.ck-editor,.ql-editor,.monaco-editor";

export const SHOW = 10;
export const HIDE = 6;

const regionCache = new WeakMap<Element, Element>();

export function labelOf(f: Element): string {
  const h = f as HTMLInputElement;
  return [nameOf(f), h.placeholder, h.name, f.id].filter(Boolean).join(" ").slice(0, 200);
}

export function regionOf(f: Element): Element {
  const hit = regionCache.get(f);
  if (hit?.isConnected) return hit;
  let n = closestDeep(f, "form,[role=form],fieldset:not(fieldset fieldset)");
  // A fieldset inside a larger form is only a group; prefer the outer form.
  const form = n && closestDeep(n, "form,[role=form]");
  if (form) n = form;
  if (!n) {
    n = f;
    for (let i = 0; i < 8; i++) {
      const p = parentOf(n);
      if (!p || p === document.body || p === document.documentElement || p.matches("main")) break;
      n = p;
      if (n.querySelector(BUTTON) && n.querySelectorAll(FIELD).length >= 3) break;
    }
  }
  regionCache.set(f, n);
  return n;
}

export function scoreRegion(root: Element, fields: Element[], pageCtx: string): number {
  let s = 0, ac = 0, lex = 0, req = 0, negText = "";
  const kinds = new Set<string>();
  if (root.querySelector("input[type=password]")) s -= 6;
  for (const f of fields) {
    const a = f.getAttribute("autocomplete") ?? "";
    const label = labelOf(f);
    if (SENSITIVE.test(a) || SENSITIVE.test(label)) return -Infinity;
    if (ID_AC.test(a.split(/\s+/).pop()!)) ac++;
    else if (ID_LEX.test(label)) lex++;
    if ((f as HTMLInputElement).required || f.getAttribute("aria-required") === "true" || REQ.test(label)) req++;
    kinds.add(f.getAttribute("role") ?? ((f as HTMLInputElement).type || f.tagName));
    negText += label + " ";
  }
  s += Math.min(ac * 3, 12) + Math.min(lex * 2, 12) + Math.min(Math.max(fields.length - 2, 0), 6);
  if (kinds.size >= 3) s += 2;
  if (req >= 2 || REQ.test((root as HTMLElement).innerText?.slice(0, 3000) ?? "")) s += 2;
  const buttons = [...root.querySelectorAll(BUTTON)].slice(0, 10)
    .map(b => b.textContent || (b as HTMLInputElement).value || "").join(" ");
  if (SUBMIT.test(buttons)) s += 3;
  const heading = root.querySelector("h1,h2,h3,legend,[role=heading]")?.textContent ?? "";
  if (CONTEXT.test(pageCtx + " " + heading)) s += 2;
  if (BUILDER.test(location.href + " " + root.className)) s += 6;
  if (kinds.has("radiogroup") || kinds.has("combobox")) s += 1;
  if (closestDeep(root, "[role=search]") || /search|検索|搜尋/i.test(buttons)) s -= 6;
  if (NEG.test(negText + buttons + heading)) s -= 4;
  if (closestDeep(root, "nav,header,footer")) s -= 3;
  if (fields.length <= 3 && fields.some(f => f.tagName === "TEXTAREA")) s -= 3;
  return s;
}

export type Detection = { score: number; region: Element | null; fields: number; signature: string };

/** One radio group or one checkbox group counts as one field. */
function groupKey(f: Element): Element | string {
  const i = f as HTMLInputElement;
  if (i.type === "radio" && i.name) return "radio:" + i.name;
  return f;
}

export function detect(): Detection {
  const none = { score: -Infinity, region: null, fields: 0, signature: "" };
  if (document.designMode === "on" || document.body?.isContentEditable || !document.body) return none;
  const groups = new Map<Element, Element[]>();
  const seen = new Set<Element | string>();
  let count = 0;
  for (const root of allRoots()) {
    for (const f of root.querySelectorAll(FIELD)) {
      if (++count > 300) break;
      if (f.closest("[role=radiogroup] [role=radio],[role=radiogroup] input") && f.getAttribute("role") !== "radiogroup") continue;
      const key = groupKey(f);
      if (seen.has(key) || !visible(f) || (f as HTMLInputElement).disabled || (f as HTMLInputElement).readOnly) continue;
      seen.add(key);
      const region = regionOf(f);
      groups.set(region, [...(groups.get(region) ?? []), f]);
    }
  }
  const ctx = location.pathname + " " + document.title;
  // Builder pages (Google Forms, Typeform…) are forms by definition; wizard steps there often hold a single question.
  const minFields = BUILDER.test(location.href) ? 1 : 3;
  let best: Detection = none;
  for (const [region, fields] of groups) {
    if (fields.length < minFields) continue;
    if (region.querySelector(EDITOR) || closestDeep(region, "[role=log]")) continue;
    const passwords = region.querySelectorAll("input[type=password]").length;
    if (passwords && passwords * 2 >= fields.length + passwords) continue;
    const score = scoreRegion(region, fields, ctx);
    if (score > best.score) {
      best = { score, region, fields: fields.length, signature: location.pathname + "|" + fields.map(labelOf).join("|") };
    }
  }
  if (best.score === -Infinity) return none;
  // Checkout pages never get the button, even if a non-payment region scores well.
  if (/\/(checkout|payment|cart)\b/i.test(location.pathname) && document.querySelector('[autocomplete^="cc-"]')) return none;
  return best;
}
