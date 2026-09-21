# Operation Catalog — Work Units 01–22

## D22 additions

Eight operation IDs now have nine registered versioned definitions. Settings.update
v2 adds an atomic relative subtitle change alongside other settings; v1 remains
unchanged. Natural-language proposals can carry `generate_after_save` for settings
only. This intent becomes a separately confirmed generation.start request after the
save receipt, bound to its resulting revision. It never grants model execution
permission. See `work-unit-22.md` and `work-report-22.md`.

## D21 接続状況（2026-09-20）

下記8操作はすべて登録済み。通常の詳細画面と自然言語の確定処理は共通コアを使う。
字幕モード・話速・話者・読み方は `project.settings.update` で既に接続済みのため、
D21で項目別handlerを重複追加していない。新規作成時も既存の専門スキーマで検証する。
旧PATCHは共通の `validate_settings` → `apply_project_settings` を使うが、要求ID再送契約は持たない。

| 初期範囲・設定群 | 状態 / 通常UI | 保存・検証 | 再生成時の影響 |
|---|---|---|---|
| 字幕サイズ（絶対/相対） | 実装済み / サイズ入力、自然言語 | 16〜120の整数、相対は一度だけ解決 | 動画組み立て |
| 字幕モード | 実装済み / 「字幕の切り替え」 | sentence / packed | 動画組み立て、音声は再利用 |
| 話速・話者 | 実装済み / 数値入力 | 話速0.5〜2.0、話者IDは非負整数。実在IDは使用エンジンに依存 | 音声＋動画 |
| 用語の読み方・アクセント | 実装済み / 「専門用語の読み方」 | カタカナ、モーラ数、表記重複、100件上限等の既存検証 | 音声＋動画。原稿・字幕表記は不変 |
| 読み上げの間 | 実装済み / 間の選択・秒数入力 | adaptive / fixed、秒数0〜5 | 音声＋動画 |
| 字幕位置・色・背景・1行文字数 | 実装済み / その他の設定 | 共通の設定スキーマ | 動画組み立て |
| 字幕表示の有無 | 実装済み / その他の設定 | boolean | 画像＋動画（字幕領域の変更） |
| 声の高さ・抑揚・音量・エンジンURL | 実装済み / その他の設定 | 共通の数値範囲・HTTP(S) URL検証 | 音声＋動画 |
| 図の強調・前後余白・最低表示時間 | 実装済み / 見せ方・その他の設定 | 共通の型・範囲検証 | 動画組み立て |
| 最大スライド枚数 | 実装済み / その他の設定 | 1〜9の整数 | 画像＋音声＋動画 |
| タイトル | 実装済み / その他の設定 | 1〜255文字 | 設定保存。生成の自動開始なし |
| 状態照会・生成・停止・再試行・設定復元 | 実装済み / 状態カード・各ボタン・履歴 | 下記の登録操作と現在状態検査 | 操作ごとの計画。成功動画は保持 |

自然言語の非空の読み方追加は既存一覧に表記単位で統合する。通常フォームは編集済みの一覧を保存する。
保存する最終値の検証・履歴・revision・無効化は共通。読み方の推測や明示されない復元先は質問へ戻す。
全 `ProjectPatch` フィールドが設定操作のスキーマに存在することをD21の自動試験で照合する。
接続済みは全言い回しの正解率を保証する意味ではない。詳細は `work-report-21.md`。

### 自然言語の初期範囲に含めないもの

| 項目 | 分類・利用可能な経路 |
|---|---|
| プロジェクト作成・削除、APIキー/プロバイダー選択 | 自然言語コアの非対象。既存の専用画面/APIを使う |
| 原稿・ブロック本文・画像指示・構成の直接編集 | 自然言語設定操作の非対象。既存のブロック編集を使う |
| 画像/音声の個別再生成 | 既存ボタンと generation.start のblock種別で実装済み。自然言語によるブロック対象の自動推測は保証しない |
| 「変更して生成」の複合依頼、構造化出力の修復 | D22で実装。設定保存後に生成を別途確認。修復は追加一回・合計120秒以内 |
| 小型モデルの最終選定、意味検索 | D23以降、検索はD26〜27 |
| メール送信・外部サービス操作 | 非対象。別操作へ置換しない |

## 登録済み操作

| Operation ID | Version | Target | Input | Side effect | Existing implementation reused |
|---|---:|---|---|---|---|
| `project.subtitle-font-size.set` | 1 | Project | `value`: integer 16–120 | Save setting and invalidate render state | Project ORM, invalidation service |
| `project.subtitle-font-size.adjust` | 1 | Project | `delta`: integer -104–104; resolved value 16–120 | Resolve once and call the absolute setter | Same setter, durable receipt/revision |
| `project.status.get` | 1 | Project | Empty object | None | Project/job state |
| `project.settings.update` | 1 | Project | Flat strict ProjectPatch fields | Save one revision, optional generation | Validation/history/invalidation |
| `project.settings.update` | 2 | Project | `settings`: same fields; `subtitle_font_size_delta`: integer or null | Resolve delta under writer lock, validate all, save one revision | Same settings handler and receipt path |
| `project.generation.start` | 1 | Project | Optional kind and block index | New snapshot/plan job | Durable job creation |
| `project.generation.cancel` | 1 | Project | job_id | Cooperative cancellation only | Durable cancellation |
| `project.generation.retry` | 1 | Project | job_id | New current-input job with parent link | Unknown guard/planner |
| `project.settings.restore` | 1 | Project | revision | Recorded settings become a new revision | Settings validation/history |

The executable source of truth is `backend/app/operations/definitions.json`. Help and schema responses are generated from it. Handler keys resolve only through the code registry.

For either setter, `generation_requested: true` on the request envelope queues the
necessary stages of a full-generation request in the same transaction, including for unchanged settings.
It requires `request_id` and `base_revision`. The default is save-only. Status cannot
request generation; with an ID it records an immutable snapshot receipt.

All new mutation operations require request_id/base_revision. Generation kind is
full (default), rerender, block_visual or block_audio. Block operations use block_index.
Unknown remote execution blocks new generation and retry, including direct legacy endpoints.
