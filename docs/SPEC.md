# FormForm 開発仕様書 (v1)

> どんなフォームも、ワンクリックで。
> 開いているタブのフォームを、ユーザーが用意したコンテキスト (Markdown) をもとに高速で自動入力する Chrome 拡張機能。

- ステータス: Draft v1 (ハッカソン)
- ベース: [`jev-ultrafast/`](../jev-ultrafast) (Browser Use × TypeSafe の Python 実装) を TypeScript / Chrome MV3 に移植
- 対象: Chrome 120+ (デスクトップ)

---

## 1. 目的とスコープ

### 1.1 解決する課題
イベント申込、問い合わせ、資料請求、アカウント登録などで、毎回同じ会社情報や個人情報を手で入力している。FormForm は、ユーザーが一度アップロードしたコンテキストから、開いているフォームの残りの項目を数秒で埋める。

### 1.2 代表ユースケース
1. ユーザーが会社情報 (社名、住所、代表者、連絡先、LP URL など) を書いた `company.md` をアップロードしておく。
2. イベントの参加申請ページを開く。右上に **Fill form** ボタンが出る。
3. 参加したいセッションなど、自分で決めたい項目は先に手で選ぶ。
4. **Fill form** を押す。まだ空いている会社情報の項目が自動で入力される。手で入れた値は上書きしない。
5. (Auto Submit がオンなら) 送信する。または「次へ」を押し、次のページも続けて入力する。

### 1.3 v1 のスコープ

| 含む | 含まない (将来) |
|---|---|
| 全サイトでのフォーム検知と Floating ボタン | 拡張機能だけでの Google Drive / Slack / Notion への直接接続 (接続は社内サーバー経由: §7.1) |
| 単一 Markdown コンテキストのアップロードと編集 | 複数の Markdown コンテキストの切り替え |
| 社内サーバー (Onyx) に接続した Google Drive / Slack / Notion / ファイルからの検索と入力 (§7.1, [SELF_HOSTING.md](SELF_HOSTING.md)) | 接続元ごとの閲覧権限の同期 (Onyx の Enterprise Edition の機能) |
| Jev / OpenAI 互換 (OpenRouter, OpenAI, Ollama, vLLM) の BYOK 設定 | 自前のバックエンドとアカウント機能 |
| 言語切り替え (English / 日本語 / 繁體中文) | ファイルアップロード項目、CAPTCHA、決済フォーム |
| Auto Submit (複数ページ連続入力) | クロスオリジン iframe 内でのクリック操作 (§6.5) |

---

## 2. 全体アーキテクチャ

```text
┌──────────────────────── Tab (all_frames) ────────────────────────┐
│ content script                                                   │
│  ├─ detector.ts   フォーム検知スコアリング (LLM なし, <5ms)        │
│  ├─ fab.ts        Floating ボタン (Shadow DOM)                    │
│  └─ snapshot.ts   jev の snapshot.js を移植 (要素の索引付け)        │
└───────────────▲──────────────────────────────┬───────────────────┘
                │ chrome.runtime messages      │ "fill" {frameId}
┌───────────────┴──────────────────────────────▼───────────────────┐
│ service worker (background)                                      │
│  ├─ agent.ts      Fill ループ (Bulk Fill → Jev ループ → 検証)       │
│  ├─ browser.ts    chrome.debugger (CDP) で入力 / クリック          │
│  ├─ providers/    decision (Jev | OpenAI互換) / text (OpenAI互換)  │
│  └─ autosubmit.ts ページ遷移を監視して再 Fill                      │
└───────────────▲──────────────────────────────────────────────────┘
                │ chrome.storage.local
┌───────────────┴─────────────┐
│ popup (拡張アイコン)          │  設定 > / コンテキスト >
└─────────────────────────────┘
```

### 2.1 jev-ultrafast からの移植対応

| jev-ultrafast (Python) | FormForm (TypeScript) | 変更点 |
|---|---|---|
| `snapshot.js` | `content/snapshot.ts` | ほぼそのまま。フォーム領域で絞り込む `scope` 引数を追加 |
| `browser.py` `browser_harness.cdp` | `background/browser.ts` `chrome.debugger.sendCommand` | 新しいタブを作らず、**既存のタブ**にアタッチする |
| `model.py` `choose()` | `providers/decision.ts` | Jev と OpenAI 互換の 2 実装 |
| `model.py` `field_text()` | `providers/text.ts` | Bulk Fill 用の一括生成を追加 (§4.2) |
| `questions.py` | `shared/prompts.ts` | フォーム入力専用のルールに書き換え |
| `agent.py` | `background/agent.ts` | 3 フェーズ化 (§4) |
| `demo.py` + `static/` | `popup/` + `content/fab.ts` | インスペクタは開発時のデバッグパネルとして残す (任意) |

### 2.2 守る不変条件 (jev-ultrafast の AGENTS.md より継承)
- モデルが出力してよいのは、**観測した要素のインデックス**と**入力する文字列**だけ。セレクタ、座標、実行コードは決して出させない。
- ブラウザを変更する操作はリトライしない。実行を記録してから結果を観測する。
- 入力の直前に、ページの鮮度 (marker / guard) と遮蔽 (`elementFromPoint`) を再確認する。
- DONE は成功の証明ではない。最後に再スナップショットを取り、独立に検証する (§4.4)。
- ページのテキストは信頼しないデータであり、指示として扱わない。
- テストは有料 API を呼ばない。

---

## 3. UI 仕様

### 3.1 Floating ボタン (content script)
- 表示条件: 検知スコアがしきい値以上 (§5)、かつそのサイトが除外リストにない。
- 位置: 画面右上 `position: fixed; top: 16px; right: 16px; z-index: 2147483647`。
- 構成: `[GIF アイコン] Fill form [×]`
- 実装: Shadow DOM (closed) で、ページの CSS と隔離する。スナップショットの対象から除外する (`data-formform-ui` 属性)。
- 状態:

| 状態 | 表示 |
|---|---|
| idle | `Fill form` |
| filling | アイコンのアニメーション + `Filling… 3/8` |
| done | `✓ Filled 8 fields` (3 秒後に idle に戻る)。未入力の必須項目があれば `2 fields need you` |
| error | `⚠ <短いメッセージ>`。クリックで popup の設定を開く |
| no-context | `Add context first` → クリックでコンテキスト画面を開く |

- ×: このタブでは閉じる (リロードするまで)。長押しまたはメニューで「このサイトでは表示しない」を選ぶと除外リストに追加する。
- キーボード: `Alt+Shift+F` (`commands` API) でも Fill を実行できる。

### 3.2 Popup (拡張アイコンをクリック)
360×480px 程度の小さいウィンドウ。トップはメニューだけ。

```text
┌──────────────────────────────┐
│ FormForm              v0.1.0 │
├──────────────────────────────┤
│ 設定                       > │
│ コンテキスト               > │
├──────────────────────────────┤
│ このページ: フォームを検知 ✓    │
│ [ Fill form ]                │
└──────────────────────────────┘
```

**設定 >**
| 項目 | 内容 | 既定値 |
|---|---|---|
| 言語 | English / 日本語 / 繁體中文 | ブラウザの言語に合わせる (なければ English) |
| Auto Submit | オンにすると、全項目が埋まった後に送信または「次へ」を押し、次のページも続けて入力する | **オフ** |
| Decision model | jev-ultrafast の `.env` と同じ項目: `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | `jev-latest` |
| Text model | 同じく `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_REASONING`。Base URL のプリセット (OpenRouter / OpenAI / Ollama / vLLM) から選べる | `https://openrouter.ai/api/v1`, `qwen/qwen3.8-27b:nitro`, `none` |
| .env の読み込み | `.env` ファイルを選ぶか貼り付けると、上の 6 項目と、サーバーの 2 項目 (`FORMFORM_SERVER_URL`, `FORMFORM_SERVER_API_KEY`) にまとめて反映する | — |
| 接続テスト | 各モデルに最小のリクエストを 1 回送り、結果を表示する | — |
| 除外サイト | ボタンを表示しないドメインの一覧 | 空 |

**コンテキスト >**
- Markdown ファイルのアップロード (`.md` / `.txt`、最大 64KB)。ドラッグ&ドロップに対応する。
- テキストエリアでのプレビューと編集、保存、削除。
- 文字数と推定トークン数を表示する。
- **接続**: 社内サーバーの URL (`FORMFORM_SERVER_URL`) と API キー (`FORMFORM_SERVER_API_KEY`) の入力欄。「保存して確認」を押すと、サーバーに接続されている接続元 (Google Drive / Slack / Notion / ファイルなど) を、名前・種類・状態 (稼働中 / 取り込み中 / 停止中 / エラー)・文書数のカードで表示する。「接続元を管理」は、サーバーの管理画面 (`/admin/indexing-status`) を新しいタブで開く。接続元の追加と認証はサーバーの管理画面で行い、拡張機能は接続元の認証情報を持たない (§7.1)。

### 3.3 多言語化
- `chrome.i18n` はブラウザの言語に固定されて切り替えられないので、UI の文言は自前の辞書 `shared/i18n/{en,ja,zh_TW}.json` で持ち、設定で切り替える。
- manifest の name / description だけは `_locales/` を使う。
- モデルに渡すプロンプトは英語に統一する。入力する値の言語は、フォームとコンテキストに合わせる (例: 日本語フォームには日本語の住所)。

---

## 4. Fill の処理フロー

速さのために、**Bulk Fill (一括で 1 回)** と **Jev ループ (1 操作ずつ)** の 2 段構えにする。jev-ultrafast の 1 操作 1 判断ループは、普通の入力欄が 10 個あるフォームでは 10 往復かかる。普通の入力欄はまとめて 1 回で埋め、複雑な部品だけを Jev に任せる。

```text
Fill form
  │
  ├─ 0. attach   chrome.debugger.attach(tabId)  (+ Emulation.setFocusEmulationEnabled)
  ├─ 1. snapshot フォーム領域内の要素を索引付けする (§5.3 の region)
  ├─ 2. Bulk Fill      text model 1 回 → {index: value}* → 順番に入力する
  ├─ 3. Jev ループ      残りの複雑な部品 (combobox, ARIA radio, date picker…) を 1 操作ずつ
  ├─ 4. 検証            再スナップショット → 空の必須項目を数える
  ├─ 5. Auto Submit?   オンで、検証を通ったら送信または次へ → 遷移後に 1 から繰り返す
  └─ 6. detach
```

### 4.1 スナップショット
- `snapshot.js` を移植する。password / file / hidden の項目は除外する (既存の `safe()`)。さらに次のものも除外する:
  - `autocomplete` が `cc-*` の項目、カード番号らしい名前の項目 (決済情報)
  - FormForm 自身の UI (`[data-formform-ui]`)
- 各項目に、Bulk Fill の判断材料として `type`、`autocomplete`、`name`、`required`、近くの見出しやテキスト、select の選択肢、radio グループの選択肢を付ける。
- **ユーザーがすでに入力した項目** (value が空でない、checked、選択済み) には `user_filled: true` を付け、Bulk Fill の対象から外す。

### 4.2 Bulk Fill (1 リクエスト)
- 対象: `textbox` / `textarea` / `email` / `tel` / `url` / `number` / ネイティブの `select` / ネイティブの radio と checkbox のうち、未入力のもの。
- text model への入力:
  ```json
  {
    "context": "<ユーザーの Markdown 全文。サーバーを設定していれば、その後ろに検索で得た箇所 (§7.1)>",
    "page": {"title": "...", "url": "...", "text": "<見えているテキスト, 最大 6000 字>"},
    "fields": [
      {"index": "3", "label": "会社名", "type": "text", "autocomplete": "organization", "required": true},
      {"index": "7", "label": "業種", "type": "select", "options": ["7:1 IT", "7:2 製造"]}
    ]
  }
  ```
- 出力 (JSON): `{"fills": [{"index": "3", "value": "株式会社クエルマップ"}, {"index": "7", "option": "7:1"}]}`
- ルール: コンテキストに根拠がない値は作らない (その項目は省く)。select と radio は、提示した選択肢の ID だけを返してよい。
- 検証: 返ってきた index が今回の対象にあること、option が提示した選択肢にあること、value が 2000 字以下であることを確認する。満たさないものは捨てる。
- 実行: 上から順に、jev と同じ方式で入力する (`click → selectAll → Input.insertText`)。入力ごとに guard を確認し、ページが変わっていたら残りは Jev ループに回す。
- 入力するたびに Floating ボタンの進捗を更新する。

### 4.3 Jev ループ (残りの複雑な部品)
- jev-ultrafast の `choose()` → `act()` をそのまま移植する。operation と各 target head を 1 リクエストで聞く。
- goal は自動で組み立てる (サイトごとの計画やハードコードはしない):
  > Fill every remaining empty field of this form using only the user's context below. Do not change fields that already have values. Do not submit or go to the next page. {Auto Submit がオンなら: "When all fields are filled, click the submit or next button."}
  > Context: …
- 上限: 1 ページあたり 20 ステップ。3 回続けてページが変わらなければ BLOCKED (既存のロジック)。
- TYPE_TEXT の値は text model の `field_text()` で作る。stale なときのキャッシュ規則は既存と同じにする。

### 4.4 検証 (DONE を信用しない)
- 再スナップショットを取り、`required` または `aria-required` の項目のうち空のものを数える。
- 0 件なら done。1 件以上なら `N fields need you` を表示し、その項目を枠で強調する。
- 入力したすべての値をログに残す (popup の「直近の実行」で確認できる)。

### 4.5 Auto Submit
- 既定はオフ。オンのときだけ、検証で未入力が 0 件なら、Jev ループで送信または「次へ」のボタンを押す。
- 遷移の検知: `chrome.webNavigation.onCompleted` (同じタブ、同じ frame) または SPA のステップ変化 (marker の変化と detector の再スコア)。検知したら §4 を最初から再実行する。
- 安全装置:
  - 最大 10 ページまで。直前と同じフォームの fingerprint が再び現れたら止める (エラーで同じページに戻った場合)。
  - 決済、CAPTCHA、ログインのページを検知したら止めて、ユーザーに渡す。
  - 送信の直前に 1.5 秒のカウントダウンを出し、Floating ボタンでキャンセルできるようにする。
- 送信後に見えるエラー文 (`aria-invalid`、`role=alert`) を検知したら止める。

---

## 5. フォーム検知

すべてのページで動くので、LLM を使わず、素の JavaScript だけで安く判定する (1 回 5ms 未満)。**再現率より適合率を優先**する。検索欄、ログイン、メルマガ、コメント欄、チャット、決済、リッチエディタではボタンを出さない。

### 5.1 「入力できる項目」の定義
表示されていて、有効で、読み取り専用でないもの:
- `input` (hidden / submit / button / reset / image / file / search / password を除く)、`select`、`textarea`
- `role=textbox|combobox|listbox|radiogroup|checkbox|spinbutton` (`contenteditable` は除く)
- radio のグループは 1 個と数える

### 5.2 スコアリング (候補の領域ごと)

| シグナル | 点 | 上限 |
|---|---|---|
| `autocomplete` が個人や会社の情報を表す値 (`name`, `given-name`, `family-name`, `organization`, `organization-title`, `email`, `tel`, `street-address`, `address-line*`, `postal-code`, `address-level*`, `country`, `bday`) | +3 / 個 | +12 |
| label / placeholder / name / id が語彙に一致 (company / 会社名 / 公司名稱, name / 氏名 / 姓名, phone / 電話番号, address / 住所 / 地址, zip / 郵便番号 / 郵遞區號, 部署 / 部門, 役職 / 職稱, メール) | +2 / 個 | +12 |
| 入力できる項目の 3 個目以降 | +1 / 個 | +6 |
| 項目の種類が 3 種類以上 (text, select, radio, date…) | +2 | |
| 必須の印が 2 個以上 (`required`, `aria-required`, `*`, 必須, 必填) | +2 | |
| 送信系のボタン文言 (submit, register, apply, sign up, RSVP, 申し込む, 送信, 確認画面へ, 登録, 応募, 提交, 送出, 報名, 申請) | +3 | |
| URL / title / 最寄りの見出しが文脈語に一致 (contact, inquiry, registration, application, survey, お問い合わせ, 申込フォーム, エントリー, アンケート, 資料請求, 聯絡我們, 報名, 問卷, 表單) | +2 | |
| フォームビルダーの痕跡 (`docs.google.com/forms`, `forms.office.com`, `typeform.com`, `hsforms` / `.hs-form`, `jotform`, `tally.so`, `formrun`, `form-mailer`, `surveymonkey`) | +6 | |
| `role=radiogroup` / `combobox` がある (アンケートらしさ) | +1 | |
| **減点** | | |
| 領域に password がある | −6 | |
| `role=search` の中にある、または search / 検索 / 搜尋 のボタンや label がある | −6 | |
| ログイン、購読、コメントの文言 (login, sign in, subscribe, newsletter, comment, reply, ログイン, メルマガ, コメント, 登入, 訂閱, 留言) | −4 | |
| `nav` / `header` / `footer` の中にある | −3 | |
| 大きい項目が `textarea` 1 つだけで、ほかの項目が 2 個以下 | −3 | |

**しきい値: スコアが 10 以上、かつ入力できる項目が 3 個以上でボタンを出す。** 一度出したら、スコアが 6 未満になるまで消さない (再描画のたびにボタンがちらつかないように、ヒステリシスを持たせる)。

数値の根拠:
- autocomplete の付いた個人情報の項目が 3 つあれば、それだけで通る (9 点 + 項目数の点)。
- autocomplete のないフォームは、label と送信ボタンがそろって 10 点に届く (例: 3×2 + 1 + 3)。
- ログインは項目数と password の減点で落ちる。メルマガは項目数で落ちる。
- コメント欄 (名前、メール、本文) はおよそ 7 点で、"comment" の −4 で落ちる。

### 5.3 絶対に出さない条件
- `chrome://` などの特殊ページ、PDF ビューア、`designMode === 'on'`、body 全体が contenteditable。
- 領域に決済や OTP の項目がある (`autocomplete` が `cc-*` / `one-time-code`、カード番号、CVV、セキュリティコード、信用卡、卡號)。そのうえ URL が `/checkout`、`/payment`、`/cart` なら、ページ全体で出さない。
- 領域の input の半分以上が password。
- チャット UI: `role=log` / `aria-live` のメッセージ一覧の隣にある入力欄。
- リッチエディタ (`.ProseMirror`, `.ck-editor`, `.ql-editor`, `.monaco-editor`) が領域の大半を占める。
- frame 内で入力できる項目が 3 個未満。
- ユーザーがそのサイトを除外リストに入れている。

### 5.4 `<form>` タグがないときの領域の決め方
1. ドキュメントと各 shadow root で、`querySelectorAll` を 1 回ずつ実行して項目を集める。shadow root は、タグ名に `-` を含む要素から `chrome.dom.openOrClosedShadowRoot(el)` で取る (closed の root も取れる)。最大 300 項目まで。
2. 項目が `closest('form,[role=form],fieldset')` に当たれば、それを領域とする。
3. 当たらなければ祖先をたどる (shadow の境界は `getRootNode().host` で越える)。最大 8 階層までで、送信系のボタンと 3 個以上の項目を含む最初の祖先で止まる。見つからなければ、`body` / `main` の手前まで上がった祖先を使う。
4. 同じ領域の項目をまとめてスコアを付け、最高点の領域を採用する。この領域は §4.1 のスナップショットの範囲にもなる。
5. 祖先の結果は `WeakMap` にキャッシュする。DOM の読み取りは書き込みを挟まず 1 パスで行い、表示判定には `checkVisibility()` を使う (デザインを変えた radio / checkbox は親の label で判定する)。

### 5.5 再評価のタイミング (SPA とウィザード)
- 初回: `document_idle` の後、`requestIdleCallback({timeout: 1000})` で実行する。
- `MutationObserver` で `childList` と `subtree` だけを監視する。追加されたノードが項目または `iframe` を含むときだけ再スキャンの対象にする。
- デバウンス: 最後の変化から 400ms 後に実行し、どんなに変化が続いても 2 秒以内に必ず 1 回実行する。
- `navigation` の `navigate` イベント (pushState の遷移) と `hashchange` で再スキャンする。項目に最初に `focusin` したときは、強い意図のシグナルなのですぐにスキャンする。
- ウィザード: その URL で一度しきい値を超えたら、次のステップでもスコアが 6 以上ならボタンを残す。
- 打ち切り: 15 回続けてスコアが変わらなければ、領域が消えたかどうかだけを監視する。
- 予算: `performance.now()` で計り、4ms を超えたら中断して次の idle callback で続きを行う。

### 5.6 iframe での検知
- manifest で `all_frames: true`、`match_about_blank: true`、`match_origin_as_fallback: true` にする。
- 各 frame が自分のスコアを計算する。200×150px より小さい frame や、項目がない frame は報告しない。
- 子 frame は UI を描かない。`chrome.runtime.sendMessage({score, fields})` で service worker に報告する。service worker は `sender.frameId` を見て、タブごとに最高点の frame を覚え、frame 0 に `chrome.tabs.sendMessage(tabId, msg, {frameId: 0})` でボタンを出すよう伝える。
- クリックされたら、service worker が最高点の frame に Fill を送る。
- トップの frame は、`iframe[src]` がフォームビルダーに一致したら自分でビルダーの点を加える (Google Forms の埋め込みなどで、子 frame の報告を待たずにボタンを出せる)。

### 5.7 スコアラーの骨格 (TypeScript)

```ts
const FIELD = 'input:not([type=hidden],[type=submit],[type=button],[type=reset],[type=image],[type=file],[type=search],[type=password]),select,textarea,[role=textbox]:not([contenteditable]),[role=combobox],[role=listbox],[role=radiogroup],[role=spinbutton]';
const BUTTON = 'button,[type=submit],[role=button],input[type=button]';
const ID_AC = /^(name|given-name|family-name|organization(-title)?|email|tel(-national)?|street-address|address-line\d|address-level\d|postal-code|country(-name)?|bday)$/;
const ID_LEX = /company|organi[sz]ation|(first|last|full|your)\s?name|e-?mail|phone|mobile|address|zip|postal|city|job\s?title|department|会社名|企業名|氏名|お名前|フリガナ|メール|電話|住所|郵便番号|都道府県|部署|役職|公司|姓名|名稱|手機|地址|郵遞區號|職稱|部門/i;
const SUBMIT = /submit|register|apply|sign\s?up|rsvp|enrol|request|book|申し?込|送信|確認|登録|応募|エントリー|提交|送出|報名|申請|註冊/i;
const CONTEXT = /contact|inquiry|registration|application|survey|questionnaire|問い合わせ|申込|応募|エントリー|アンケート|資料請求|聯絡|報名|申請|問卷|表單/i;
const NEG = /search|log\s?in|sign\s?in|subscribe|newsletter|comment|reply|検索|ログイン|メルマガ|コメント|搜尋|登入|訂閱|留言/i;
const SENSITIVE = /^cc-|one-time-code|card.?(num|no)|cvv|cvc|security.?code|カード番号|セキュリティコード|信用卡|卡號/i;
const BUILDER = /docs\.google\.com\/forms|forms\.(office|microsoft)\.com|typeform\.com|hsforms|hs-form|hbspt|jotform|tally\.so|formrun|form-mailer|surveymonkey/i;
const REQ = /\*|必須|必填|required/i;

export function scoreRegion(root: Element, fields: Element[], pageCtx: string): number {
  let s = 0, ac = 0, lex = 0, req = 0; const kinds = new Set<string>(); let negText = '';
  if (root.querySelector('input[type=password]')) s -= 6;
  for (const f of fields) {
    const a = f.getAttribute('autocomplete') ?? '', label = labelOf(f);
    if (SENSITIVE.test(a) || SENSITIVE.test(label)) return -Infinity; // 絶対に出さない
    if (ID_AC.test(a.split(/\s+/).pop()!)) ac++;
    else if (ID_LEX.test(label)) lex++;
    if ((f as HTMLInputElement).required || f.getAttribute('aria-required') === 'true' || REQ.test(label)) req++;
    kinds.add(f.getAttribute('role') ?? (f as HTMLInputElement).type ?? f.tagName);
    negText += label + ' ';
  }
  s += Math.min(ac * 3, 12) + Math.min(lex * 2, 12) + Math.min(Math.max(fields.length - 2, 0), 6);
  if (kinds.size >= 3) s += 2;
  if (req >= 2) s += 2;
  const btnText = [...root.querySelectorAll(BUTTON)].slice(0, 10)
    .map(b => b.textContent || (b as HTMLInputElement).value || '').join(' ');
  if (SUBMIT.test(btnText)) s += 3;
  const heading = root.querySelector('h1,h2,h3,legend,[role=heading]')?.textContent ?? '';
  if (CONTEXT.test(pageCtx + ' ' + heading)) s += 2;
  if (BUILDER.test(location.href + ' ' + root.className)) s += 6;
  if (kinds.has('radiogroup') || kinds.has('combobox')) s += 1;
  if (root.closest('[role=search]') || /search|検索|搜尋/i.test(btnText)) s -= 6;
  if (NEG.test(negText + btnText + heading)) s -= 4;
  if (root.closest('nav,header,footer')) s -= 3;
  if (fields.length <= 3 && fields.some(f => f.tagName === 'TEXTAREA')) s -= 3;
  return s;
}
```
`labelOf()`、`regionOf()` (§5.4)、`bestScore()` (frame 内の最高点の領域を返す) は `content/detector.ts` に置く。

### 5.8 適合率を確かめる fixtures
`extension/fixtures/{pos,neg}/` に静的な HTML として保存し、Playwright で拡張機能を読み込んで、ボタンが出るかどうかを確かめる。全 fixture で、スキャン時間の p95 が 5ms 未満であることも確かめる。

| 出さない (`neg/`) | 出す (`pos/`) |
|---|---|
| Google 検索、Amazon の検索バーとヘッダー | Google Forms の埋め込み (トップと iframe)、Microsoft Forms |
| GitHub のログイン、Google のログイン (1 ステップに 1 項目)、password だけのステップ | Typeform (1 問ずつのウィザード: ヒステリシスの確認) |
| Substack / Medium のメルマガ欄、フッターの購読フォーム | HubSpot の問い合わせフォーム埋め込み、JotForm |
| WordPress のコメント欄 (名前、メール、Web サイト、本文) | 日本語の申込フォーム (会社名、氏名、フリガナ、電話番号、必須、確認画面へ) |
| Slack / Discord / ChatGPT の入力欄 | 台湾の報名表 (公司名稱、姓名、提交) |
| Stripe Checkout、Shopify の決済 (カード項目あり) | connpass / Peatix / Eventbrite の参加登録 |
| Notion、Google Docs、CKEditor のデモ | Greenhouse / Lever の求人応募 |
| Cookie 同意のダイアログ、小さい広告の iframe | `<form>` なしの React / MUI フォーム、Shadow DOM の Lit / Shoelace フォーム、2 秒後に描画されるフォーム、SPA で遷移した先の問い合わせページ |

**やらないこと:** ML による分類、サイトごとのルール、ラベルと入力欄の位置関係による照合。位置関係の照合は、`<label>` のない日本語サイトで見逃しが多いとわかったら追加する。

---

## 6. モデルプロバイダ

### 6.1 役割分担と設定項目 (jev-ultrafast の `.env` と同じ)
| 役割 | 使うフェーズ | 設定項目 |
|---|---|---|
| **Decision model** (Jev, TypeSafe) | Jev ループ (operation + target の選択) | `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` |
| **Text model** (OpenAI 互換) | Bulk Fill (一括で値を作る)、TYPE_TEXT (1 項目の値を作る) | `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_REASONING` |

### 6.2 Decision: Jev (TypeSafe)
- `POST https://api.typesafe.ai/v1/systemone`。リクエストは jev-ultrafast の `choose()` と同じ形にする。
- 応答は `validate_choice()` を移植して検証する (choice が候補に含まれる、確率の合計が 1 など)。

### 6.3 Text: OpenAI 互換
- 既定: OpenRouter `qwen/qwen3.8-27b:nitro` で `reasoning: {enabled: false}`。
- プリセット:

| Preset | base URL | 備考 |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | |
| OpenAI | `https://api.openai.com/v1` | |
| Ollama | `http://localhost:11434/v1` | `OLLAMA_ORIGINS=chrome-extension://*` が必要 (設定画面に案内を出す) |
| vLLM | `http://localhost:8000/v1` | |

### 6.4 通信
- すべて service worker から `fetch` する。content script がすでに全サイトで動くので、`host_permissions: ["<all_urls>"]` で統一する (localhost の Ollama / vLLM も含む)。
- 429 / 503 / 529 のときだけ、最大 2 回まで指数バックオフでリトライする (モデル呼び出しはブラウザを変更しないので許可される)。
- タイムアウトは 25 秒。

### 6.5 iframe
- 検知とボタンを出す frame の決め方は §5.6 のとおり。Fill は最高点の frame に送る。
- 同一オリジンの iframe: トップから要素の座標を補正して、CDP で操作する。
- クロスオリジンの iframe (Google Forms の埋め込みなど): v1 では、その frame の content script から `focus()` を呼び、CDP の `Input.insertText` で入力する (座標が要らない)。select はネイティブの `change` イベントで設定する。クリック系の部品は v1 では対象外とし、「新しいタブで開く」を提案する。

---

## 7. データとストレージ

`chrome.storage.local` (端末ローカル。sync は使わない: API キーとコンテキストを Google アカウントに同期させないため)

```ts
type Settings = {
  locale: "en" | "ja" | "zh_TW";
  autoSubmit: boolean;
  // jev-ultrafast の .env と同じキー名
  env: { TYPESAFE_API_KEY: string; TYPESAFE_MODEL: string; TEXT_MODEL_API_KEY: string;
         TEXT_MODEL_BASE_URL: string; TEXT_MODEL: string; TEXT_MODEL_REASONING: "" | "none";
         FORMFORM_SERVER_URL: string; FORMFORM_SERVER_API_KEY: string };
  disabledSites: string[];
};
type Source = { id: string; type: "markdown"; name: string; content: string; updatedAt: number };
type RunLog = { url: string; startedAt: number; fills: { label: string; value: string; via: "bulk" | "jev" }[];
                modelCalls: number; elapsedMs: number; result: "done" | "partial" | "blocked" | "error" };
```

- Markdown のコンテキストは、`sources` のうち `type: "markdown"` の 1 件をそのままプロンプトに入れる。
- Markdown 以外の接続元は拡張機能に保存しない。Fill のたびに社内サーバーから必要な箇所だけを読み込む (§7.1)。
- RunLog は直近 20 件だけ残す。

### 7.1 社内サーバーからのコンテキスト取得

機密保持のため、文書を社外のサービスにアップロードできない企業を想定する。Google Drive / Slack / Notion / ファイルの取り込みと検索は、社内で動かす Onyx (MIT の Community Edition) に任せる。構成と手順は [SELF_HOSTING.md](SELF_HOSTING.md)。

- **サーバー**: Onyx v5.1.1 の公式イメージをそのまま使い、`server/formform_onyx/app.py` で API を 2 つ足す。
  - `POST /api/formform/context` `{queries: string[≤8], limit, max_chars}` → `{passages: [{title, source, link, content}]}`。Onyx のハイブリッド検索 (ローカルの埋め込みモデル + キーワード) をクエリごとに実行し、順位の高い順に 1 件ずつ交互に取り、重複を除いて `max_chars` 以内で返す。LLM は呼ばない。
  - `GET /api/formform/sources` → `[{id, name, source, status, docs, last_indexed}]`。
  - どちらも Bearer の API キーで認証し、そのキーのユーザーが読める文書だけを対象にする。
- **拡張機能** (`background/retrieval.ts`、service worker からだけ呼ぶ):
  1. ページごとに 1 回、Bulk Fill の前に、空欄のラベルから検索クエリを作る (`buildQueries`)。「必須」などの印を除き、重複をまとめ、数個ずつつなげて最大 4 クエリにする。
  2. サーバーから該当箇所を受け取る (最大 12,000 文字、タイムアウト 10 秒)。
  3. `Markdown + "# Retrieved from connected sources" + 該当箇所` を、これまでと同じ `context` としてプロンプトに渡す (`mergeContext`)。プロンプトと action space は変えない。
- サーバーを設定していなければ、これまでどおり Markdown だけで動く。サーバーに接続できないときは、Markdown があれば Markdown だけで続け (実行ログに理由を残す)、なければエラーを表示して何も入力しない。

---

## 8. セキュリティとプライバシー

- **ローカルで完結する部分**: 検知はすべて端末内で行い、外部には何も送らない。
- **外部に送る部分**: Fill を押したときだけ、コンテキスト (サーバーから読み込んだ箇所を含む) とページのテキストを、ユーザーが設定したプロバイダに送る。初回の Fill の前に、何を送るかの同意ダイアログを出す。
- **社内サーバーに送る部分**: Fill を押したときに、空欄のラベルから作った検索クエリを送る。サーバーは社外のモデルを呼ばない。どのデータがどこへ行くかの一覧は [SELF_HOSTING.md §6](SELF_HOSTING.md)。
- API キー: BYOK。`chrome.storage.local` にだけ保存し、設定したプロバイダ以外には送らない。content script には渡さない (service worker だけが読む)。
  - ※ jev-ultrafast の「認証情報はサーバー側に置く」という原則は、BYOK の拡張機能では「service worker の外に出さない」と読み替える。配布版で共有キーを使う場合は、プロキシサーバーを別に用意する。
- プロンプトインジェクション対策: ページのテキストは untrusted と明示する。モデルは観測したインデックスと値しか出せず、値は入力欄にだけ入る。
- 入力しない項目: password、file、`cc-*`、CVC、マイナンバーや SSN らしい項目 (ラベルで判定)。
- `chrome.debugger` を使うと Chrome がバナーを表示する。Fill の間だけアタッチし、終わったらすぐ detach する。

---

## 9. 権限 (manifest.json)

```json
{
  "manifest_version": 3,
  "permissions": ["storage", "debugger", "scripting", "activeTab", "webNavigation"],
  "host_permissions": ["<all_urls>"],
  "content_scripts": [{ "matches": ["<all_urls>"], "js": ["content.js"], "all_frames": true, "match_about_blank": true, "match_origin_as_fallback": true, "run_at": "document_idle" }],
  "background": { "service_worker": "background.js", "type": "module" },
  "action": { "default_popup": "popup.html" },
  "commands": { "fill-form": { "suggested_key": { "default": "Alt+Shift+F" } } }
}
```

---

## 10. 技術スタックとリポジトリ構成

- TypeScript + esbuild (ビルドスクリプト 1 本)。UI フレームワークは使わない (popup は小さいので素の DOM で書く)。
- テスト: vitest + jsdom (detector のスコア、action space、応答の検証、Bulk Fill のパーサ)。Playwright で拡張機能を読み込み、`fixtures/*.html` で E2E を行う (モデルはモックにする)。

```text
formform/
├── jev-ultrafast/          移植元 (参照用。変更しない)
├── docs/SPEC.md            この文書
├── extension/
│   ├── manifest.json
│   ├── _locales/{en,ja,zh_TW}/messages.json
│   ├── assets/icon.gif, icon-*.png
│   ├── src/
│   │   ├── background/  agent.ts browser.ts autosubmit.ts retrieval.ts
│   │   ├── content/     detector.ts fab.ts snapshot.ts index.ts
│   │   ├── popup/       popup.html popup.ts settings.ts context.ts
│   │   ├── providers/   decision.ts text.ts http.ts
│   │   └── shared/      prompts.ts storage.ts i18n/ messages.ts types.ts
│   ├── fixtures/        検知と入力のテスト用 HTML
│   └── test/
├── server/                 社内サーバー: Onyx に重ねる compose、env のひな形、formform_onyx/ (追加 API)、sample-docs/
├── package.json
└── README.md
```

---

## 11. 性能目標

| 指標 | 目標 |
|---|---|
| 検知のコスト | 1 回 5ms 未満、メインスレッドを 16ms 以上止めない |
| 普通の入力欄 10 個のフォーム | Fill を押してから完了まで **3 秒以内** (モデル呼び出し 1 回) |
| 複雑な部品を含むフォーム | 複雑な部品 1 つあたり 1 秒前後 |
| モデル呼び出し | Bulk 1 回 + 複雑な部品の数 × 1〜2 回 |

---

## 12. 受け入れ基準 (デモ前のチェック)

1. `fixtures/event-signup.html` (日本語、項目 12 個、セッションの select を手で選んだ状態) で Fill を押すと、手で選んだ値はそのままに、ほかの全項目が 3 秒以内に埋まる。
2. Google 検索、ログインページ、メルマガの 1 行入力欄では、Floating ボタンが出ない。
3. 言語を切り替えると、popup と Floating ボタンの文言がすぐに変わる。
4. Auto Submit がオンのとき、2 ページあるウィザードのフォームを最後まで入力して送信する。オフのときは送信しない。
5. コンテキストにない項目 (例: 生年月日) は空のまま残り、`1 field needs you` と表示される。
6. API キーが未設定、または 404 のとき、ボタンにエラーを表示し、ページには何も入力しない。
7. `npm test` は外部 API を呼ばずに通る。

---

## 13. マイルストーン (ハッカソン)

| # | 内容 | 完了の条件 |
|---|---|---|
| M1 | 雛形: manifest、esbuild、popup のメニュー、storage、i18n | 拡張機能が読み込めて、設定が保存できる |
| M2 | 検知 + Floating ボタン | fixtures で表示と非表示が正しく切り替わる |
| M3 | snapshot / browser (chrome.debugger) の移植 | popup から 1 項目を入力できる |
| M4 | Bulk Fill + 検証 | 受け入れ基準 1 と 5 |
| M5 | Jev ループの移植 (Decision の 2 実装) | combobox を含む fixture を入力できる |
| M6 | Auto Submit | 受け入れ基準 4 |
| M7 | 仕上げ: 接続 UI、GIF アイコン、デモ動画 | デモができる |
| M8 | 社内サーバー (Onyx) からのコンテキスト取得 (§7.1) | Markdown なしで、サーバーの PDF / XLSX / DOCX からフォームを入力できる |

---

## 14. 未決事項
- ~~text model と Decision model の設定方法~~ → jev-ultrafast の `.env` と同じ 6 項目に決定 (§6.1)。
- Auto Submit の送信前カウントダウン (1.5 秒) は、デモの速さとのトレードオフになる。
- 配布 (Chrome Web Store) するときの、`<all_urls>` の content script に対する審査への対応。
