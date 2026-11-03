/** Profile → «История»: every ranked match with the numbers, filters and pages (backend me_stats.history). */
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, subscribe } from '../api/client';
import { useHeroes } from '../api/hooks';
import { HeroSearch } from './HeroSearch';
import { Empty, ErrorBox, fmtPct, HeroIcon, Loading, Segmented } from './ui';

interface Row {
  match: number;
  t: number | null;
  hero: number;
  win: boolean;
  k: number;
  d: number;
  a: number;
  kda: number;
  minutes: number;
  party: number;
  radiant: boolean;
  parsed: boolean;
  rating: number | null;
  tag: string | null;
}
interface Page {
  total: number;
  wins: number;
  wr: number | null;
  rows: Row[];
  offset: number;
  limit: number;
  fetched?: number | null;
  refreshing?: boolean;
}

const ago = (t: number) => {
  const m = Math.max(0, Math.round((Date.now() / 1000 - t) / 60));
  if (m < 60) return `${m} мин назад`;
  const h = Math.round(m / 60);
  return h < 48 ? `${h} ч назад` : `${Math.round(h / 24)} дн назад`;
};

const PAGE = 50;
const when = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—';
const TAG: Record<string, string> = { ruiner: 'заруинил', mvp: 'MVP', unlucky: 'тащил', carried: 'затащили', weakest: 'слабее всех' };

export function MyHistory({ onAnalyze }: { onAnalyze: (matchId: number) => void }) {
  const heroes = useHeroes().data;
  const [hero, setHero] = useState<number | null>(null);
  const [result, setResult] = useState<'' | 'win' | 'loss'>('');
  const [party, setParty] = useState<'' | 'solo' | 'party'>('');
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ offset: String(offset), limit: String(PAGE) });
  if (hero) params.set('hero', String(hero));
  if (result) params.set('result', result);
  if (party) params.set('party', party);
  const q = useQuery({
    queryKey: ['me', 'history', hero, result, party, offset],
    queryFn: () => api<Page>(`/me/history?${params}`),
    retry: false,
    placeholderData: keepPreviousData,
    // a refresh started in the background (the history was over an hour old): look again soon
    refetchInterval: (qq) => (qq.state.data?.refreshing ? 8000 : false),
  });
  const qc = useQueryClient();
  // the history was refreshed (in the background, or after a match): every profile query reads it again
  useEffect(() => subscribe((e) => e.type === 'me' && void qc.invalidateQueries({ queryKey: ['me'] })), [qc]);
  const p = q.data;
  const reset = (f: () => void) => {
    f();
    setOffset(0);
  };
  return (
    <div className="myh">
      <div className="myh__filters">
        <div className="myh__hero">
          {hero ? (
            <button className="btn btn--sm" onClick={() => reset(() => setHero(null))} title="Убрать фильтр">
              <HeroIcon id={hero} size="xs" /> {heroes?.byId.get(hero)?.name} ✕
            </button>
          ) : (
            <HeroSearch compact placeholder="Фильтр по герою" onPick={(h) => reset(() => setHero(h.id))} />
          )}
        </div>
        <Segmented
          small
          value={result}
          onChange={(v) => reset(() => setResult(v))}
          options={[{ value: '', label: 'Все' }, { value: 'win', label: 'Победы' }, { value: 'loss', label: 'Поражения' }]}
        />
        <Segmented
          small
          value={party}
          onChange={(v) => reset(() => setParty(v))}
          options={[{ value: '', label: 'Все' }, { value: 'solo', label: 'Соло' }, { value: 'party', label: 'Пати' }]}
        />
        {p && (
          <span className="muted small">
            {p.total.toLocaleString('ru')} матчей · <b className={p.wr != null && p.wr >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(p.wr)}</b> побед
            {p.fetched ? ` · обновлено ${ago(p.fetched)}` : ''}
            {p.refreshing ? ' · обновляю…' : ''}
          </span>
        )}
      </div>
      {q.isLoading && <Loading>Загружаю историю…</Loading>}
      {q.error && <ErrorBox error={q.error} />}
      {p && !p.rows.length && <Empty>Нет матчей с такими фильтрами.</Empty>}
      {p && p.rows.length > 0 && (
        <table className="table myh__table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Герой</th>
              <th>Итог</th>
              <th>У/С/П</th>
              <th>KDA</th>
              <th>Длина</th>
              <th>Пати</th>
              <th title="Рейтинг «Кто заруинил», если матч уже разобран">Рейтинг</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {p.rows.map((r) => (
              <tr key={r.match} className={r.win ? 'is-win' : 'is-loss'} onClick={() => onAnalyze(r.match)} title="Открыть разбор матча">
                <td className="muted">{when(r.t)}</td>
                <td className="table__hero">
                  <span className="mys__hero">
                    <HeroIcon id={r.hero} size="sm" />
                    {heroes?.byId.get(r.hero)?.name}
                  </span>
                </td>
                <td className={r.win ? 'c-good' : 'c-bad'}>{r.win ? 'победа' : 'поражение'}</td>
                <td>
                  {r.k}/{r.d}/{r.a}
                </td>
                <td>{r.kda.toFixed(2)}</td>
                <td className="muted">{r.minutes} мин</td>
                <td className="muted">{r.party > 1 ? `${r.party} чел.` : 'соло'}</td>
                <td>
                  {r.rating != null ? (
                    <>
                      <b className={r.rating >= 60 ? 'c-good' : r.rating <= 40 ? 'c-bad' : ''}>{r.rating}</b>
                      {r.tag && TAG[r.tag] ? <small className="muted"> {TAG[r.tag]}</small> : null}
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <span className="btn btn--sm btn--ghost">Разбор →</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {p && p.total > PAGE && (
        <div className="myh__pages">
          <button className="btn btn--sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            ← Новее
          </button>
          <span className="muted small">
            {offset + 1}–{Math.min(offset + PAGE, p.total)} из {p.total}
          </span>
          <button className="btn btn--sm" disabled={offset + PAGE >= p.total} onClick={() => setOffset(offset + PAGE)}>
            Старше →
          </button>
        </div>
      )}
    </div>
  );
}
