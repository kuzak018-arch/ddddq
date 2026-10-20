/**
 * «Оформление игры»: the warning, the switch that unlocks installing (off by default), where things
 * go (voice language folder, read from Dota and never changed), what is installed, «Убрать всё».
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { useUi } from '../../state/ui';
import { ErrorBox, Toggle } from '../ui';

export interface ModsStatus {
  dota: string | null;
  running: boolean | null;
  language: string | null;
  language_source: string | null;
  folder: string | null;
  usable: boolean;
  other_packs: string[];
  background: { path: string; bytes: number; language: string; time: number; clean: boolean; hero: string; grid: string; menu: boolean; label: string } | null;
  fonts: string[];
  packs?: { id: string; name: string; path: string; bytes: number; files: number; top: string[]; intact: boolean }[];
  fonts_intact: boolean | null;
  background_intact: boolean | null;
  menu_client: string | null;
  error: string | null;
}

export function useModsStatus() {
  return useQuery({ queryKey: ['game-mods'], queryFn: () => api<ModsStatus>('/game-mods/status'), refetchInterval: 4000, retry: false });
}

const LANGS: Record<string, string> = { russian: 'русский', english: 'английский', ukrainian: 'украинский', schinese: 'китайский', koreana: 'корейский', spanish: 'испанский', portuguese: 'португальский', brazilian: 'бразильский' };

/** Why installing is not possible right now, or null. */
export function blocker(s: ModsStatus | undefined, enabled: boolean): string | null {
  if (!enabled) return 'Сначала включи «Оформление игры» выше и прочитай предупреждение.';
  if (!s) return 'Проверяю Доту…';
  if (!s.dota) return s.error ?? 'Не нашёл Dota 2.';
  if (s.running) return 'Дота запущена: закрой её полностью, в том числе из трея Steam.';
  if (s.running === null) return s.error ?? 'Не удалось проверить, запущена ли Дота.';
  return null;
}

export function ModsGate() {
  const enabled = useUi((s) => s.gameMods);
  const set = useUi((s) => s.set);
  const status = useModsStatus();
  const qc = useQueryClient();
  const s = status.data;
  const remove = useMutation({
    mutationFn: () => api<{ removed: { background: boolean; fonts: boolean; packs: boolean } }>('/game-mods/remove', { body: { what: 'all' } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-mods'] }),
  });
  const installed = !!s?.background || !!s?.fonts.length || !!s?.packs?.length;
  return (
    <div className={`mods-gate ${enabled ? 'is-on' : ''}`}>
      <details className="mods-gate__warn" open={!enabled}>
        <summary>
          <b>{enabled ? 'Оформление игры включено — изменение файлов игры на свой риск' : 'Это изменение файлов игры — на свой риск.'}</b>
        </summary>
        <ul>
          <li>Правила Steam формально запрещают менять файлы игры. Банов за фон меню и шрифты не известно.</li>
          <li>В 2022 году Valve на время отключала вход в онлайн с изменёнными файлами. Если такое повторится — нажми «Убрать всё».</li>
          <li>После патча Доты мод может перестать работать или спрятать новые элементы меню — тогда убери его и собери заново после обновления программы.</li>
          <li>Ставится только при закрытой Доте. Фон — отдельным файлом в папке языка озвучки, файлы Доты не меняются. Свои VPK — тоже отдельными файлами там же. Шрифт заменяет файлы Доты, но оригиналы сначала копируются к нам, и «Убрать всё» их возвращает (или «Проверить целостность» в Steam).</li>
        </ul>
      </details>
      <div className="mods-gate__toggle">
        <Toggle on={enabled} onChange={(gameMods) => set({ gameMods })} label={<b>Включить «Оформление игры»</b>} />
      </div>
      {s && (
        <div className="mods-gate__state">
          {!s.dota ? (
            <p className="warn small">{s.error ?? 'Не нашёл Dota 2 в библиотеках Steam.'}</p>
          ) : (
            <>
              <p className="small">
                Язык озвучки: <b>{LANGS[s.language ?? ''] ?? s.language}</b> <span className="muted">({s.language_source})</span>
                {s.usable ? (
                  <>
                    {' '}
                    — фон ляжет в <code>…\game\dota_{s.language}</code>.
                  </>
                ) : null}
              </p>
              {!s.usable && (
                <p className="warn small">
                  Дота не читает папку английского языка, поэтому фон меню с английской озвучкой не заработает. Поставь в Доте другую озвучку:
                  «Настройки → Звук → Язык озвучки» (например, русский; Steam докачает пакет, текст интерфейса не изменится). Если в параметрах
                  запуска Доты есть <code>-language</code> — убери его. Программа сама настройки Доты не меняет. Шрифт от языка не зависит.
                </p>
              )}
              {!!s.other_packs.length && (
                <p className="hint">
                  В папке языка уже есть чужие моды: {s.other_packs.join(', ')}. Если они тоже меняют меню, в игре победит один из них.
                </p>
              )}
              {s.running && <p className="warn small">Дота запущена — ставить и убирать можно только при закрытой.</p>}
              {s.background && (
                <p className="small">
                  Фон меню стоит{s.background_intact === false ? ', но файл изменён или удалён (обновление Steam?)' : ''} · {Math.round(s.background.bytes / 1e6)} МБ ·{' '}
                  {new Date(s.background.time * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </p>
              )}
              {!!s.packs?.length && <p className="small">Своих VPK стоит: {s.packs.length}.</p>}
              {!!s.fonts.length && (
                <p className="small">
                  Шрифт стоит: {s.fonts.length} файлов Доты заменено{s.fonts_intact === false ? ' — но Steam вернул часть оригиналов (проверка целостности?)' : ''}.
                </p>
              )}
              {s.menu_client && <p className="hint">Меню Доты в программе — {s.menu_client}. После крупного обновления Доты пересобери фон.</p>}
            </>
          )}
          {installed && (
            <button className="btn btn--sm" disabled={!!s.running || remove.isPending} onClick={() => remove.mutate()}>
              {remove.isPending ? 'Убираю…' : 'Убрать всё'}
            </button>
          )}
          {remove.data && <p className="small c-good">Убрано: {[remove.data.removed.background && 'фон', remove.data.removed.fonts && 'шрифт', remove.data.removed.packs && 'свои VPK'].filter(Boolean).join(', ') || 'ничего не стояло'}. Оригиналы Доты на месте.</p>}
          {remove.error && <ErrorBox error={remove.error} />}
        </div>
      )}
      {status.error && <ErrorBox error={status.error} />}
    </div>
  );
}
