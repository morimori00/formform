# formform サーバーを社内で動かす

formform は、Markdown ファイルのほかに、社内サーバーに取り込んだ文書 (Google Drive / Slack / Notion / アップロードしたファイルなど) からフォームを入力できます。
サーバーは [Onyx](https://github.com/onyx-dot-app/onyx) (MIT ライセンスの Community Edition) に、formform 用の検索 API を足したものです。文書と検索用のインデックスは、すべて自社のサーバーに置きます。

```text
Chrome 拡張 (各社員の PC)                      社内サーバー (docker compose)
  Fill ─ 空欄のラベルから検索クエリを作る ──▶  nginx :3080
                                               └ api_server   Onyx + /api/formform/*  (server/formform_onyx)
       ◀── 該当箇所の本文 (最大 12,000 文字) ──   ├ inference_model_server  埋め込みモデル (ローカル実行)
  ↓                                            ├ opensearch   ベクトル + キーワード検索
  Markdown と合わせて text model へ             ├ background   コネクタの取り込み (Drive / Slack / Notion / File…)
                                               └ relational_db / cache
```

検索には LLM を使いません。Onyx のチャット機能 (LLM が回答を作る機能) も使わないので、LLM の API キーを登録しなくても動きます。

## 1. 必要なもの

| 項目 | 目安 |
|---|---|
| OS | Linux (x86_64 / arm64)。macOS の Docker Desktop でも試せます |
| Docker | Docker Engine 24 以降と Docker Compose v2.24 以降 (`ports: !override` を使うため) |
| メモリ | 16 GB 以上を推奨。8 GB の試用構成は `FORMFORM_SMALL=1` (実測: 文書 25 件を取り込んだ状態で、コンテナの合計が約 6.2 GB) |
| CPU | 4 コア以上。GPU は不要です (埋め込みモデルは CPU で動きます) |
| ディスク | イメージ約 10 GB + 取り込む文書の量に応じた領域 (最低 30 GB を推奨) |
| その他 | `git`, `openssl`。初回だけ Docker Hub と GitHub に接続します (閉域網の場合は 8 章) |

## 2. 起動

```bash
git clone https://github.com/morimori00/formform.git
cd formform/server
./up.sh                      # 8 GB のマシンで試す場合: FORMFORM_SMALL=1 ./up.sh
./up.sh ps                   # 全コンテナが running / healthy になるまで数分かかります
```

`up.sh` は次のことをします。

1. `server/.env` がなければ `env.template` から作り、`USER_AUTH_SECRET`・`ENCRYPTION_KEY_SECRET`・PostgreSQL と OpenSearch のパスワードを `openssl rand` で生成します。`.env` は Git の管理外です。
2. `.env` の `IMAGE_TAG` (既定は `v5.1.1`) と同じタグの Onyx を `server/.onyx/` に clone します。使うのは compose ファイルと nginx の設定だけで、このリポジトリに Onyx のソースは含めていません。
3. Onyx の `docker-compose.yml` に `docker-compose.formform.yml` を重ねて `docker compose up -d` を実行します。

`./up.sh <サブコマンド>` で、同じ構成に対する `docker compose` のサブコマンドをそのまま実行できます (`./up.sh logs -f api_server`, `./up.sh down` など)。

起動したら、サーバー上のブラウザで `http://localhost:3080` を開きます。別の PC から使う方法は 7 章を見てください。

## 3. 管理者とアクセストークンを作る

1. `http://localhost:3080` を開き、**Create an Account** でメールアドレスとパスワード (8 文字以上) を登録します。最初に登録したユーザーが管理者になります。確認メールは送られません。
2. 「Let's get started」という LLM の設定画面が出ても、設定せずに進めてかまいません。formform は検索だけを使います。
3. 拡張機能を使う社員も、同じ画面でそれぞれアカウントを作ります (2 人目以降は一般ユーザーになります)。
4. 各自が、左下のユーザーメニュー → **Settings → Accounts & Access → Access Tokens → New Access Token** でトークンを作ります。
   - **Permissions** は、既定の「Inherits all of your permissions」のままにせず、検索の読み取り (`read:search`。作成後の一覧には「Read search」と表示されます) だけにします。こうすると、このトークンでは検索しかできず、チャットや管理 API は 403 になります。管理者のアカウントで作る場合は、特に忘れないでください。
   - **Expires in** で有効期限を決めます。
5. 表示されたトークン (`onyx_pat_…`) を控えます。あとから再表示はできません。これを拡張機能に入れます (5 章)。

登録できるメールアドレスを自社ドメインに限るには、`server/.env` に `VALID_EMAIL_DOMAINS=example.co.jp` を追加して `./up.sh` を実行し直します。

Admin Panel の **Service Accounts** (共有の API キー) の画面は、Community Edition では開けません (Business / Enterprise プランの表示になります)。そのため、ここでは個人のアクセストークンを使います。トークンは本人の権限で動き、Settings の同じ画面からいつでも無効にできます。

## 4. 接続元を追加する

Admin Panel の **Connectors** (`/admin/connectors`) で接続元を選びます。取り込みの状況は **Indexing Status** (`/admin/indexing-status`) で確認できます。
**Document Access** (グループ単位の制限、接続元の権限との同期) は Business プランの機能で、この構成では選べません。**つまり、サーバーにアカウントを持つ全員が、取り込んだ文書をすべて検索できます。** 取り込む範囲 (フォルダ、チャンネル、ページ) は、その前提で決めてください。

### 4.1 ファイル (PDF / Word / Excel / PowerPoint / Markdown)

外部のアカウントが要らないので、最初の動作確認に向いています。

1. **Connectors → File** を開きます。
2. **Add files…** からファイルを追加します。対応形式は `.pdf` `.docx` `.pptx` `.xlsx` `.md` `.txt` `.csv` `.html` など。`.zip` にまとめてもアップロードできます。試すだけなら [`server/sample-docs/`](../server/sample-docs) の架空の会社資料が使えます。
3. **Display Name** に名前を付け、**Create Connector** を押します。
4. Indexing Status が **Active** になり、文書数が表示されれば完了です (サンプル 5 件で、実測 19 秒)。

Obsidian の Vault は Markdown ファイルのフォルダなので、zip にまとめてこの File コネクタにアップロードします。

### 4.2 Google Drive

Onyx のサーバーから Google の API (`*.googleapis.com`) への HTTPS 通信が必要です。OAuth を使う方法を書きます (Google Workspace 全体を対象にする場合はサービスアカウントも使えます: `server/.onyx/documentation/admins/connectors/official/google_drive/service_account.mdx`)。

Google Cloud 側 (管理者):

1. <https://console.cloud.google.com/projectcreate> でプロジェクトを作ります。
2. **APIs & services → Enabled APIs and services → + ENABLE APIS AND SERVICES** で、**Google Drive API**・**Admin SDK API**・**Google Sheets API**・**Google Docs API** を有効にします。
3. **OAuth consent screen** を設定します。User Type は、Google Workspace の組織があれば **Internal** を選びます。
4. スコープに `.../auth/drive.readonly`・`.../auth/drive.metadata.readonly`・`.../auth/admin.directory.user.readonly`・`.../auth/admin.directory.group.readonly` を追加します。
5. **Credentials → + CREATE CREDENTIALS → OAuth client ID** で **Web application** を作ります。
   - Authorized JavaScript origin: `server/.env` の `WEB_DOMAIN` と同じ URL (例: `https://formform.example.co.jp`)
   - Authorized redirect URI: `<WEB_DOMAIN>/admin/connectors/google-drive/auth/callback`
6. 作成後、クライアントの JSON をダウンロードします。

Onyx 側:

1. **Connectors → Google Drive** を開き、**Authentication Account → Create New → OAuth** で、ダウンロードした JSON をアップロードします。
2. **Authenticate with Google Drive** を押し、取り込みたい Drive のアカウントでログインします。
3. 取り込む範囲を選びます (共有ドライブ、マイドライブ、特定のフォルダの URL)。
4. **Create Connector** を押します。

`WEB_DOMAIN` が実際にブラウザで開く URL と違うと、Google からのリダイレクトが失敗します。`.env` を直したら `./up.sh` を実行し直してください。

### 4.3 Slack

Onyx のサーバーから `slack.com` への HTTPS 通信が必要です。Slack ワークスペースの管理者が行います。

1. <https://api.slack.com/apps> → **Create New App → From an app manifest** でワークスペースを選びます。
2. YAML タブに次を貼り付けて作成します。

   ```yaml
   display_information:
     name: OnyxConnector
     description: ReadOnly Connector for indexing Onyx
   features:
     bot_user:
       display_name: OnyxConnector
       always_online: false
   oauth_config:
     scopes:
       bot:
         - channels:history
         - channels:read
         - groups:history
         - groups:read
         - channels:join
         - im:history
         - users:read
         - users:read.email
         - usergroups:read
   settings:
     org_deploy_enabled: false
     socket_mode_enabled: false
     token_rotation_enabled: false
   ```
3. **OAuth & Permissions → Install to Workspace** で承認し、**Bot User OAuth Token** (`xoxb-…`) をコピーします。
4. Onyx の **Connectors → Slack → Authentication Account → New Slack Account** で、**Slack Bot Token** に貼り付けます。足りないスコープがあれば、保存の前に表示されます。
5. 必要なら **Advanced Options** で取り込むチャンネルを絞り、**Create Connector** を押します。

公開チャンネルにはボットが自分で参加します。非公開チャンネルを取り込むには、そのチャンネルにアプリを招待します。

### 4.4 Notion

Onyx のサーバーから `api.notion.com` への HTTPS 通信が必要です。

1. Notion のワークスペースオーナーが <https://app.notion.com/developers/connections> で **New connection** を作り、認証方式に **Access token** を選びます。
2. その connection の権限で **Read content** だけを有効にします (書き込みの権限は不要です)。
3. **Configuration → Integration token** の **Access token** をコピーします (古い画面では Internal Integration Secret)。
4. 取り込みたいページを開き、**••• → Connections** からこの connection を追加します。子ページも対象になります。
5. Onyx の **Connectors → Notion** で **Integration Token** に貼り付けます。特定のページ以下だけを取り込むなら **Root Page ID** を指定します。
6. **Create Connector** を押します。

### 4.5 その他

Confluence、SharePoint、Box、Dropbox、GitHub、Jira、Salesforce、Web ページなど、Onyx の Community Edition にあるコネクタは同じ画面から追加できます。各コネクタの手順は `server/.onyx/documentation/admins/connectors/official/` にあります。

## 5. 拡張機能をサーバーに向ける

1. 拡張機能アイコン → **コンテキスト >** → **接続** を開きます。
2. `FORMFORM_SERVER_URL` にサーバーの URL (例: `https://formform.example.co.jp`、サーバー上で試すなら `http://localhost:3080`)、`FORMFORM_SERVER_API_KEY` に 3 章のアクセストークンを入れます。
3. **保存して確認** を押すと、接続元の一覧 (名前・種類・状態・文書数) が表示されます。**接続元を管理** は、サーバーの Indexing Status を新しいタブで開きます。
4. フォームのページで Fill を押します。Markdown をアップロードしていなくても、サーバーだけで入力できます。両方あるときは、Markdown の後ろに、サーバーから読み込んだ箇所を足してモデルに渡します。

`.env` を読み込む機能も、この 2 つのキーに対応しています。

```dotenv
FORMFORM_SERVER_URL=https://formform.example.co.jp
FORMFORM_SERVER_API_KEY=onyx_pat_…
```

トークンは `chrome.storage.local` にだけ保存し、service worker からそのサーバーにだけ送ります。サーバーに接続できないときは、Markdown があれば Markdown だけで入力を続け、なければエラーを表示して何も入力しません。

## 6. どのデータがどこへ行くか

| データ | 行き先 | 補足 |
|---|---|---|
| 取り込んだ文書、インデックス、埋め込みベクトル | 社内サーバーの Docker ボリュームだけ | 埋め込みモデル (`ibm-granite/granite-embedding-97m-multilingual-r2`) はイメージに同梱されていて、サーバー上の CPU で動きます |
| 検索クエリ (フォームの空欄のラベル) | 拡張機能 → 社内サーバー | LLM は呼びません |
| Onyx の開発元への通信 | なし | `ONYX_AIRGAPPED=true` と `DISABLE_TELEMETRY=true` を既定にしています |
| コネクタの通信 | 社内サーバー → Google / Slack / Notion の API | 文書を取り込む方向だけです。File コネクタだけを使うなら、外向きの通信はありません |
| Fill のときのコンテキスト (Markdown と、サーバーから読み込んだ箇所) とページのテキスト | 拡張機能 → **設定した text model** | 社外に出さないためには、text model を社内の Ollama / vLLM にします (`TEXT_MODEL_BASE_URL`) |
| コンボボックスなどの操作の判断 (ページの状態、入力予定の値、コンテキストの先頭 4,000 文字) | 拡張機能 → **TypeSafe の API (社外)** | 独自ドロップダウンやオートコンプリートがあるフォームでだけ呼びます。この経路をなくすには、Decision model を社内で動かす必要があります (現在は未対応) |

つまり、サーバー側から文書が社外に出ることはありません。ただし、フォームに入力する値そのものは、拡張機能が使うモデルに渡ります。「社外のモデルに一切送らない」という要件があるなら、text model を社内に置き、独自ウィジェットのあるフォームでは Decision model に送られる内容を確認してください。

## 7. 社内ネットワークと TLS

- 既定では `127.0.0.1:3080` だけで待ち受けます。平文の HTTP を社内 LAN に直接出さないためです。
- 社内に公開するときは、TLS を終端するリバースプロキシ (社内の nginx / Caddy / ロードバランサ) をサーバーの前に置き、`http://127.0.0.1:3080` に転送します。証明書は社内 CA のものでかまいません。その CA が社員の PC で信頼されていれば、拡張機能はそのまま接続できます。
- `server/.env` の `WEB_DOMAIN` を、社員がブラウザで開く URL (`https://formform.example.co.jp`) にします。Google Drive の OAuth はこの値を使います。
- プロキシを置かずに試すだけなら、`.env` で `FORMFORM_BIND=0.0.0.0` にすると `http://<サーバーの IP>:3080` で届きます。トークンが平文で流れるので、本番では使わないでください。
- 拡張機能は service worker から直接サーバーを呼ぶので、サーバー側の CORS 設定は要りません。
- 開けるポートは、リバースプロキシの 443 だけです。PostgreSQL・OpenSearch・Redis・モデルサーバーは、Docker の内部ネットワークにしか出していません。
- コネクタを使う場合だけ、サーバーから各サービスの API への外向き HTTPS を許可します (4 章の各節)。

## 8. 閉域網で動かす

インターネットに出られないサーバーでは、接続できるマシンでイメージと Onyx のタグを取得して持ち込みます。

```bash
# 接続できるマシンで
cd formform/server && ./up.sh pull
docker save $(./up.sh config --images | sort -u) | gzip > formform-images.tar.gz
tar czf formform-server.tar.gz -C .. server        # .onyx と .env を含みます

# 閉域網のサーバーで
tar xzf formform-server.tar.gz && docker load < formform-images.tar.gz
cd server && ./up.sh
```

既定の埋め込みモデルはイメージに入っているので、Hugging Face への接続は要りません。Admin Panel の Index Settings で別のモデルに変えると、そのモデルを初回にダウンロードしようとします。

## 9. アップグレード

1. Onyx のリリースノートを確認し、`server/.env` の `IMAGE_TAG` を新しいタグに書き換えます。
2. `./up.sh pull && ./up.sh` を実行します。`up.sh` が `server/.onyx/` を同じタグに取り直し、API サーバーが起動時に DB のマイグレーションを実行します。
3. `curl -H "Authorization: Bearer <トークン>" http://localhost:3080/api/formform/sources` が接続元の一覧を返すことを確認します。

`server/formform_onyx/app.py` は、Onyx の内部モジュール (`search_pipeline` など) を import しています。メジャーバージョンを上げるとモジュールの場所が変わることがあり、その場合は API サーバーが起動時に ImportError で止まります (`./up.sh logs api_server`)。動作を確認したのは `v5.1.1` です。アップグレードの前に、Docker ボリュームのバックアップを取ってください。

## 10. 停止と削除

```bash
./up.sh stop          # 止める (データは残る)
./up.sh down          # コンテナを消す (データは残る)
./up.sh down -v       # 取り込んだ文書・インデックス・ユーザーを含め、すべて消す
rm -rf .onyx .env     # clone した Onyx と、生成した秘密情報を消す
```

## 11. Onyx に加えた変更とライセンス

Onyx 本体のファイルは書き換えていません。足したものは次の 2 つです。

| 変更 | 理由 |
|---|---|
| `server/formform_onyx/app.py` を API サーバーのコンテナにマウントし、`onyx.main` の代わりにこれを起動する。標準のアプリに `POST /api/formform/context` と `GET /api/formform/sources` を足す | 標準の `POST /api/search` は、クエリの書き換えや文書の選別に LLM を呼ぶため、LLM のキーがないと使えません。`/api/formform/context` は、Onyx のハイブリッド検索 (`search_pipeline`) だけを複数のクエリで実行し、重複を除いて、指定した文字数以内で返します。`/api/formform/sources` は、検索だけを許可したトークンで接続元の状態を読むためのものです (標準の API は管理者権限が必要) |
| `docker-compose.formform.yml`: コンテナ内の `/app/ee` を空のディレクトリで隠す、ポートを 1 つにして 127.0.0.1 に限定する。`.env`: ファイルの保存先を PostgreSQL にする、MCP サーバーを止める、開発元への通信を止める | Enterprise Edition のコードを読み込ませない (MIT のコードだけで動かす)、コンテナと公開ポートを減らす、データを外に出さない |

- Onyx は、`ee/` ディレクトリ以外が MIT ライセンスです (`server/.onyx/LICENSE`)。`ee/` 以下は Onyx Enterprise License で、本番で使うには契約が必要です。formform は `ee/` のコードを import せず、変更もせず、実行時にも読み込ませません。
- Docker Hub の公式イメージには `ee/` のファイルが含まれています。API サーバーと background では上の設定で隠していますが、Web UI のイメージには EE 用の画面のコードが (ライセンスがないと無効な状態で) 入ったままです。ファイルとしても含めたくない場合は、Onyx が公開している MIT のみのミラー (<https://github.com/onyx-dot-app/onyx-foss>) からイメージをビルドし、`.env` の `ONYX_BACKEND_IMAGE` / `ONYX_WEB_SERVER_IMAGE` / `ONYX_MODEL_SERVER_IMAGE` で指定してください。
- どちらの API も、トークンの持ち主が Onyx 上で読める文書だけを返します。

## 12. うまくいかないとき

| 症状 | 確認すること |
|---|---|
| `./up.sh ps` で `api_server` が unhealthy | `./up.sh logs api_server`。初回は DB のマイグレーションに 1〜2 分かかります |
| コンテナが再起動を繰り返す | メモリ不足のことが多いです。`docker stats` で確認し、`FORMFORM_SMALL=1 ./up.sh` を試してください |
| 拡張機能に `Context server returned HTTP 403` | トークンが違うか、期限切れか、検索の権限がありません。3 章の手順で作り直してください |
| `Context server unreachable` | URL、TLS 証明書 (社内 CA が PC で信頼されているか)、`FORMFORM_BIND` を確認します |
| 接続元は Active なのに入力されない | `curl -X POST -H "Authorization: Bearer <トークン>" -H "Content-Type: application/json" -d '{"queries":["会社名 所在地"]}' http://localhost:3080/api/formform/context` で、該当箇所が返るかを確認します |

## 13. 動作確認の記録 (2026-11-11)

macOS (Apple Silicon, 16 GB) の Docker Desktop (VM に 7.65 GB) で、`FORMFORM_SMALL=1 ./up.sh` の構成を確認しました。既定の構成 (モデルサーバー 2 台、OpenSearch のヒープ 2 GB) は、このマシンのメモリに収まらないため起動していません。`docker compose config` が通ることだけを確認しています。生の結果は [`docs/evidence/onyx-e2e/`](evidence/onyx-e2e) にあります。

- **サーバー**: Onyx v5.1.1。File コネクタ 2 つに、架空の会社「株式会社アオバ精密」の文書を 25 件取り込みました。`server/sample-docs/` の PDF 2 件・XLSX 1 件・DOCX 2 件と、紛らわしい内容を含む Markdown 20 件 ([`docs/evidence/onyx-e2e/distractors/`](evidence/onyx-e2e/distractors): 営業所の住所、役員の氏名、沿革の日付、社員の給与口座の手続きなど) です。LLM のキーは登録していません。
- **フォーム**: [`extension/fixtures/e-ja-vendor.html`](../extension/fixtures/e-ja-vendor.html) (取引先登録、17 項目)。
- **拡張機能**: `extension/dist` を Playwright の Chromium (headless=new) に読み込み、Floating ボタンを実際にクリックしました。text model は `qwen/qwen3.8-27b:nitro` (OpenRouter)。結果は、フォームの最終的な値 (`FormData`) で判定しています。

| 条件 | フォームの最終値 | 時間 | モデル呼び出し |
|---|---|---|---|
| サーバーのみ (Markdown なし、検索だけのアクセストークン) | サーバーの文書にある 16 項目がすべて正しい (会社概要 PDF から 8、口座情報 XLSX から 6、セキュリティ体制 DOCX から 2)。文書にない「携帯電話番号」は空のまま赤枠で「1 項目は手入力が必要です」 | 2.6 秒 | 1 (Bulk) |
| Markdown (担当者の氏名と携帯電話だけ) + サーバー | 17/17 項目が正しい。携帯電話は Markdown から、残りの 16 項目はサーバーから | 1.9 秒 | 1 |
| Markdown のみ (サーバー未設定) | Markdown にある 3 項目だけを入力。サーバーへの通信なし (これまでと同じ動作) | 1.4 秒 | 1 |
| どちらもなし | 何も入力しない (「先にコンテキストを追加」) | — | 0 |
| サーバー停止 / トークン誤り (Markdown なし) | 何も入力せず、`Context server unreachable` / `HTTP 403` を表示 | — | 0 |

検索そのもの (`/api/formform/context`、4 クエリ) は 0.08〜0.13 秒で、11 か所・約 2,300 文字を返しました。その中には、紛らわしい文書 8 件も含まれています。どの値を使うかは text model が決めます。

確認できていないこと: Google Drive / Slack / Notion への実際の接続 (外部アカウントが必要なため)。この 3 つは、起動したサーバーでコネクタのクラスが読み込めることと、管理画面の Connectors に表示されることまでを確認しました。4.2〜4.4 の手順は、Onyx v5.1.1 に同梱されている公式ドキュメントに基づいています。

### 既知の制限

- 「自社」がどの会社かを、サーバーは知りません。取り込んだ文書に複数の会社の概要 (取引先の会社案内など) があると、別の会社の値を入力する可能性があります。その場合は、Markdown に自社名を書いておくと、モデルが区別しやすくなります。
- 検索クエリは空欄のラベルだけから作ります。ラベルが「項目 1」のように意味を持たないフォームでは、該当箇所が見つかりません。
- 1 ページにつき、モデルに渡す検索結果は最大 12,000 文字です。長い文書の全体が必要な項目 (長文の自由記述など) には向きません。
