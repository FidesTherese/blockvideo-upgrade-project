# 操作索引の作成・更新（D26）

**D27追記：** 日本語対応E5での意味検索・候補拡張を実装した。
現在の設定・測定結果は[semantic-retrieval.md](semantic-retrieval.md)を参照。
以下のNomicの構築手順と整合性検査は引き続き使える。D26時点の精度未評価の記述は履歴である。

操作定義を検索用の文書とベクトルへ変換し、ローカルJSONファイルに保存する。
現在は8種類・9件の版付き定義から90文書を生成する。D26は索引の生成と検証までで、
通常画面は引き続きAll Tools方式。D27で入力文の意味検索、D28でreadiness表示、
D29で方式の切替を接続する。

## 採用した構成

ユーザーは既存のNomic Embed Text v1.5を選択した。追加ダウンロードやベクトルDBは不要。
少数文書はファイルに保存し、D27では全ベクトルとのコサイン類似度比較を使う方針。
この規模での単純な比較は[Sentence Transformersの説明](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)に沿う。

Nomicは[公開カード](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)で英語モデルとされる。
今回の成功は日本語検索の精度を示さない。日本語の候補保持率・別の多言語モデルとの比較はD27。
会話用のTernary Bonsaiとは別のモデルで、設定値を推論する役割は持たない。

## 正本と生成物

- `backend/app/operations/definitions.json`：操作ID、厳密な版、説明、例、入力schemaの正本。
- `backend/app/operations/search_scope.json`：BlockVideoのアプリIDと、版付き操作ごとの対応能力。
  schemaやhandlerは複製しない。正本と一対一の対応を検査する。
- `backend/app/retrieval/nomic-profile.json`：モデルID、重みSHA-256、768次元、入力接頭辞、正規化。
- 生成先の `manifest.json`：生成時刻、生成器・抽出形式の版、正本2ファイルのハッシュ、
  定義の意味内容のハッシュ、モデル情報、文書数、文書・ベクトル・bundleのハッシュ。
- `bundle-<SHA-256>.json`：公開文書と同じ順序のベクトル。説明、例文、入力項目を別々に収録。
  各文書はUTF-8で最大1200バイト。内部handler、事前条件名、台本、会話履歴は含めない。

索引の文書は実行用の命令ではない。索引だけを変更して新しい操作を追加することはできない。
読み込み時には現在の正本から文書を再生成し、全件を照合する。

## 実行例（PowerShell）

backendを作業ディレクトリにする。LM Studioのローカルサーバーを起動し、
`text-embedding-nomic-embed-text-v1.5` を提供する。LAN公開・クラウドAPIキーは不要。
既存の[ローカル埋め込みAPI](https://lmstudio.ai/docs/developer/openai-compat/embeddings)を呼び出す。
このコマンド自体はサーバーの起動・停止・モデルのダウンロードを行わない。
LM Studio側の設定により、初回の埋め込み呼び出しで既存モデルが読み込まれる。

```powershell
Set-Location C:\Users\Danir\Downloads\blockvideo-upgrade-project\backend
$indexDir = 'storage/operation-index'
$embeddingWeights = 'C:\Users\Danir\.lmstudio\.internal\bundled-models\nomic-ai\nomic-embed-text-v1.5-GGUF\nomic-embed-text-v1.5.Q4_K_M.gguf'
python -m uv run python -m scripts.operation_index build --index $indexDir --weights $embeddingWeights
python -m uv run python -m scripts.operation_index validate --index $indexDir
python -m uv run python -m scripts.operation_index select --index $indexDir --app blockvideo --capability settings.write --operation project.settings.update@1 --operation project.settings.update@2
```

最後の例では `settings.write` のみ対応していると指定したのでv1だけを返す。
v2には `--capability settings.relative-subtitle` も必要。版の指定を省いて最新版へ置き換えることはない。
能力はアプリが実装している機能の情報であり、ジョブの実行中/停止中やAPIキーの有無ではない。
`select` は指定した範囲の文書を選ぶだけで、入力文章による類似度検索はしない。
0件を返しても「利用者の依頼が未対応」とは判定しない。

`validate` と `select` はネットワークもモデルも使用しない。終了コード0は成功、2は検査失敗。
本文やファイル内容をエラーへ転記せず、固定の `reason_code` を返す。
`--catalog`、`--scope`、`--profile` で開発用の別ファイルを指定できる。
生成物をGitへ入れないため、通常の生成先は既に除外済みの `storage/` を使う。

## 定義を更新するとき

1. 正本の操作定義を変更し、操作の契約変更なら操作版も更新する。範囲対応も同じID・版へ更新する。
2. 共通コア側の登録・検証を済ませる。索引へ追加するだけではhandlerは登録されない。
3. 同じ `build` コマンドで再構築し、`validate` を実行する。
4. D27以降の利用箇所でも、候補選択前に現在の `load_sources()` を使って検証する。
   `eligible_documents(scope, current_sources)` は保持中の索引にもこの照合を要求する。
5. 抽出処理や埋め込み前処理を変える場合、対応する形式・生成器・正規化の版も更新し、再構築する。

説明だけの変更や改行・空白の変更でもファイルハッシュが変わるので、旧索引は `stale_index` で拒否する。
未知のID/版・不一致の範囲定義も拒否する。別版・実行可能な別操作を代わりに選ばない。
実行時の対象、引数、revision、readiness、生成の明示確認は既存の共通コアが検査する。

## 書き込みの整合性と制約

全ベクトルの件数・次元・有限値・正規化を検査してからbundleを保存する。
一時ファイルをflush/fsyncし、置換する。最後にmanifestを原子的に置換する。
途中の失敗は公開済みmanifestを変更せず、成功時も過去bundleを削除しない。
失敗で残った未参照bundleは読まれない。自動整理機能はない。

モデルには文書しか渡さず、ファイルパスや更新コマンドを渡さない。
埋め込みAPIはモデルID・応答番号・件数・次元・有限値を検査し、リダイレクト・自動再試行をしない。
重みファイルは呼び出し前後にSHA-256で照合する。ただし、ローカルサーバーが実際に
その重みを使うことはサーバーへの信頼に依存し、モデル名だけによる暗号学的証明ではない。
manifestとbundleのハッシュも、両方を書き換えられるローカル攻撃者への電子署名ではない。

この工程では画面・動画生成を変更していない。D24の評価文・人の承認台帳も更新しない。
