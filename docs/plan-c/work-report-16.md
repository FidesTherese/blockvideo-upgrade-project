# D16 実装・接続条件・検証記録

## 現在の状態

モデルから操作を提案させる境界を実装した。既存の実行コアや通常画面は変更していない。
ユーザーから合成要求5件・外部API課金0円の実接続試験を進める承認を受領した。
実際のTernary Bonsaiで5ケースすべての期待結果を確認し、D16の合格条件を満たした。
構造化出力の受信だけでは設定・要求履歴・ジョブ・成果物が変更されない。

## 接続条件

- ユーザーの選択：ローカルモデル。保存済み候補の提示後、Ternary Bonsaiで開始する回答を受領。
- モデル：`OS-Software/Ternary-Bonsai-27B-heretic-ja-GGUF/Ternary-Bonsai-27B-heretic-ja-Q2_g64.gguf`、約8.2GB。
- LM Studio内の識別子：`blockvideo-d16`。context 8192、並列1、idle TTL 3600秒で読み込み。
- 接続先：`http://127.0.0.1:1234/v1/chat/completions`。localhostのみにbind、CORS拡張なし。
- CLI commit：`71bd99c`。選択runtime：`llama.cpp-win-x86_64-amd-rocm-avx2@2.41.0`。
- 専用SDKは使用しない。既存の`httpx`でHTTPを送る。既存動画生成用LLM設定・APIキーは参照しない。
- 送信範囲：固定合成要求5件、字幕変更/状態取得の候補3件とJSON Schema、架空project ID 101 / revision 7 / 字幕48 / completed。
- 外部API課金：0円。課金API接続、モデル追加ダウンロード、実データ送信はない。
- データ・費用条件：上記条件に対し、ユーザーの「はい。進めてどうぞ」を受領。再承認は不要。
- 最終条件：`reasoning_effort: "none"`、`temperature: 0`、`max_tokens: 768`、全体timeout 120秒。

公式資料ではLM Studioの`/v1/chat/completions`が`response_format.json_schema`を受け付け、
返答テキストを`choices[0].message.content`に返す。GGUFでは文法によるサンプリングを使う。
ただしモデル・runtime・スキーマの組合せでの動作は実応答による確認が必要。
[LM Studio公式資料](https://lmstudio.ai/docs/developer/openai-compat/structured-output)
（2026-09-19参照）。Ollamaも調査したが今回の接続には選択していない。
[Ollama公式資料](https://docs.ollama.com/capabilities/structured-outputs)

思考設定は[LM Studio 0.4.8公式変更履歴](https://lmstudio.ai/changelog/lmstudio/lmstudio-v0.4.8)
でChat Completionsへの対応を確認し、実際の`/api/v1/models`応答で対象モデルの思考on/off対応を確認した。
`reasoning_effort: "none"`の効果は以下の実測で検証した。

## 実モデルの小試験

| 合成要求 | 検証済みの返答 | 時間 |
|---|---|---|
| 字幕を56pxにする | `project.subtitle-font-size.set`、`value: 56` | 2.051秒 |
| 字幕を少し大きくする | `project.subtitle-font-size.adjust`、`delta: 2` | 1.800秒 |
| 動画の状態を教えて | `project.status.get`、引数なし | 0.975秒 |
| 字幕の文字サイズを変更して（値なし） | `clarification`、希望サイズを質問、`missing_fields: ["arguments"]` | 1.698秒 |
| 友達にメールを送って | `unsupported` | 1.695秒 |

すべて`executed: false`。最終5ケースの合計は8.219秒。これは合成ケースの接続・形式・分類確認であり、
自由な日本語全般の精度保証ではない。DBや`.env`を読み込まない独立コマンドで実施した。

試験中に次の2点を修正した。失敗した記録も保存し、成功扱いにはしていない。

1. 既定思考モードでは最初の5ケースすべてが`incomplete_response`になった。
   診断応答は`finish_reason: length`、出力768トークンすべてが思考、JSON本文0文字だった。
   明示的に思考を無効化すると字幕56pxの応答は`stop`、出力60トークン、思考0、正しいJSONになった。
   adapterに任意の思考無効設定を追加し、検証コマンドではこれを明示する。自動fallback/retryは追加していない。
2. その設定での5ケース中、値なしの変更要求を「未対応」と分類した。
   候補にある操作の値不足は必ず聞き返し、候補にない操作のみ未対応とする判定順をプロンプトに明記。
   形式だけでは意味の正しさを保証できない例として記録し、最終5ケースを再確認した。

合成要求の種類は承認済み5種類のみ。調査・再試験を含めた推論回数は17回
（初回5、同じ字幕56px要求での診断2、思考設定変更後5、指示明確化後5）。外部API課金は0円。

証拠はタスクの`outputs/d16-verification/`に保存：

- `local-model-probe.json`：最終5件、送信schema、最小状態、接続パラメーター、検証結果、時間。
- `local-model-probe-initial.json`：最初の未完了5件。
- `local-model-probe-before-clarification-fix.json`：分類修正前の5件。
- `diagnostic-default.json` / `diagnostic-none.json`：合成要求での接続診断。

再実行はLM Studioで同じモデルを読み込み、localhostのserverを開始してから、backendで行う。

```powershell
python -m uv run python -m scripts.probe_interpretation --model blockvideo-d16 --reasoning-effort none --output <absolute-evidence-path.json>
```

## 実装した境界

`backend/app/interpretation/`に次を分離した。

| ファイル | 担当 |
|---|---|
| `contracts.py` | 入力の上限、送信状態の許可項目、提案・聞き返し・未対応の型 |
| `candidates.py` | 提示候補をコピーして固定、候補ごとのJSON Schemaを生成 |
| `parser.py` | JSON全体の厳格な読取り、重複キー・深さ・不正数値・Unicodeの拒否、候補と引数の再検証 |
| `transport.py` | 差替え可能なモデル接続のインターフェース |
| `local_chat.py` | ローカルHTTP接続、完了判定、時間・サイズ制限、失敗の分類 |
| `service.py` | 最小状態と候補を渡し、検証済みの提案だけを返す |
| `errors.py` | 生のモデル返答や秘密を含まない固定の日本語エラー表示 |

既存の`LLMProvider.chat_json`が持つ「文章やMarkdownからJSONを抜き出す補正」は使わない。
通信失敗の自動再送、別モデルへの自動切替、JSON制約を外すフォールバックもない。
接続先はloopbackだけ、環境変数のHTTP proxyは無効、redirectも追わない。

モデルは信頼できる要求ID・対象・基準revision・生成フラグを指定できない。
正常な返答でも`executed: false`で、`proposed`は「候補の形式を満たした提案」を意味する。
実行可能性、ユーザーの意図との一致、設定保存の成功を意味しない。
自由文は聞き返し・未対応の説明だけで、実行コマンドとして扱わない。
通常画面への失敗表示はD18に接続し、D16では検証コマンドのJSON/日本語メッセージで確認する。

## 検証

`test_interpretation_boundary.py`、`test_interpretation_transport.py`、
`test_interpretation_isolation.py`で次を検査する。

- 不正JSON、コードフェンス、前後の文章、重複キー、過度の入れ子、不正な数値とUnicode。
- 余計な項目、未提示ID/版、引数の型・範囲・必須値、偽の実行フラグ。
- 通信失敗、timeout、429/5xx、redirect、応答過大、回答拒否、未完了、tool call。
- メタデータ変更が応答待ちの候補を変えないこと。秘密・原稿・出力パスを送信しないこと。
- 正常な字幕変更・生成・復元・キャンセル提案を受信してもDB全表と保存ファイルに変更がないこと。
- 提案をそのまま実行APIへ送ると422になること。別adapterに差替えても操作コアの変更が不要なこと。
- interpretationからDB・worker・実行handlerへのimportがないこと。

初回のテストで、深いJSONの拒否理由と巨大なテストIDに問題を発見し修正した。
Windowsでは巨大なパラメーターをpytestの自動IDにしないよう、短い名前を明示した。
最終確認結果（2026-09-19）：

| 確認 | 結果 |
|---|---|
| D16重点テスト | 118 passed、2.59秒 |
| backend全体 `python -m uv run pytest` | 638 passed、skipなし、72.40秒 |
| `python -m uv run ruff check .` | 成功 |
| frontend `npx -y pnpm@10.18.3 test` | 58 passed、9ファイル |
| frontend build / lint | 両方成功 |
| `git -c core.safecrlf=false diff --check` | 成功 |
| 非`__init__` 76モジュールのtop-level import検査 | 循環なし |
| 実モデルの合成小試験 | 最終5/5ケースが期待結果、設定変更・生成実行なし |

既存のStarlette/httpx非推奨警告が1件ある。自動テスト成功を実モデルの推論成功とは数えない。
テストには既存の合成動画生成・FFmpeg検証も含まれる。D16による製品画面の変更はないため、
D15で保存した画面・動画の証拠を今回の新規ブラウザ試験としては扱わない。
ログはタスク作業領域の`work/d16-*-tests.log`等に保存した。
試験後、タスク専用の`blockvideo-d16`をunloadし、起動したlocalhost serverも停止済み。

## 残る範囲

自然言語から実行への接続、対象の最新状態検査、
実行用の要求ID生成はD17。製品の自然言語入力欄と結果カードはD18。
一般的な日本語理解の精度、小型モデル比較、cloud providerの構造化出力互換性は未評価。
既存D11–D15の未コミット変更を保持。新たなDB migration・実データ変更・push・deployなし。
