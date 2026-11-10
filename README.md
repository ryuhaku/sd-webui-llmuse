# sd-webui-llmuse

LM Studio のローカル LLM を使って、日本語入力から英語プロンプトを生成する Forge Neo 拡張機能です

![screenshot](screenshot.png)

## 機能

- 日本語を入力するだけで英語プロンプトを生成
- Simple / Normal / Detail の 3 段階プリセットで生成の詳細度を調整
- プリセットのシステムプロンプトを自由に編集・追加・削除可能
- 使用するモデルをドロップダウンで切り替え
- 接続先を LM Studio / Strata から選択
- 生成結果を Forge Neo のプロンプト欄へ自動送信
- Run LLM → 画像生成を繰り返す連続生成モード
- img2img タブでは元画像を Vision モデルで読み込み、変更点だけを反映した英語プロンプトを生成
- Forge Neo の Batch タブでは、画像ごとに解析してプロンプトを作り替え

## インストール方法

**LM Studio のセットアップ**

1. [https://lmstudio.ai/](https://lmstudio.ai/) からインストーラーをダウンロードしてインストール
2. **Discover** タブでモデルを検索し、**Instruct** モデルをダウンロード


   ※ 必ず Instruct モデルを使用してください。Base モデルではシステムプロンプトに従いません。開発・検証は 16GB VRAM 環境で `Qwen3-8B-Instruct (Q4_K_M)` を使用しています。

   | VRAM | 推奨モデル | サイズ (Q4_K_M) |
   |------|-----------|----------------|
   | 24GB〜 | `Qwen3-14B-Instruct (Q4_K_M)` | 〜9.3GB |
   | 16GB | `Qwen3-8B-Instruct (Q4_K_M)` ← 開発環境 | 〜5.2GB |
   | 12GB | `Qwen3-4B-Instruct (Q4_K_M)` | 〜2.6GB |

   モデルサイズは量子化（Q値）によって変わります。Q値が高いほど精度が高くサイズも大きくなり、低いほど軽量になります。`Q4_K_M` は精度と軽量さのバランスが良くおすすめです。

   ※ SD モデルと VRAM を共有するため、実際に使える容量は環境によって異なります。上記はあくまで目安です。NSFW 用途の場合は検索キーワードに `Heretic` や `abliterated` を加えると良い感じのモデルが見つかります。

3. **Developer** タブで **Start Server** をクリックしてサーバーを起動

**LLMuse のインストール**

1. WebUI を起動
2. **Extensions** タブ → **Install from URL** を開く
3. 以下のURLを貼り付けて Install をクリック：
   ```
   https://github.com/ranran141/sd-webui-llmuse
   ```
4. WebUI を再起動

## 動作環境

- Forge Neo

## 使い方

txt2img タブのプロンプト欄の下に **「✦ LLMuse」** アコーディオンが表示されます。

1. ドロップダウンから**プリセットを選択**（Simple / Normal / Detail）
   - **Simple** — 入力を忠実に翻訳するだけ、追加要素なし
   - **Normal** — 翻訳 + 照明・雰囲気・画質タグを自然に補完（60〜80 語程度）
   - **Detail** — キャラクター詳細・ポーズ・背景・画風まで全展開（100 語以上）
2. 左のテキストボックスに**日本語で入力**
3. **Run LLM** をクリック → 右側に生成された英語プロンプトが表示される
4. モデル右の **Add / Rep** でプロンプト欄への送信モードを切り替え
   - **Add** — 既存のプロンプトに追記
   - **Rep** — 既存のプロンプトを上書き
5. **Send** をクリックして Forge Neo のプロンプト欄へ送信

### img2img タブでの使い方（Vision モデル）

img2img タブにも同じアコーディオンが表示され、**元画像を Vision モデルで解析した英語プロンプト**を作成できます。

1. img2img タブに画像を投入
2. LLMuse のモデル欄で **Vision 対応モデル**を選択（一覧には vision 対応のモデルのみが表示されます）
3. 左の欄に**日本語で変更内容を入力**して **Run LLM**
   - 未入力の場合は「元画像を忠実に再現する」扱いになります
4. 生成されたプロンプトを Add / Rep で送信し、そのまま img2img 生成を実行

- 送信する画像は回転補正を行ったうえで長辺 1536px に縮小し、JPEG（品質 90）として渡します
- 指示しなかった部分は元画像を保つように扱います
- Vision 非対応のモデルを選んだ場合はエラーを表示し、実行しません

### Batch タブでの使い方（画像ごとの解析）

Forge Neo の Batch タブで複数の画像をまとめて処理する際、**画像ごとに LLMuse でプロンプトを作り替える**ことができます。

1. LLMuse の **「Analyze each batch image」** にチェックを入れる
2. Batch タブで画像を選択・アップロード（入力ディレクトリの指定も可能です）
3. Forge Neo の **Generate** を押す（LLMuse の Run LLM から Batch を開始することもできます）

- 各画像は 1 回だけ解析し、その画像専用のプロンプトに置き換えます。生成情報（parameters）には `LLMuse Batch` / `LLMuse Prompt` が記録されます
- Dynamic Prompts で複数の組み合わせを作成しても、同じ画像の再解析は行いません
- 接続失敗・認証失敗・モデル未選択などの致命的なエラーでは Batch を停止し、画像の準備不良や空応答ではその画像だけをスキップします
- 対応するのは標準の img2img タブと Batch タブで、Sketch / Inpaint 系は対象外です

### 設定（⚙ ボタン）

| 項目 | 説明 |
|------|------|
| LLM Provider | プロンプト生成に使う接続先を `LM Studio` / `Strata` から選択（初期値: LM Studio） |
| LM Studio URL | LM Studio のサーバーアドレス（デフォルト: `http://localhost:1234`） |
| Strata URL | Strata の Base URL（例: `http://127.0.0.1:47831`）。`/v1` は付けない |
| Randomness | 出力のランダム性。低いほど忠実、高いほど多様（0.1〜2.0） |
| Auto-send | 生成後に自動でプロンプト欄へ送信する |
| Auto-generate | プロンプト欄へ送信後、自動で画像生成を開始する |
| Continuous | Run LLM → プロンプト送信 → 画像生成を繰り返す |
| Loop delay | Continuous 有効時に、次の Run LLM を実行するまでの待機時間 |
| Auto-unload | 使用後 n 秒でモデルを VRAM から解放する（LM Studio のみ） |
| Timeout | n 秒以内に応答がなければ中断する |
| Force Unload | 全モデルを今すぐ VRAM から解放する（LM Studio のみ） |

Continuous を有効にすると、`Run LLM → プロンプト欄へ送信 → 画像生成 → Run LLM` の流れを自動で繰り返します。
なお、Continuous 有効時は、プロンプトの意図しない累積を防ぐため、Add / Rep の選択に関わらず上書き送信します。
連続生成を停止する場合は、**Run LLM** ボタンを右クリックします。現在の画像生成が完了した後、次の Run LLM 実行を停止します。

### 接続先の切り替え（LM Studio / Strata）

- `LLM Provider` を切り替えると、モデル一覧はその接続先のものだけを表示します。モデル選択は接続先ごとに別々に保存されるため、LM Studio で選んだモデル ID が Strata へ渡ることはありません。
- Strata 選択中は、LLMuse からモデルのロード・アンロード要求を一切送りません。推論前の自動ロード、`ttl` の送信、推論後の自動解放は行われず、Auto-unload / Force Unload の項目も表示されません。Strata のモデルと VRAM は Strata 側で管理されます。
- Strata への推論は Thinking を無効化して送信します（`reasoning_effort: "none"`）。
- Strata で API キーが有効な場合は、`LLMUSE_STRATA_API_KEY`（既存の `STRATA_API_KEY` でも可）を環境変数に設定してから Forge Neo を起動してください。キーは settings.json・画面・ログには表示されません。キーなしで認証を要求された場合は、その旨を 401 の案内として表示します。
- Strata の API ポートは Strata の起動ごとに変わる可能性があります。接続できない場合は ⚙ 設定の `Strata URL` を現在のポートに合わせます。モデル一覧の取得に失敗したときは、モデル選択欄の下に接続失敗・認証失敗・一覧が空であることを表示し、その状態ではプロンプト送信も画像生成も始まりません。

### プリセットエディタ（📋 ボタン）

- ドロップダウンからプリセットを選択して読み込む
- テキストエリアでシステムプロンプトを編集
- **＋** ボタンで新規プリセットを作成
- **ゴミ箱アイコン**でプリセットを削除（最後の 1 件は削除不可）
- **💾 Save** で保存

## 更新履歴

### v1.1.0

- モデル選択欄の右に **Add / Rep** トグルを追加

### v1.0.0

- 初回リリース

### Unreleased

- Auto-generate と Continuous generation モードを追加
- img2img / Batch 対応
  - Vision モデルの選択と、元画像を踏まえた img2img プロンプト生成
  - Batch タブでの画像ごとのプロンプト生成と、Dynamic Prompts をまたいだ解析結果の再利用
  - 致命的なエラーではバッチを停止し、画像側の問題は該当画像のみスキップ
  - 実行結果の種別化（fatal / image / empty / length）と、出力長不足時の max_tokens 再試行
- 接続先プロバイダー選択（LM Studio / Strata）を追加
  - Strata は OpenAI 互換 API（`GET /v1/models` / `POST /v1/chat/completions`）を使い、`reasoning_effort: "none"` で推論する
  - Strata に対してはモデルのロード・アンロード・`ttl` を送らない（モデルと VRAM は Strata 側で管理）
  - API キーは環境変数 `LLMUSE_STRATA_API_KEY`（または `STRATA_API_KEY`）からのみ読み込み、設定ファイル・画面・ログには出さない
  - 接続失敗・認証失敗・モデル一覧取得失敗・空応答を区別して表示し、エラー時はプロンプト送信と画像生成を行わない
  - `provider` 項目が無い既存 settings.json は LM Studio として扱い、既存動作は変えない
