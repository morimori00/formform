<p align="center"><img src="docs/hero.gif" alt="A divine hand filling in a tax refund form" width="420"></p>

# formform

Fill any form in one click. formform is a Chrome extension that fills the form in your open tab from your own context: a Markdown file, or Google Drive / Slack / Notion / files ingested into a server you run in-house.
It ports the [jev-ultrafast](jev-ultrafast/) loop (Browser Use × TypeSafe) to TypeScript / MV3. The spec is in [docs/SPEC.md](docs/SPEC.md) (Japanese).

## How it works

```text
Fill form
  ├─ snapshot      the content script indexes the form's fields (crossing closed shadow DOM)
  ├─ retrieval     (when a server is set) search the in-house server with the empty fields' labels
  │                and append the matching passages after the Markdown
  ├─ Bulk Fill     one text-model call returns values for every empty field as JSON → typed in order
  │                (one more call if dependent selects reveal new options)
  ├─ Jev loop      only for comboboxes and custom dropdowns: TypeSafe Jev picks operation + target in one request
  ├─ verify        count empty required fields and visible errors, outline them in red (DONE is never trusted)
  └─ Auto Submit   (when on) if nothing is missing, submit / go next after a 1.5 s countdown, then keep filling
```

The models can only return an observed field index, an option id, or the text to type. They never emit selectors or code.
Input goes through `chrome.debugger` (CDP) as trusted `Input.insertText` and mouse events; the debugger is attached only while a fill runs.

## Build and install

```bash
npm install
npm run build          # outputs to extension/dist
npm test               # unit tests (no external API calls)
npm run typecheck
```

In Chrome: `chrome://extensions` → Developer mode → **Load unpacked** → choose `extension/dist`.

## Settings

Extension icon → **Settings >**. The fields match jev-ultrafast's `.env` (choose a `.env` file to import them all at once).

| Field | Purpose |
|---|---|
| `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | Decision model (Jev). Chooses the actions for comboboxes and similar widgets |
| `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_REASONING` | Text model (OpenAI-compatible: OpenRouter / OpenAI / Ollama / vLLM). Produces the values to type |

Keys are stored only in `chrome.storage.local` and sent only from the service worker to the providers you set.
Upload your Markdown under **Context >** (up to 64 KB).

## Context beyond Markdown (in-house server)

For organisations that cannot put documents on outside services, Google Drive / Slack / Notion / files (PDF, Word, Excel…) are ingested into a server you run yourself. The server is [Onyx](https://github.com/onyx-dot-app/onyx) (the MIT Community Edition) plus a retrieval API, and lives in `server/`. Search runs on the server's own embedding model and calls no LLM.

```bash
cd server && ./up.sh        # to try it on an 8 GB machine: FORMFORM_SMALL=1 ./up.sh  →  http://localhost:3080
```

[docs/SELF_HOSTING.md](docs/SELF_HOSTING.md) (Japanese) covers launch, creating the account and access token, adding sources (the File walkthrough, and what an admin sets up for Google Drive / Slack / Notion), exposing it on an intranet, which data goes where, upgrading and removal.

In the extension, enter these two under **Context > Connections**. **Save and check** lists the server's sources with their status and document count.

| Field | Purpose |
|---|---|
| `FORMFORM_SERVER_URL` | The server's URL (e.g. `http://localhost:3080`) |
| `FORMFORM_SERVER_API_KEY` | An access token created on the server, limited to search |

Without a server, formform works on Markdown alone, as before. With both, the passages read from the server (up to 12,000 characters per page) are appended after the Markdown before it goes to the model.

### Verified results (2026-11-11, Onyx v5.1.1, `qwen/qwen3.8-27b:nitro`)

25 documents of a fictional company (2 PDF, 1 XLSX, 2 DOCX, 20 Markdown) were ingested with the File connector, and [E · vendor registration](extension/fixtures/e-ja-vendor.html) (17 fields) was filled by the extension loaded into Playwright's Chromium. Results are judged from the form's final values. Records are in [docs/evidence/onyx-e2e/](docs/evidence/onyx-e2e).

| Condition | Result | Time | Model calls |
|---|---|---|---|
| Server only (no Markdown) | All 16 fields present in the documents are correct (8 from the PDF, 6 from the XLSX, 2 from the DOCX). The mobile number, absent from the documents, stays empty and is outlined in red | 2.6 s | 1 |
| Markdown + server | 17/17 fields correct (mobile number from the Markdown, the rest from the server) | 1.9 s | 1 |
| Markdown only | Fills only the 3 fields the Markdown has. No request to the server | 1.4 s | 1 |

Google Drive / Slack / Notion need outside accounts, so a real connection was not tested. What is confirmed is that the connectors are available on the server, and the admin setup steps are documented.

## Test forms

```bash
cd extension/fixtures && python3 -m http.server 8791 --bind 127.0.0.1
```

| Case | What makes it hard | Context |
|---|---|---|
| [A · Japanese event application](extension/fixtures/a-ja-event.html) | No `<form>`, labels only in table cells, split inputs (postal code, phone, name, reading), an ARIA autocomplete for the prefecture (not committed until a suggestion is clicked), an off-screen honeypot, a session the user picked beforehand, a required field missing from the context (birthday) | [a-minato.md](extension/fixtures/contexts/a-minato.md) |
| [B · Traditional Chinese forum sign-up](extension/fixtures/b-zh-shadow.html) | **Closed** shadow DOM, rendered 1.5 s late, ARIA radios and checkboxes, a dependent city → district select, an email confirmation field, a newsletter that must stay unsubscribed | [b-obsidian.md](extension/fixtures/contexts/b-obsidian.md) |
| [C · English SPA wizard](extension/fixtures/c-en-wizard.html) | A two-step SPA (re-rendering replaces the DOM), a custom listbox rendered outside the form (with options that need scrolling), a State that depends on the country, contenteditable, a date, ARIA radiogroup chips, Auto Submit through to the end | [c-harbor.md](extension/fixtures/contexts/c-harbor.md) |
| [D · With another extension's iframe](extension/fixtures/d-ext-iframe.html) | The same wizard as C plus another extension's `chrome-extension://` iframe. `chrome.debugger.attach` fails on this page, so it checks that input falls back to synthetic events | [c-harbor.md](extension/fixtures/contexts/c-harbor.md) |
| [E · Vendor registration](extension/fixtures/e-ja-vendor.html) | The context is not Markdown but PDF / XLSX / DOCX on the in-house server. Look-alike documents (branch addresses, officer names, employee payroll accounts) are mixed into the search results. A required field missing from the documents (mobile number) | [server/sample-docs/](server/sample-docs) |

### GUI test results on a real browser (2026-11-11, Chrome on macOS, `qwen/qwen3.8-27b:nitro` + `jev-latest`)

The extension was installed for real and run by clicking the floating button. Results are checked against the data each form submitted (`window.__submitted`).

| Case | Result | Time | Model calls |
|---|---|---|---|
| A (Auto Submit off) | Every field present in the context is correct. The hand-picked session is untouched, the honeypot and the question box stay empty, and the prefecture is committed by clicking its suggestion. Only the birthday is outlined in red, with "1 field needs you" | 2.7 s | 5 (Bulk 1 + Jev 4) |
| A (Auto Submit on) | Same. It does not submit because a field is still missing | 3.4 s | 5 |
| B (Auto Submit off) | 15/15 fields correct. Bulk alone completes it | 2.5 s | 2 |
| B (Auto Submit on) | Fills, then submits automatically and reaches the success page | 5.7 s (including the 1.5 s countdown) | 2 |
| C (Auto Submit on) | 14/14 fields correct across both steps, submitted automatically, ends on "Application received" | 7.1–8.2 s (including two countdowns and the demo's 0.8 s network wait) | 6 |
| D (attach fails) | Does not stop when attaching fails; fills every field of step 1 with synthetic events (including the custom dropdown and the dependent select) | 2.5–9.1 s | 5 |

Bugs found and fixed during testing: a lazily rendered form inside closed shadow DOM was not detected; custom dropdowns with `type=button` were not picked up as fields; options that need scrolling inside a list could not be clicked; a "required" marker that only sits in a table cell was missed; DONE was chosen after typing into a combobox without clicking a suggestion; the Bulk answer is occasionally empty (retried once).

### Known limitations
- When a page contains another extension's iframe, Chrome refuses to attach `chrome.debugger` (`Cannot access a chrome-extension:// URL of different extension`). formform then types with synthetic events from the content script. On sites that check `isTrusted`, input through this path may not take effect.
- The in-house server does not know which company is "yours". If the ingested documents contain several companies' profiles, formform may enter another company's values (writing your company name in the Markdown helps).
- On form builders such as Google Forms, the button appears even on a page with a single question. On other sites a page needs at least three fields.
- Value formats vary with the model's output (e.g. phone numbers with or without parentheses; in B the district is repeated in the street field).
- Inside cross-origin iframes, click-type widgets are driven with synthetic events.
- The popup GUI test used CDP (Browser Harness) with real coordinate clicks and file choosers, because Claude in Chrome cannot open `chrome-extension://` pages. The language `<select>` alone was switched by setting its value and firing `change`, since macOS's native popup cannot be driven.
