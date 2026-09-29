import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/api/client';
import { GenerationHistory } from '@/components/GenerationHistory';
import { RecoveryStatus } from '@/components/RecoveryStatus';
import { StartupStatus } from '@/components/StartupStatus';
import type { JobSummary, RecoveryCode, RecommendedAction, StartupState } from '@/lib/types';
import { jobFixture } from '@/test/project-fixtures';

vi.mock('@/api/client', async (original) => {
  const actual = await original<typeof import('@/api/client')>();
  return { ...actual, api: { ...actual.api, startup: vi.fn() } };
});

const recoveryCases: Array<{
  recoveryCode: RecoveryCode;
  recommendedAction: RecommendedAction;
  label: string;
  guidance?: string;
}> = [
  {
    recoveryCode: 'wait',
    recommendedAction: 'wait',
    label: '処理の完了待ち',
    guidance: '処理が完了するまでお待ちください。',
  },
  {
    recoveryCode: 'safe_retry',
    recommendedAction: 'retry_current',
    label: '再実行できます',
    guidance: '現在の設定で新しい生成として再実行できます。',
  },
  {
    recoveryCode: 'external_outcome_unknown',
    recommendedAction: 'check_provider',
    label: '外部処理の結果が不明',
    guidance: '自動で再送しません。外部サービス側の実行履歴を確認してください。',
  },
  {
    recoveryCode: 'refresh_required',
    recommendedAction: 'refresh',
    label: '状態の再取得が必要',
    guidance: '画面を再読み込みして最新の状態を確認してください。',
  },
  {
    recoveryCode: 'cancelled',
    recommendedAction: 'none',
    label: 'キャンセル完了',
  },
  {
    recoveryCode: 'completed',
    recommendedAction: 'none',
    label: '生成完了',
  },
  {
    recoveryCode: 'failed',
    recommendedAction: 'none',
    label: '生成失敗',
  },
];

describe('RecoveryStatus', () => {
  it.each(recoveryCases)(
    'renders exact guidance for $recoveryCode/$recommendedAction without owning an action',
    ({ recoveryCode, recommendedAction, label, guidance }) => {
      const job: JobSummary = jobFixture({
        recovery_code: recoveryCode,
        recommended_action: recommendedAction,
      });

      const { container } = render(<RecoveryStatus job={job} />);

      expect(screen.getAllByRole('status')).toHaveLength(1);
      expect(screen.getByRole('status')).toHaveTextContent(label);
      if (guidance) {
        expect(screen.getByRole('status')).toHaveTextContent(guidance);
      }
      expect(container.querySelector('button')).toBeNull();
    },
  );
});

const startup = (overrides: Partial<StartupState> = {}): StartupState => ({
  status: 'ready',
  reason_code: null,
  message: '起動が完了しました。',
  schema_version: 1,
  backup_available: false,
  ...overrides,
});

describe('GenerationHistory recovery controls', () => {
  it('shows retry only for an authoritative retry-current action', () => {
    render(<GenerationHistory
      jobs={[jobFixture({ recovery_code: 'safe_retry', recommended_action: 'retry_current', retryable: true })]}
      disabled={false}
      running={false}
      onRetry={vi.fn()}
      onCancel={vi.fn()}
    />);

    expect(screen.getByRole('button', { name: '現在の設定で再実行' })).toBeEnabled();
  });

  it('keeps an unknown provider outcome button-free', () => {
    render(<GenerationHistory
      jobs={[jobFixture({
        status: 'unknown',
        recovery_code: 'external_outcome_unknown',
        recommended_action: 'check_provider',
        retryable: false,
      })]}
      disabled={false}
      running={false}
      onRetry={vi.fn()}
      onCancel={vi.fn()}
    />);

    expect(screen.getByRole('status')).toHaveTextContent('外部処理の結果が不明');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('StartupStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the exact starting guidance', async () => {
    vi.mocked(api.startup).mockResolvedValue(startup({
      status: 'starting',
      message: '起動処理中です。',
      schema_version: null,
    }));

    render(<StartupStatus />);

    await screen.findByText('起動処理中です。起動が完了するまでお待ちください。');
    expect(screen.getByRole('status')).toHaveTextContent(
      '起動処理中です。起動が完了するまでお待ちください。',
    );
  });

  it('shows the exact ready status', async () => {
    vi.mocked(api.startup).mockResolvedValue(startup());

    render(<StartupStatus />);

    await screen.findByText('起動が完了しました。');
    expect(screen.getByRole('status')).toHaveTextContent('起動が完了しました。');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows bounded migration recovery guidance without performing recovery', async () => {
    vi.mocked(api.startup).mockResolvedValue(startup({
      status: 'migration_failed',
      reason_code: 'migration_failed',
      message: 'データベースの移行に失敗しました。管理者に確認してください。',
      schema_version: null,
      backup_available: true,
    }));

    const { container } = render(<StartupStatus />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'データベースの移行に失敗しました。管理者に確認してください。アプリを停止したまま、文書化されたバックアップ復元手順を確認してください。復元後にアプリを再起動してください。',
    );
    expect(container.querySelector('button')).toBeNull();
  });

  it('uses fixed network guidance and never exposes private error details', async () => {
    vi.mocked(api.startup).mockRejectedValue(
      new Error('C:\\Users\\private-user\\database.sqlite'),
    );

    render(<StartupStatus />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '起動状態を確認できません。通信を確認してから再読み込みしてください。',
    );
    expect(screen.queryByText(/private-user|database\.sqlite/)).not.toBeInTheDocument();
  });

  it('does not replace a newer state after unmount', async () => {
    let resolveStartup!: (state: StartupState) => void;
    vi.mocked(api.startup).mockReturnValue(new Promise((resolve) => {
      resolveStartup = resolve;
    }));

    const mounted = render(<StartupStatus />);
    mounted.unmount();
    resolveStartup(startup());

    await waitFor(() => expect(screen.queryByText('起動が完了しました。')).not.toBeInTheDocument());
  });
});
