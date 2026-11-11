// Floating "Fill form" button. Closed shadow root so page CSS cannot reach it and the snapshot skips it.
import { translator } from "../shared/i18n";
import type { FabState } from "../shared/types";
import { getSettings, saveSettings } from "../shared/storage";
import { UI_TAG } from "./dom";

const CSS = `
:host{all:initial;position:fixed;top:16px;right:16px;z-index:2147483647;font:700 14px/1.25 Inter,Arial,Helvetica,sans-serif;color:#fff}
.bar{position:relative;display:flex;align-items:stretch;background:#000;border:1px solid #5e5e5e;border-radius:2px;overflow:hidden}
.bar:before{content:"";position:absolute;top:0;left:0;width:8px;height:8px;background:#76b900}
.go{display:flex;align-items:center;gap:8px;margin:6px 0 6px 12px;padding:0 14px 0 8px;height:32px;border:0;border-radius:2px;
  background:#76b900;color:#000;font:inherit;cursor:pointer;white-space:nowrap}
.go:hover{background:#5a8d00}.go:disabled{cursor:default;background:#76b900}
.go img{width:20px;height:20px;border-radius:1px;display:block}
.msg{display:flex;align-items:center;padding:0 12px;color:#fff;font-weight:400;max-width:260px}
.msg[hidden]{display:none}
.x{width:32px;border:0;border-left:1px solid #5e5e5e;margin-left:8px;background:transparent;color:rgba(255,255,255,.7);font:400 18px/1 Arial;cursor:pointer}
.x:hover{color:#fff}
.menu,.panel{margin-top:4px;background:#000;border:1px solid #5e5e5e;border-radius:2px}
.menu button{display:block;width:100%;padding:10px 14px;border:0;background:transparent;color:#fff;font:400 14px/1.25 Inter,Arial,sans-serif;text-align:left;cursor:pointer}
.menu button:hover{color:#76b900}
.panel{padding:16px;max-width:300px}
.panel h2{margin:0 0 8px;font:700 16px/1.25 Inter,Arial,sans-serif}
.panel p{margin:0 0 12px;font:400 14px/1.5 Inter,Arial,sans-serif;color:rgba(255,255,255,.7)}
.panel button{height:36px;padding:0 16px;border:0;border-radius:2px;background:#76b900;color:#000;font:700 14px Inter,Arial,sans-serif;cursor:pointer}
.out{background:transparent!important;color:#fff!important;border:1px solid #fff!important;margin-left:8px}
.warn .msg{color:#ef9100}.error .msg{color:#ff6b6b}
[hidden]{display:none!important}
`;

export class Fab {
  host = document.createElement(UI_TAG);
  private root = this.host.attachShadow({ mode: "closed" });
  private go: HTMLButtonElement;
  private label: HTMLSpanElement;
  private msg: HTMLSpanElement;
  private menu: HTMLDivElement;
  private panel: HTMLDivElement;
  private wrap: HTMLDivElement;
  private dismissed = false;
  private cancelCountdown: (() => void) | null = null;
  t = translator("en");

  constructor(private onFill: () => void, private onIdle: () => void = () => {}) {
    this.host.setAttribute("data-formform-ui", "");
    this.root.innerHTML = `<style>${CSS}</style><div class="wrap"><div class="bar">
      <button class="go" part="go"><img alt="" src="${chrome.runtime.getURL("assets/fab.gif")}"><span class="label"></span></button>
      <span class="msg" hidden></span><button class="x" aria-label="close">×</button></div>
      <div class="menu" hidden><button data-a="close"></button><button data-a="site"></button></div>
      <div class="panel" hidden><h2></h2><p></p><button data-a="agree"></button></div></div>`;
    const $ = <T extends Element>(s: string) => this.root.querySelector(s) as T;
    this.wrap = $(".wrap");
    this.go = $(".go");
    this.label = $(".label");
    this.msg = $(".msg");
    this.menu = $(".menu");
    this.panel = $(".panel");
    this.go.onclick = () => this.onFill();
    $<HTMLButtonElement>(".x").onclick = () => (this.menu.hidden = !this.menu.hidden);
    this.menu.onclick = async e => {
      const a = (e.target as HTMLElement).dataset.a;
      if (a === "site") {
        const s = await getSettings();
        await saveSettings({ disabledSites: [...new Set([...s.disabledSites, location.hostname])] });
      }
      if (a === "close" || a === "site") this.dismiss();
    };
    this.panel.onclick = async e => {
      if ((e.target as HTMLElement).dataset.a !== "agree") return;
      await saveSettings({ consented: true });
      this.panel.hidden = true;
      this.onFill();
    };
  }

  async localize() {
    this.t = translator((await getSettings()).locale);
    this.label.textContent = this.t("fill");
    this.root.querySelector('[data-a="close"]')!.textContent = this.t("close");
    this.root.querySelector('[data-a="site"]')!.textContent = this.t("hideSite");
    this.root.querySelector(".panel h2")!.textContent = this.t("consentTitle");
    this.root.querySelector(".panel p")!.textContent = this.t("consentBody");
    this.root.querySelector('[data-a="agree"]')!.textContent = this.t("agree");
  }

  show(on: boolean) {
    if (on && !this.dismissed && !this.host.isConnected) {
      document.documentElement.append(this.host);
      void this.localize();
    }
    // Keep a finished result visible; the done timer hides the button afterwards if the form is gone.
    if (!on && this.host.isConnected && !this.busy && !/done|warn|error/.test(this.wrap.className)) this.host.remove();
  }

  get busy() {
    return this.go.disabled;
  }

  dismiss() {
    this.dismissed = true;
    this.host.remove();
  }

  askConsent() {
    this.panel.hidden = false;
  }

  set(state: FabState, text = "", progress = "") {
    if (!this.host.isConnected && !this.dismissed) document.documentElement.append(this.host);
    this.wrap.className = "wrap " + state;
    this.go.disabled = state === "filling" || state === "countdown";
    this.label.textContent = state === "filling" ? this.t("filling") + (progress ? " " + progress : "") : this.t("fill");
    this.msg.hidden = !text;
    this.msg.textContent = text;
    this.menu.hidden = true;
    if (state === "done") setTimeout(() => {
      if (!this.wrap.classList.contains("done")) return;
      this.set("idle");
      this.onIdle();
    }, 4000);
  }

  countdown(ms: number): Promise<boolean> {
    return new Promise(resolve => {
      this.set("countdown");
      const cancel = document.createElement("button");
      cancel.className = "go out";
      cancel.textContent = this.t("cancel");
      this.msg.after(cancel);
      const end = Date.now() + ms;
      const finish = (ok: boolean) => {
        clearInterval(timer);
        cancel.remove();
        this.cancelCountdown = null;
        resolve(ok);
      };
      const tick = () => {
        const left = Math.max(0, end - Date.now());
        this.msg.hidden = false;
        this.msg.textContent = this.t("submitting", { s: (left / 1000).toFixed(1) });
        if (!left) finish(true);
      };
      const timer = setInterval(tick, 100);
      tick();
      cancel.onclick = () => finish(false);
      this.cancelCountdown = () => finish(false);
    });
  }
}
