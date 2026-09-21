# D27 意味検索の使い方と境界

入力文を文章用の数値列へ変換し、操作定義から作った90文書とコサイン類似度を比較する。
各操作ID・版について最も近い文書の値を使い、最初の5候補をモデルへ渡す。
検索の対象は操作の説明・例・入力schemaであり、数百件の評価用文章を索引へ混ぜてはいない。
検索は設定値を決めず、操作も実行しない。

## 候補が足りない場合

1. 最初の5候補で、未対応・質問・不正な構造化出力になった場合、8候補へ一度だけ拡張する。
2. まだ判断できなければ、同じアプリ・対応能力・正確な操作版の全候補へ一度だけ切り替える。
   現在は9件。32件を超える場合や切替を無効にした場合は、利用者への質問で止める。
3. 全候補でも曖昧なら質問する。全候補を確認した場合だけモデルの「未対応」を返せる。

各段階で未検証の別操作に置き換えて実行することはない。上限は埋め込み1回、会話モデル4回、
全体180秒。最後の全候補の段階だけ、壊れたJSON等を一度修正できる。
接続断を候補拡張として再試行しない。最初の5候補が全候補に相当する小さいscopeなら拡張しない。

候補0件は質問、索引・正本の不一致はエラーで停止する。埋め込みだけ失敗した場合は、
検証済みの同じscopeで全候補に切り替えられる。長い会話を検索用に黙って切り詰めない。
UTF-8で1200バイト、E5で512トークンを超える場合もこの経路を使う。

類似度は正解確率ではない。候補の順位は詳細欄へ記録し、モデルには既存のAll Toolsと同じ
ID・版の固定順で候補と出力schemaを提示する。順位変更でJSONの分岐順まで変更しないためである。
確定した提案は、既存の値・参照チェック、実行直前のreadiness、revision、永続要求IDを通る。
設定は即時保存し、生成は確認ボタンを押すまで開始しない。

## E5と導入

[multilingual-e5-smallの公開元](https://huggingface.co/intfloat/multilingual-e5-small)のモデルを固定して使う。
384次元、query接頭辞は`query: `、文書は`passage: `、attention maskを使った平均とL2正規化。
日本語を含む多言語モデルで、推論はONNX RuntimeのCPUのみ。リモートのPythonコードは実行しない。
版は`614241f622f53c4eeff9890bdc4f31cfecc418b3`。

- model.onnx：470,268,510バイト、SHA-256 `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`
- tokenizer.json：17,082,730バイト、SHA-256 `0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39`

このPCにはダウンロード済み。backendの`storage/embedding-models/multilingual-e5-small/`にある。
新しい環境では次の明示的な導入操作を使う。アプリ起動・利用者の依頼が勝手にダウンロードや
索引更新を行うことはない。重みとtokenizerのハッシュは構築時と初回ロード時に検査する。

```powershell
Set-Location C:\Users\Danir\Downloads\blockvideo-upgrade-project\backend
python -m uv sync --extra dev --extra retrieval --frozen
$e5Dir = 'storage/embedding-models/multilingual-e5-small'
New-Item -ItemType Directory -Path $e5Dir -Force | Out-Null
$e5Source = 'https://huggingface.co/intfloat/multilingual-e5-small/resolve/614241f622f53c4eeff9890bdc4f31cfecc418b3'
if (!(Test-Path "$e5Dir/model.onnx")) {
  Invoke-WebRequest "$e5Source/onnx/model.onnx" -OutFile "$e5Dir/model.onnx"
}
if (!(Test-Path "$e5Dir/tokenizer.json")) {
  Invoke-WebRequest "$e5Source/tokenizer.json" -OutFile "$e5Dir/tokenizer.json"
}
python -m uv run --extra retrieval python -m scripts.operation_index build --profile app/retrieval/e5-profile.json --weights "$e5Dir/model.onnx" --index storage/operation-index-e5
python -m uv run --extra retrieval python -m scripts.operation_index validate --profile app/retrieval/e5-profile.json --index storage/operation-index-e5
```

開発サーバーで有効にする場合は、同じPowerShellで以下を指定する。`.env`を書き換える必要はない。
LM Studioでは会話用Ternary Bonsaiを8192コンテキストで起動しておく。E5はLM Studioに追加しない。

```powershell
$env:LANGUAGE_RETRIEVAL_INDEX = (Resolve-Path storage/operation-index-e5).Path
$env:LANGUAGE_MODEL = 'ternary-bonsai-27b-heretic-ja'
python -m uv run --extra retrieval uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`LANGUAGE_RETRIEVAL_INDEX`未設定なら既存のAll Tools。E5用依存はoptional extraなので、通常機能だけなら不要。
profile・assetsの既定値はE5。Nomicを使う場合は対応profileと索引を明示し、ローカル埋め込みAPIを用意する。
`LANGUAGE_RETRIEVAL_ALL_TOOLS=false`なら、拡張後も候補不足のとき全操作に切り替えず質問する。
D28では、検索を有効にすると候補に暫定的なreadinessを付ける。
`LANGUAGE_RETRIEVAL_READINESS=false`でD27の注釈なし経路を維持できる。
候補の順位・数・拡張方針・実行コアは変わらない。詳しくは[candidate-readiness.md](candidate-readiness.md)。
Hard Filterは評価専用の関数で、製品の設定からは有効にできない。方式の共通比較はD29で扱う。

## 記録と開発評価

詳細欄と永続応答には、順位・コサイン類似度、提示候補、拡張回数、各段階の結果、モデル呼出し数、
処理時間、内容のUTF-8バイト数を残す。バイト数はmessagesとschema・応答テキストの量であり、
HTTP全体の通信量・トークン数・料金ではない。ログには固定コードと数値だけを記録し、本文・パスは含めない。
再送は保存済み応答を先に取得し、モデルと索引が停止していても元の結果を返す。

開発用の人・AI承認を通った80件のうち、モデル対象73件、明示的な正解操作付き52件で測定した。
Recall@5はNomic40/52、E5 52/52。E5でも最終の操作・引数一致は64/73。
残る9件は既存チェックまたは解釈器が止めることを保存出力で確認したが、依頼の完了成功ではない。
これだけで将来の文章の正答率や全体の処理成功率は保証しない。最終評価用の文章・ラベルは未使用。

再現用は`python -m scripts.probe_retrieval --help`を参照。`--model`を省くと埋め込みのRecallだけ、
指定すると実際のローカル会話モデルも呼ぶ。実行コアやDBは呼ばない。
詳細な実行結果、D25との比較上の制約、人の残確認は[work-report-27.md](work-report-27.md)に記録する。
