# D23 ローカルモデルの起動・切替手順

2026-09-20に、このPC上で実際の推論を確認した開発用構成です。
自然言語の操作解釈に使うモデルです。開発を担当するCodexのモデル、台本分割用の
LLM、画像生成、音声合成の設定とは別です。27Bの圧縮モデルであり、少ない
パラメーター数のモデルを比較選定した結果ではありません。

## 確認した構成

| 項目 | 値・根拠 |
|---|---|
| LM Studio | 0.4.20（利用者が画面で確認） |
| モデルID | `ternary-bonsai-27b-heretic-ja`（モデル一覧・応答本体） |
| ファイル | `OS-Software/Ternary-Bonsai-27B-heretic-ja-GGUF/Ternary-Bonsai-27B-heretic-ja-Q2_g64.gguf` |
| サイズ | 8,214,577,440 bytes（ローカル一覧/API） |
| 量子化 | Q2_g64（ファイル名・表示名）。APIのquantizationはnull |
| 実行エンジン | `llama.cpp-win-x86_64-amd-rocm-avx2@2.41.0`（lms runtime ls） |
| コンテキスト | 8192、parallel=1、eval_batch_size=512、flash_attention=true、KV GPU offload=true（読み込み済みインスタンスAPI） |
| 推論指定 | temperature=0、max_tokens=768、reasoning_effort=none、stream=false、JSON Schema strict |
| PC | Windows 11 Pro / Ryzen 7 9800X3D / Radeon RX 9070 XT / RAM 33,408,593,920 bytes |
| 通信先 | `http://127.0.0.1:1234/v1`。環境プロキシ、リダイレクト、クラウドへの自動切替なし |

Windowsの取得方法ではGPUの正確な専用メモリ容量を確認できなかったため、VRAMの
実測値は記載しません。APIや画面で選択したモデル名だけで推論成功とは判定しません。

## 起動

1. LM StudioのDeveloper画面で、上記のダウンロード済みモデルを選びます。
2. Context Lengthを8192として読み込み、READYになるまで待ちます。
3. Server Portを1234、「ローカルネットワークで提供」をオフにし、Start serverをオンにします。
4. `GET http://127.0.0.1:1234/api/v1/models` のloaded_instancesにあるIDとcontext_lengthを確認します。
5. BlockVideoのバックエンド用設定に、次の値を設定してバックエンドを再起動します。
   `.env.example`から設定する際も、既存の`.env`全体を上書きしないでください。

```dotenv
LANGUAGE_MODEL=ternary-bonsai-27b-heretic-ja
LANGUAGE_BASE_URL=http://127.0.0.1:1234/v1
LANGUAGE_REASONING_EFFORT=none
LANGUAGE_REVIEW_ALL=false
```

今回の試験では独立DBの検証サーバーに上記を注入しました。通常利用する`.env`は
変更していません。通常の設定フォームと生成ボタンは、自然言語用モデルが未設定でも使えます。

6. プロジェクト詳細上部の「言葉で操作するAI」を開き、接続先とモデル名を確認します。
   「接続を確認」はモデル一覧を取得するだけで、依頼文の送信も推論も行いません。
7. テスト用プロジェクトで「字幕を56pxにして」などを送り、保存結果を確認します。

起動手順は[LM Studio公式手順](https://lmstudio.ai/docs/developer/core/server)、
構造化出力は[公式JSON Schema手順](https://lmstudio.ai/docs/developer/openai-compat/structured-output)、
読み込み状態は[モデル一覧API](https://lmstudio.ai/docs/developer/rest/list)に準拠しています。
以前の冷えた状態からの読み込みは9分超かかった記録があり、今回の暖まった状態の
推論時間から初回起動時間を予測することはできません。

## 切替と失敗時

別のモデルを使う場合はLM Studioで読み込み、実際のAPI応答のmodelと一致するIDを
LANGUAGE_MODELへ設定します。設定はバックエンド再起動後に有効です。表示名・ファイル名・
読み込み時の別名は一致するとは限りません。IDを確認せず他のモデルへ代替しません。

- 未設定：自然言語操作はエラー。通常フォームは利用できます。
- 接続失敗・時間切れ：新しい設定やジョブを作成せず終了します。
- モデル一覧に指定IDがない：接続確認で表示します。
- 応答のmodelが指定IDと違う、またはない：`model_mismatch`として拒否します。
  LM Studioが存在しないIDを別モデルで処理したことを実際に観測したための検査です。
  サーバー側の推論が始まること自体は止められませんが、その返答で操作は実行しません。
- 不正な構造化出力：既存の修復上限1回。通信・モデル不一致は修復で再試行しません。
- 応答を受け取れなかった操作の再送：同じ要求IDで記録を照会します。
  設定やモデルを変更した後に新しい推論を望む場合は、新しい依頼として送ります。

## 計測と残る制約

固定の開発用20ケースを、候補3件と9件（8操作ID、settings.updateは2版）で測定しました。
モデル単体の厳密一致は15/20、中央値2.694秒、最大3.585秒、入力2212〜4139 tokensでした。
この数字は一般的な正答率や最終評価ではありません。D24の未見評価には流用しません。

曖昧な量の補完・短い回答での設定漏れ・訂正の矛盾が見つかりました。D23では利用者の
指示を受け、根拠のない字幕値と記録済みの未保存設定の欠落を保存前に止める検査を追加しました。
字幕以外の指定されていない数値と、明示した話速の抜け落ちも検査します。
判断できない言い回しは聞き返します。モデル自体の誤りが消えたわけではなく、全設定・全言語の
意味を形式的に保証するものでもありません。複合依頼の短い回答は希望全体の再入力を求める場合があります。

会話を続けても同じ確認が出る場合は「新しい依頼」で希望全体を入力してください。
今回も短い回答で設定や生成希望が抜けるケースがあり、自然な対話の改善はD24〜D25で追跡します。

測定中のPC全体の空き物理メモリは最少約0.26GiB、空きコミットは約0.76GiBでした。
これは各推論前後のスナップショットであり、ピーク値やモデル単独の使用量ではありません。
ブラウザーの応答が遅い場面もあり、常用時の余裕は小さい構成です。追加購入やOS設定変更は行っていません。

[配布元カード](https://huggingface.co/OS-Software/Ternary-Bonsai-27B-heretic-ja-GGUF)には
Apache-2.0の表記と、研究・実験用途を想定し公開サービスには推奨しない旨の説明があります。
ここでの採用は利用者が選んだPC上の開発試験用です。公開版のモデル採用判断とは分けます。

再測定はbackendから、新しい出力先を指定して行います。

```powershell
python -m uv run python -m scripts.probe_local_configuration --model ternary-bonsai-27b-heretic-ja --output C:/path/to/new-probe.json
python -m uv run python -m scripts.probe_local_failures --model ternary-bonsai-27b-heretic-ja --output C:/path/to/new-failures.json
```

後者は1235番ポートが未使用という試験条件です。既存サーバーを停止せず、接続不能と
存在しないモデルIDを試します。前者は合成入力・実応答・token使用量・プロンプトと
スキーマのハッシュを記録します。通常のアプリログに依頼本文を追加するものではありません。
