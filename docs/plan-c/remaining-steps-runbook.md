# 残作業の手順書（D35.1 後継候補 → D40 判定）— 2026-10-03

実装エージェント（Claude）が一人でできる作業はすべて済ませた状態です。ここに残っているのは、
**人（ユーザー）にしかできない作業**と、**実装に関わっていない別のAI・評価者にしかできない作業**、
そしてそれらが済んだ後に誰でも実行できる最終手順だけです。リリース判定は現在 **Not ready** です。

## 1. 済んでいること

| 項目 | 内容 |
|---|---|
| 固定版の実行環境 | Python 3.12.12 + uv 0.12.15（`C:\Users\Danir\tools\python\cpython-3.12.12-windows-x86_64-none`）、ツール用環境 `C:\Users\Danir\tools\bv-tooling-venv`、Node 24.11.1（`C:\Users\Danir\tools\node-v24.11.1-win-x64`）、FFmpeg 専用フォルダ（winget の `ffmpeg-8.1.2-full_build\bin`） |
| D35 の実証跡（流れの確認） | 管理ファイル `C:\Users\Danir\Downloads\blockvideo-d36-control\d35-candidate.json`（記録済みハッシュ `dda5f8b5…` と一致）、凍結 `release-evidence/d36/26933fe07103c402-522775516c07`、D39 検証（smoke 不可のため failed）、D40 判定 `release-evidence/d40/d35-decision`（Not ready） |
| 後継候補 D35.1 | コミット `93dae092bf0424595c3a71138510da480a0298cd`（ブランチ `candidate/d35.1`）。D35 から、偽の鍵6件の分割、`frontend/vite.config.js` のビルド時差分、README の前提バージョンだけを修正 |
| D35.1 の凍結 | 管理ファイル `C:\Users\Danir\Downloads\blockvideo-d36-control\d35.1-candidate.json`（SHA-256 `cbecf90b7edc8bc4e22b389d92cd7ba9c51ac32299d4581952f80a826dffa6a0`）、凍結 `release-evidence/d36/c910dcb3d2399b53-93dae092bf04`、候補チェックアウト `C:\Users\Danir\Downloads\blockvideo-d35.1-candidate` |
| D35.1 の事前確認 | 秘密情報スキャン 0 件、文書チェック 6 キーすべて合格、D39 の 9 コマンドの事前実行結果は下記 |
| ツール側の変更 | ブランチ `claude/d36-successor-candidate`（後継候補の受け付け、README から参照される文書を凍結対象に追加） |

D35.1 で D39 の 9 コマンドを固定版環境（Python 3.12.12 / uv 0.12.15 / Node 24.11.1 / pnpm 10.18.3）で事前実行した結果（証跡ではなく事前確認）:

| コマンド | 結果 |
|---|---|
| uv sync --locked（dev, retrieval） | 成功 |
| import app.main | 成功 |
| backend pytest | 1310 passed, 3 skipped（シンボリックリンク権限が無いための skip。開発者モードで実行される） |
| ruff | 成功 |
| D31〜D35 テスト | 245 passed, 3 skipped（同上） |
| pnpm install --frozen-lockfile | 成功 |
| frontend test / build / lint | 成功 / 成功 / 成功（ビルド後に追跡ファイルの変更なし） |

## 2. ユーザーにお願いすること

### 2-1. Windows の開発者モードをオンにする（D39 の smoke に必須）
設定 → システム → 開発者向け → 「開発者モード」をオン。シンボリックリンクの作成権限が無いと、
D39 の smoke は最初の段階で止まります（セキュリティ設定なので AI は変更しません）。

### 2-2. held-out の未確認 32 問を確認する
`C:\Users\Danir\Documents\BlockVideo-Evaluation\D24\held-out-v2\human-review.changed-only.html`
を開き、変更された 32 問を確認してください。確認結果は、**実装に関わっていない評価担当のAI**に伝え、
人の承認台帳へ転記してもらいます（実装エージェントは held-out の中身を読みません）。
未確認のままでも評価はできますが、その 32 問は評価対象から外れます。

### 2-3. 実際の操作確認（human operation）を行い、記録する
後継候補 D35.1 を起動して実際に操作します（README の手順。例: `make demo` 相当）。
確認メモ（気づいた点、確認した画面・操作）を1つのファイルに保存し、そのSHA-256を次の形式で記録します。

```json
{"artifact_sha256":"<確認メモのSHA-256（小文字64桁）>","candidate_id":"c910dcb3d2399b53-93dae092bf04","kind":"human_operation","recorded_at":"2026-10-04T00:00:00Z","reviewer":"<お名前>","status":"completed"}
```

キーはこの順（アルファベット順）・空白なし・末尾に改行1つの正規JSONで保存してください。
問題があって合格としない場合は `"status":"failed"` にします。

### 2-4. PR の扱いを決める
ツール側ブランチ `claude/d36-successor-candidate` の PR をレビュー後にマージしてください。
`candidate/d35.1` は候補そのものなので main にはマージしません。

## 3. 別のAI・独立評価者にお願いすること

### 3-1. 独立レビュー
- ツール側 PR と、後継候補の差分（`522775516c07..93dae092bf04`）をレビューする。
- 結果を `kind` が `independent_review` の記録（2-3 と同じ形式）として保存する。

### 3-2. D37 目隠し評価（独立評価者のみ。実装エージェントは実行しない）
held-out の封印フォルダと承認台帳を使い、評価者が管理するモデル・インデックス・トークン鍵で実行します。

```text
python -m uv run python -m scripts.run_blinded_evaluation \
  --candidate-root C:\Users\Danir\Downloads\blockvideo-d35.1-candidate \
  --freeze-manifest <repo>\release-evidence\d36\c910dcb3d2399b53-93dae092bf04\freeze-manifest.json \
  --corpus <封印フォルダの held-out コーパス> \
  --human-review <人の承認台帳> --independent-review <独立承認台帳> \
  --output <新しい空の評価出力フォルダ> --model <評価者のモデルID> \
  --index <評価者のstatefulインデックス> --evaluator-name <評価者名> \
  --token-key-file <評価者のトークン鍵ファイル>
```

出力の `protocol.json` と `result-bundle.json`、D37 ツールの構成証明を次の手順で使います。

## 4. 上記が揃った後（誰でも実行可）

コマンドは `backend` で、`C:\Users\Danir\tools\bv-tooling-venv\Scripts\python.exe` を使います。
PATH の先頭に Node 24.11.1 と FFmpeg 専用フォルダを置きます。パスはすべて絶対パスにします。

1. **D38 取り込み**: `python -m scripts.import_evaluation_result --bundle <result-bundle.json> --expected-sha256 <そのSHA-256> --freeze-manifest <D35.1 の freeze-manifest.json> --protocol <protocol.json> --d36-trial-tool-attestation <D35.1 凍結の d36-tool-attestation.json> --d37-tool-attestation <D37 ツール構成証明> --repo-root .. --output <repo>\release-evidence\d38-d35.1`
2. **D39 準備**: `python -m evaluation.scripts.materialize_candidate_runtime --candidate-root C:\Users\Danir\Downloads\blockvideo-d35.1-candidate --freeze-manifest <freeze-manifest.json> --work-root C:\Users\Danir\bv-d39-work --output <repo>\release-evidence\d39-d35.1-materialization\runtime-materialization.json`
3. **D39 smoke**（開発者モードが必要）: `python -m evaluation.scripts.d39_smoke` に候補・凍結・runtime・準備記録とそのSHA-256・作業フォルダを渡し、`--output <repo>\release-evidence\d39-d35.1-smoke`（準備記録とは別フォルダ）
4. **D39 検証**: `python -m evaluation.scripts.verify_release_candidate`（同じ入力 + `--smoke-manifest <smoke-manifest.json>`、`--output <repo>\release-evidence\d39-d35.1-verification`）
5. **D40**: `python -m evaluation.scripts.attest_release_decision --repo-root .. --output <repo>\release-evidence\d40\d35.1\decision-tool-attestation.json --expected-sha256 <集計値>` の後、`python -m scripts.decide_release_readiness` に凍結・D38 の3ファイル・D39 の検証記録と構成証明（それぞれ別途SHA-256）・2つのレビュー記録を渡す。出力は新しいフォルダ。

D35 での実行例（失敗側の確認）は `release-evidence/` に残しています。出力先フォルダの重なりは拒否されるので、
各段階は別フォルダにしてください。
