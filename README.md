# formform

どんなフォームも、ワンクリックで。開いているタブのフォームを、自分のコンテキスト (Markdown、または社内サーバーに取り込んだ Google Drive / Slack / Notion / ファイル) から高速で自動入力する Chrome 拡張機能。
[jev-ultrafast](jev-ultrafast/) (Browser Use × TypeSafe) のループを TypeScript / MV3 に移植しています。仕様は [docs/SPEC.md](docs/SPEC.md)。

## 仕組み

```text
Fill form
  ├─ snapshot      content script がフォーム項目を索引付け (closed Shadow DOM も横断)
  ├─ 検索          (サーバー設定時) 空欄のラベルで社内サーバーを検索し、該当箇所を Markdown の後ろに足す
  ├─ Bulk Fill     text model 1 回で、空の項目すべての値を JSON で返す → 順に入力
  │                (連動 select などで新しい選択肢が出たら、もう 1 回だけ)
  ├─ Jev ループ     コンボボックス・独自ドロップダウンだけ、TypeSafe Jev が operation + target を 1 リクエストで選ぶ
  ├─ 検証           必須の空欄とエラー表示を数え、赤枠で示す (DONE を信用しない)
  └─ Auto Submit   (オン時) 空欄 0 なら 1.5 秒のカウントダウン後に送信/次へ → 次の手順も続けて入力
```

モデルが返せるのは、観測した項目のインデックス・選択肢 ID・入力する文字列だけです。セレクタやコードは出させません。
入力は `chrome.debugger` (CDP) の trusted な `Input.insertText` / マウスイベントで、Fill の間だけアタッチします。

## ビルドとインストール

```bash
npm install
npm run build          # extension/dist に出力
npm test               # 単体テスト (外部 API は呼ばない)
npm run typecheck
```

Chrome で `chrome://extensions` → デベロッパーモード → 「パッケージ化されていない拡張機能を読み込む」→ `extension/dist` を選択。

## 設定

拡張機能アイコン → **設定 >**。項目は jev-ultrafast の `.env` と同じです (`.env` ファイルを選ぶと一括で読み込めます)。

| 項目 | 用途 |
|---|---|
| `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | Decision model (Jev)。コンボボックスなどの操作を選ぶ |
| `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_REASONING` | Text model (OpenAI 互換: OpenRouter / OpenAI / Ollama / vLLM)。入力する値を作る |

キーは `chrome.storage.local` にだけ保存され、service worker から設定したプロバイダにだけ送られます。
**コンテキスト >** で Markdown をアップロードします (最大 64 KB)。

## Markdown 以外のコンテキスト (社内サーバー)

機密保持のために文書を社外のサービスに置けない組織向けに、Google Drive / Slack / Notion / ファイル (PDF, Word, Excel…) は、自社で動かすサーバーに取り込みます。サーバーは [Onyx](https://github.com/onyx-dot-app/onyx) (MIT の Community Edition) に検索 API を足したもので、`server/` にあります。検索はサーバー上の埋め込みモデルで行い、LLM は呼びません。

```bash
cd server && ./up.sh        # 8 GB のマシンで試す場合: FORMFORM_SMALL=1 ./up.sh  →  http://localhost:3080
```

起動、アカウントとアクセストークンの作成、接続元の追加 (File の手順と、Google Drive / Slack / Notion で管理者が行う設定)、社内ネットワークでの公開、どのデータがどこへ行くか、アップグレードと削除は [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md) にまとめています。

拡張機能では **コンテキスト > 接続** に次の 2 つを入れます。「保存して確認」を押すと、サーバーの接続元が状態と文書数つきで表示されます。

| 項目 | 用途 |
|---|---|
| `FORMFORM_SERVER_URL` | サーバーの URL (例: `http://localhost:3080`) |
| `FORMFORM_SERVER_API_KEY` | サーバーで作ったアクセストークン (検索の権限だけにしたもの) |

サーバーを設定しなければ、これまでどおり Markdown だけで動きます。両方あるときは、Markdown の後ろに、サーバーから読み込んだ箇所 (1 ページあたり最大 12,000 文字) を足してモデルに渡します。

### 確認した結果 (2026-11-11, Onyx v5.1.1, `qwen/qwen3.8-27b:nitro`)

架空の会社の文書 25 件 (PDF 2・XLSX 1・DOCX 2・Markdown 20) を File コネクタで取り込み、[E · 取引先登録](extension/fixtures/e-ja-vendor.html) (17 項目) を、Playwright の Chromium に読み込んだ拡張機能で入力しました。判定には、フォームの最終的な値を使っています。記録は [docs/evidence/onyx-e2e/](docs/evidence/onyx-e2e)。

| 条件 | 結果 | 時間 | モデル呼び出し |
|---|---|---|---|
| サーバーのみ (Markdown なし) | 文書にある 16 項目がすべて正しい (PDF から 8、XLSX から 6、DOCX から 2)。文書にない携帯電話番号は空のまま赤枠 | 2.6 秒 | 1 |
| Markdown + サーバー | 17/17 項目が正しい (携帯電話は Markdown、残りはサーバー) | 1.9 秒 | 1 |
| Markdown のみ | Markdown にある 3 項目だけを入力。サーバーへの通信なし | 1.4 秒 | 1 |

Google Drive / Slack / Notion は、外部アカウントが必要なため実際の接続は確認していません。サーバーでコネクタが使える状態になっていることと、管理者の設定手順の文書化までです。

## テスト用フォーム

```bash
cd extension/fixtures && python3 -m http.server 8791 --bind 127.0.0.1
```

| ケース | 難しいところ | コンテキスト |
|---|---|---|
| [A · 日本語イベント申込](extension/fixtures/a-ja-event.html) | `<form>` なし、表のセルにだけあるラベル、郵便番号・電話・姓名・フリガナの分割入力、ARIA オートコンプリートの都道府県 (候補をクリックしないと確定しない)、画面外のハニーポット、ユーザーが先に選んだセッション、コンテキストにない必須項目 (生年月日) | [a-minato.md](extension/fixtures/contexts/a-minato.md) |
| [B · 繁體中文の論壇報名](extension/fixtures/b-zh-shadow.html) | **closed** Shadow DOM、1.5 秒後に遅延描画、ARIA の radio と checkbox、縣市 → 區 の連動 select、メール確認欄、電子報は購読しない | [b-obsidian.md](extension/fixtures/contexts/b-obsidian.md) |
| [D · 拡張機能の iframe 入り](extension/fixtures/d-ext-iframe.html) | C と同じウィザードに、別の拡張機能の `chrome-extension://` iframe を追加したもの。このページでは `chrome.debugger.attach` が失敗するので、合成イベントで入力する経路に切り替わるかを確かめる | [c-harbor.md](extension/fixtures/contexts/c-harbor.md) |
| [E · 取引先登録](extension/fixtures/e-ja-vendor.html) | コンテキストが Markdown ではなく、社内サーバーの PDF / XLSX / DOCX にある。紛らわしい文書 (営業所の住所、役員名、社員の給与口座) が検索結果に混ざる。文書にない必須項目 (携帯電話番号) | [server/sample-docs/](server/sample-docs) |
| [C · 英語の SPA ウィザード](extension/fixtures/c-en-wizard.html) | 2 ステップの SPA (再描画で DOM が入れ替わる)、フォーム外に描画される独自リストボックス (スクロールが必要な選択肢)、国に連動する State、contenteditable、date、ARIA radiogroup のチップ、Auto Submit で最後まで送信 | [c-harbor.md](extension/fixtures/contexts/c-harbor.md) |

### 実機 GUI テストの結果 (2026-11-11, macOS の Chrome, `qwen/qwen3.8-27b:nitro` + `jev-latest`)

拡張機能を実際にインストールし、Floating ボタンをクリックして実行しました。結果の確認には、フォームが送信したデータ (`window.__submitted`) を使っています。

| ケース | 結果 | 時間 | モデル呼び出し |
|---|---|---|---|
| A (Auto Submit オフ) | コンテキストにある項目はすべて正しい。手で選んだセッションはそのまま、ハニーポットと質問欄は空、都道府県は候補クリックで確定。生年月日だけ赤枠で「1 項目は手入力が必要です」 | 2.7 秒 | 5 (Bulk 1 + Jev 4) |
| A (Auto Submit オン) | 同上。未入力が残るので送信しない | 3.4 秒 | 5 |
| B (Auto Submit オフ) | 15/15 項目が正しい。Bulk だけで完了 | 2.5 秒 | 2 |
| B (Auto Submit オン) | 入力後に自動送信して「報名成功」 | 5.7 秒 (カウントダウン 1.5 秒含む) | 2 |
| D (アタッチ失敗) | アタッチが失敗しても止まらず、合成イベントで Step 1 の全項目を入力 (独自ドロップダウンと連動 select を含む) | 2.5〜9.1 秒 | 5 |
| C (Auto Submit オン) | 2 ステップ 14/14 項目が正しく、自動送信して「Application received」 | 7.1〜8.2 秒 (カウントダウン 2 回、デモの通信待ち 0.8 秒含む) | 6 |

テストで見つけて直した不具合: closed Shadow DOM の遅延描画を検知できない、`type=button` の独自ドロップダウンを項目として拾わない、リスト内でスクロールが必要な選択肢をクリックできない、表のセルにある「必須」を見落とす、コンボボックスに入力しただけで DONE を選ぶ、まれに Bulk の応答が空になる (1 回だけ再試行)。

### 既知の制限
- ページに別の拡張機能の iframe があると、Chrome が `chrome.debugger` のアタッチを拒否します (`Cannot access a chrome-extension:// URL of different extension`)。その場合は content script からの合成イベントで入力します。`isTrusted` を確認するサイトでは、この経路での入力が効かないことがあります。
- 社内サーバーは「自社」がどの会社かを知りません。取り込んだ文書に複数の会社の概要があると、別の会社の値を入力する可能性があります (Markdown に自社名を書くと区別しやすくなります)。
- Google Forms などのフォームビルダーでは、質問が 1 つだけのページでもボタンを出します。それ以外のサイトでは、入力項目が 3 つ以上必要です。
- 値の書式はモデルの出力しだいでぶれます (例: 電話番号の括弧の有無、B の番地欄に「內湖區」が重複)。
- クロスオリジン iframe 内では、クリック系の部品は合成イベントで操作します。
- popup の GUI テストは、Claude in Chrome が `chrome-extension://` を開けないため、CDP (Browser Harness) で実際の座標クリックとファイル選択を行いました。言語の `<select>` だけは、macOS のネイティブポップアップを操作できないため、値の設定と `change` イベントで切り替えています。
