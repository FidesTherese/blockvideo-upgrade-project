import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import type { StartupState } from '@/lib/types';

const NETWORK_FAILURE_MESSAGE = '起動状態を確認できません。通信を確認してから再読み込みしてください。';
const MIGRATION_GUIDANCE = 'アプリを停止したまま、文書化されたバックアップ復元手順を確認してください。復元後にアプリを再起動してください。';

export function StartupStatus() {
  const [startup, setStartup] = useState<StartupState | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    api.startup()
      .then((state) => {
        if (active) setStartup(state);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (failed) {
    return <div role="alert" className="border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">{NETWORK_FAILURE_MESSAGE}</div>;
  }
  if (!startup) {
    return <div role="status" className="text-sm text-slate-600">起動状態を確認しています。</div>;
  }
  if (startup.status === 'migration_failed') {
    return (
      <div role="alert" className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
        <p>{startup.message}</p>
        <p className="mt-1">{MIGRATION_GUIDANCE}</p>
      </div>
    );
  }
  if (startup.status === 'starting') {
    return <div role="status" className="text-sm text-slate-600">{startup.message}起動が完了するまでお待ちください。</div>;
  }
  return <div role="status" className="text-sm text-slate-600">{startup.message}</div>;
}
