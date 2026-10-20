/**
 * Settings card «Версия и обновления»: the app's version, checking for a newer one, downloading
 * and installing it (lib/updates.ts), automatic updates, and the author's Telegram.
 */
import { Download, Info, RefreshCw, RotateCw } from 'lucide-react';
import { useEffect } from 'react';

import { useUi } from '../state/ui';
import { appVersion, checkForUpdate, downloadUpdate, installNow, useUpdate } from '../lib/updates';
import { ExternalLink } from './ExternalLink';
import { IconTelegram, Ti } from './Icons';
import { Section } from './Section';
import { Toggle } from './ui';

const TELEGRAM = 'kuzak0';
const mb = (n: number | null) => (n ? `${(n / 1048576).toFixed(0)} МБ` : '');

export function VersionCard() {
  const u = useUpdate();
  const auto = useUi((s) => s.autoUpdate);
  const set = useUi((s) => s.set);
  const app = !!u.version; // known only in the installed app
  useEffect(() => {
    void appVersion().then((v) => {
      if (v && !useUpdate.getState().checkedAt) void checkForUpdate();
    });
  }, []);
  const c = u.check;
  const newer = c?.newer ? c : null;
  const ready = newer && u.ready?.version === newer.latest ? u.ready : null;
  return (
    <Section>
      <div className="panel__head">
        <h2>
          <Ti icon={Info} />
          Версия и обновления
        </h2>
        {u.version && <span className="pill">версия {u.version}</span>}
      </div>
      {!app && <p className="hint">Обновления работают в установленном приложении.</p>}
      {app && (
        <div className="update">
          <div className="update__state">
            {u.checking ? (
              <span className="muted">Проверяю…</span>
            ) : newer ? (
              <span>
                Доступна версия <b>{newer.latest}</b>
                {newer.size ? <span className="muted"> · {mb(newer.size)}</span> : null}
              </span>
            ) : c ? (
              <span className="muted">Установлена последняя версия</span>
            ) : u.error ? (
              <span className="muted">Не удалось проверить: {u.error}</span>
            ) : null}
            <button className="btn btn--sm btn--ghost" onClick={() => void checkForUpdate()} disabled={u.checking} title="Проверить сейчас">
              <Ti icon={RefreshCw} />
            </button>
          </div>
          {newer?.notes && <p className="update__notes">{newer.notes}</p>}
          {newer && !ready && (
            <button className="btn btn--sm btn--accent" onClick={() => void downloadUpdate()} disabled={u.downloading}>
              <Ti icon={Download} />
              {u.downloading ? `Скачиваю… ${u.progress?.match(/\d+%/)?.[0] ?? ''}` : 'Скачать обновление'}
            </button>
          )}
          {ready && (
            <>
              <button className="btn btn--sm btn--accent" onClick={() => void installNow(ready)}>
                <Ti icon={RotateCw} />
                Установить и перезапустить
              </button>
              <p className="hint">
                {auto ? 'Скачано и проверено. Установится само, когда закроешь программу, или нажми кнопку сейчас.' : 'Скачано и проверено.'}
              </p>
            </>
          )}
          {u.error && c && <p className="muted small">{u.error}</p>}
        </div>
      )}
      <Toggle
        on={auto}
        onChange={(autoUpdate) => set({ autoUpdate })}
        label="Обновлять автоматически: проверять, скачивать в фоне и ставить при закрытии программы"
      />
      <p className="hint">Обновление ставится поверх старой версии: настройки и данные сохраняются.</p>
      <ExternalLink className="contact" href={`https://t.me/${TELEGRAM}`}>
        <span className="contact__icon">
          <IconTelegram width={18} height={18} />
        </span>
        <span>
          <b>@{TELEGRAM}</b>
          <span className="muted small">Автор · вопросы, баги и идеи в Telegram</span>
        </span>
      </ExternalLink>
    </Section>
  );
}
