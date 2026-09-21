# Current System Map

## D21で確認した現在の接続

詳細画面の `ProjectSettingsEditor` → `useProjectOperation` → operation API →
`project.settings.update` → `validate_settings` / `apply_project_settings`。
自然言語入力は `LanguageOperationService` の検証・確定後に同じ共通コアを呼ぶ。
旧PATCHは同じ設定検証・保存・履歴・工程無効化サービスを使う。
現在の対象範囲は `operation-catalog.md`、入口の等価性は `work-report-21.md` を参照。

以下はD01〜D10当時の地図であり、現在のUIの有無を示すものではない。

## Existing save and generation path

```mermaid
flowchart LR
  Form[React forms] --> Client[api/client.ts]
  Client --> Routes[routes_projects.py]
  Routes --> Schema[schemas ProjectCreate/Patch]
  Routes --> ORM[models Project]
  ORM --> DB[(SQLite)]
  Routes --> Worker[job_runner.py]
  Worker --> Pipeline[pipeline.py]
  Pipeline --> Files[(storage/projects)]
```

- UI settings: `frontend/src/components/PacingSettings.tsx`, `ProjectForm.tsx`.
- HTTP boundary: `frontend/src/api/client.ts`; `backend/app/api/routes_projects.py`.
- Validation: `frontend/src/lib/validation.ts`; `backend/app/schemas/__init__.py`.
- Persistence: `backend/app/models/project.py`, `backend/app/db.py`.
- Setting invalidation: `backend/app/services/invalidation.py`.
- Jobs/generation: `backend/app/workers/job_runner.py`, `backend/app/services/pipeline.py`.
- Output publication: project `output_video_path` and `/api/projects/{id}/download`.

## Representative operation classification

| Operation | Existing capability | Plan C work |
|---|---|---|
| Set subtitle font size | Project PATCH and ORM field exist | Connect through shared settings service and typed operation handler |
| Get project status | Project GET exists | Provide typed operation result through common core |
| Generate/rerender/cancel | Existing APIs exist | Deferred from the operation core until units 11–15 |
| Natural-language commands | Not present on baseline | Deferred until unit 16+ |

The existing `PATCH /api/projects/{id}` has no frontend caller for existing projects. G1 verifies shared backend semantics rather than adding a new editor UI.
