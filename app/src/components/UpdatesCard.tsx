/** Settings card: the app's version and its updates from GitHub. */
import { checkForUpdates, installUpdate, useUpdates } from '../lib/updates';
import { Panel } from './Glass';
import { ErrorBox } from './ui';

export function UpdatesCard() {
  const u = useUpdates();
  const busy = u.status === 'checking' || u.status === 'downloading' || u.status === 'ready';
  return (
    <Panel>
      <div className="panel__head">
        <h2>Обновления</h2>
        {u.current && <span className="pill">версия {u.current}</span>}
      </div>
      {u.status === 'available' && (
        <div className="update">
          <b>Доступна версия {u.version}</b>
          {u.notes && <p className="small update__notes">{u.notes}</p>}
          <button className="btn btn--accent" onClick={installUpdate}>
            Обновить и перезапустить
          </button>
        </div>
      )}
      {u.status === 'downloading' && (
        <div className="update">
          <span className="small">Скачиваю обновление{u.progress !== null ? `: ${Math.round(u.progress * 100)}%` : '…'}</span>
          <div className="lane__progress">
            <i style={{ width: `${Math.round((u.progress ?? 0) * 100)}%` }} />
          </div>
        </div>
      )}
      {u.status === 'ready' && <p className="small">Устанавливаю и перезапускаю…</p>}
      {u.status === 'none' && <p className="muted small">У тебя последняя версия.</p>}
      {u.status === 'unconfigured' && (
        <p className="muted small">Эта сборка сделана на компьютере, а не в GitHub: автообновление в ней не настроено.</p>
      )}
      {u.status === 'error' && u.error && <ErrorBox error={u.error} />}
      <button className="btn" onClick={checkForUpdates} disabled={busy}>
        {u.status === 'checking' ? 'Проверяю…' : 'Проверить обновления'}
      </button>
      <p className="hint">
        Приложение само проверяет обновления после запуска и раз в 6 часов. Обновление подписано: чужой файл установить не получится.
        Твои настройки и данные при обновлении сохраняются.
      </p>
    </Panel>
  );
}
