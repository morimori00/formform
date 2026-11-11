// Shapes exchanged between the content script and the service worker.

export type Action = {
  id: string;
  node: number;
  kind: "fill" | "click" | "select" | "scroll" | "wait";
  role?: string;
  label: string;
  value?: string;
  current_value?: string;
  checked?: string;
  selected?: string;
  expanded?: string;
  delta?: number;
};

export type Widget = "text" | "date" | "select" | "choice" | "check" | "custom";

export type Field = {
  node: number;
  widget: Widget;
  label: string;
  hint: string;
  type: string;
  autocomplete?: string;
  name?: string;
  required: boolean;
  value: string;
  filled: boolean;
  part?: string;
  /** select: option value; choice: node of the radio to click. */
  options?: { id: string; label: string }[];
  native: boolean;
};

export type Snapshot = {
  url: string;
  title: string;
  text: string;
  formText: string;
  top: boolean;
  actions: Action[];
  fields: Field[];
  guards: Record<string, string>;
  fingerprint: string;
};

export type ContentRequest =
  | { type: "snapshot" }
  | { type: "detect" }
  | { type: "guard"; node: number }
  | { type: "focusText"; node: number }
  | { type: "point"; node: number }
  | { type: "setValue"; node: number; value: string }
  | { type: "domClick"; node: number }
  | { type: "blur"; node: number }
  | { type: "scroll"; delta: number }
  | { type: "settle"; node?: number; fill?: boolean }
  | { type: "verify" }
  | { type: "submitButton" }
  | { type: "countdown"; ms: number }
  | { type: "fab"; state: FabState; text?: string; progress?: string }
  | { type: "showFab"; show: boolean };

export type FabState = "idle" | "filling" | "done" | "warn" | "error" | "countdown";

export type BackgroundRequest =
  | { type: "fill"; tabId?: number }
  | { type: "detected"; score: number }
  | { type: "status"; tabId: number }
  | { type: "openPopup" }
  | { type: "consent" }
  | { type: "testConnection" };
