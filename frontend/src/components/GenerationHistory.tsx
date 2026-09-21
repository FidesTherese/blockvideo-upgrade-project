import type { JobSummary } from '@/lib/types';

const statusLabels: Record<string, string> = { pending: '開始待ち', running: '生成中', completed: '成功', failed: '失敗', cancelled: 'キャンセル完了', unknown: '外部処理の結果が不明' };
const stageLabels: Record<string, string> = { split: '台本分割', plan: '構成', image: '画像', audio: '音声', render: '動画組み立て', concat: '動画結合', subtitles: '字幕' };

export function GenerationHistory({ jobs, disabled, running, onRetry, onCancel }: {
  jobs: JobSummary[]; disabled: boolean; running: boolean; onRetry: (id: number) => void; onCancel: (id: number) => void;
}) {
  return (
    <section id="generation-history" className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-base font-semibold text-slate-800">生成の履歴</h2>
      <p className="mt-1 text-sm text-slate-500">再実行は現在の設定で新しい生成を開始します。元の試行は履歴に残ります。</p>
      {!jobs.length && <p className="mt-3 text-sm text-slate-500">まだ生成していません。</p>}
      <ul className="mt-3 space-y-3">
        {jobs.map((job) => {
          const active = job.status === 'pending' || job.status === 'running';
          return <li key={job.id} className="rounded border border-slate-200 p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-slate-800">生成 {job.id} · {statusLabels[job.status] ?? job.status}
                {job.input_revision != null && <span className="ml-2 font-normal text-slate-500">設定の版 {job.input_revision}</span>}
              </p>
              {active ? <button type="button" className="btn-danger" disabled={disabled || job.cancel_requested}
                onClick={() => onCancel(job.id)}>{job.cancel_requested ? '停止を待っています' : 'キャンセルを要求'}</button>
                : ['failed', 'cancelled', 'unknown'].includes(job.status) && <button type="button" className="btn-secondary"
                  disabled={disabled || running || !job.retryable || job.status === 'unknown'} onClick={() => onRetry(job.id)}>現在の設定で再実行</button>}
            </div>
            {job.parent_job_id != null && <p className="mt-1 text-xs text-slate-500">生成 {job.parent_job_id} からの再実行</p>}
            {job.plan?.stages && <p className="mt-1 text-xs text-slate-500">実行する工程: {job.plan.stages.map((stage) => stageLabels[stage] ?? stage).join(' → ') || '変更なし'}</p>}
            {job.cancel_requested && active && <p className="mt-2 text-amber-700">キャンセル要求済み。処理が安全に区切れる所で停止します。停止完了まで設定は変更できません。</p>}
            {job.status === 'unknown' && <p className="mt-2 text-amber-700">外部サービスの結果を確認できないため、自動で再送しません。この画面では完了状態を照会できないため、サービス側の実行履歴を確認してください。</p>}
            {(job.recovery_message || job.error_message) && <p className="mt-2 whitespace-pre-wrap text-slate-600">{job.recovery_message || job.error_message}</p>}
            {job.retry_blocked_reason && <p className="mt-1 text-amber-700">{job.retry_blocked_reason}</p>}
          </li>;
        })}
      </ul>
    </section>
  );
}
