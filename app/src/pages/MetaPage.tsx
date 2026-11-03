import { Activity, Ban, CalendarDays, ChartColumnIncreasing, Layers, Percent, Table2, TrendingUp, type LucideIcon } from 'lucide-react';
import { useMemo, useState } from 'react';

import { useHeroes, useSettings, useTierList } from '../api/hooks';
import type { TierRow } from '../api/types';
import { AttrIcon, RankMedal, RoleIcon } from '../components/DotaIcons';
import { Panel } from '../components/Glass';
import { Ti } from '../components/Icons';
import { ErrorBox, fmtPct, HeroIcon, Loading, Segmented, Sparkline } from '../components/ui';
import { useUi } from '../state/ui';

const RANKS = ['', 'Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];
type SortKey = 'score' | 'wr' | 'pick_rate' | 'ban_share' | 'trend_delta' | 'pos_wr';

export function MetaPage() {
  const settings = useSettings().data;
  const [pos, setPos] = useState<number | null>(null);
  const [tier, setTier] = useState<number | null>(null);
  const [days, setDays] = useState<number | null>(null);
  const [view, setView] = useState<'tiers' | 'table'>('tiers');
  const [sort, setSort] = useState<SortKey>('score');
  const tl = useTierList(pos, tier ? [tier] : null, days ?? settings?.tier_days ?? 14);
  const heroes = useHeroes().data;
  const openHero = useUi((s) => s.openHero);
  const rows = useMemo(() => {
    const xs = [...(tl.data?.heroes ?? [])];
    return xs.sort((a, b) => ((b[sort] ?? -1) as number) - ((a[sort] ?? -1) as number));
  }, [tl.data, sort]);
  const myTier = tl.data?.tiers[0];

  return (
    <Panel className="meta" refracting>
      <div className="panel__head panel__head--wrap">
        <h2>
          <Ti icon={ChartColumnIncreasing} />
          Мета
        </h2>
        <Segmented
          value={pos}
          onChange={setPos}
          options={[{ value: null, label: 'Все' }, ...[1, 2, 3, 4, 5].map((p) => ({
              value: p,
              title: `Позиция ${p}`,
              label: (
                <>
                  <RoleIcon pos={p} size={14} className="seg-role" />
                  {p}
                </>
              ),
            }))]}
        />
        <Segmented
          small
          value={tier}
          onChange={setTier}
          options={[{ value: null, label: myTier ? `Мой (${RANKS[myTier]})` : 'Мой ранг' }, ...[1, 2, 3, 4, 5, 6, 7].map((t) => ({
            value: t,
            title: RANKS[t],
            label: (
              <>
                <RankMedal tier={t * 10} size={20} className="seg-medal" />
                {RANKS[t]!.slice(0, 3)}
              </>
            ),
          }))]}
        />
        <Segmented small value={days} onChange={setDays} options={[{ value: 7, label: <><Ti icon={CalendarDays} />7 дн</> }, { value: null, label: `${settings?.tier_days ?? 14} дн` }, { value: 30, label: '30 дн' }]} />
        <Segmented small value={view} onChange={setView} options={[{ value: 'tiers', label: <><Ti icon={Layers} />Тиры</> }, { value: 'table', label: <><Ti icon={Table2} />Таблица</> }]} />
      </div>
      {tl.error && <ErrorBox error={tl.error} />}
      {tl.data && (
        <div className="meta__info">
          <p className="muted">
            {tl.data.matches.toLocaleString('ru')} ранговых матчей по {tl.data.until}
            {pos && tl.data.bracket && ' · винрейт на позиции и баны — Stratz'}
          </p>
          {/* a new filter keeps the old list on screen until the new one arrives: say so */}
          {tl.isFetching && !tl.isPending && <Loading inline>Обновляю…</Loading>}
        </div>
      )}
      {tl.isPending ? (
        <Loading>Считаю тир-лист…</Loading>
      ) : view === 'tiers' ? (
        <div className="tiers">
          {(['S', 'A', 'B', 'C', 'D'] as const).map((t) => (
            <div key={t} className="tier glass glass--inset">
              <span className={`tier__label tier--${t}`}>{t}</span>
              <div className="tier__heroes">
                {rows
                  .filter((r) => r.tier === t)
                  .sort((a, b) => b.score - a.score)
                  .map((r) => (
                    <span key={r.hero} className="tier__hero" onClick={() => openHero(r.hero)} title={tip(r, heroes?.byId.get(r.hero)?.name)}>
                      <HeroIcon id={r.hero} size="md" />
                      <small className={r.wr >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(r.wr)}</small>
                    </span>
                  ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Герой</th>
                <th>Тир</th>
                {(
                  [
                    ['wr', 'Винрейт', Percent],
                    ['pick_rate', 'Пикрейт', TrendingUp],
                    ['ban_share', 'Доля банов', Ban],
                    ...(pos ? [['pos_wr', `WR на поз ${pos}`, Percent]] : []),
                    ['trend_delta', 'Тренд 7 дн', Activity],
                  ] as [SortKey, string, LucideIcon][]
                ).map(([k, label, icon]) => (
                  <th
                    key={k}
                    className={`is-sortable ${sort === k ? 'is-sorted' : ''}`}
                    onClick={() => setSort(k)}
                    title={k === 'ban_share' ? 'Доля героя среди всех банов на твоём ранге (Stratz). Сортировка — кого банят чаще всех.' : undefined}
                  >
                    <Ti icon={icon} />
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.hero} onClick={() => openHero(r.hero)}>
                  <td className="table__hero">
                    <HeroIcon id={r.hero} size="sm" /> <AttrIcon attr={heroes?.byId.get(r.hero)?.attr ?? ''} size={14} />{' '}
                    {heroes?.byId.get(r.hero)?.name}
                  </td>
                  <td>
                    <span className={`tier-badge tier--${r.tier}`}>{r.tier}</span>
                  </td>
                  <td className={r.wr >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(r.wr)}</td>
                  <td>{fmtPct(r.pick_rate)}</td>
                  <td>{fmtPct(r.ban_share)}</td>
                  {pos ? <td>{fmtPct(r.pos_wr)}</td> : null}
                  <td className="table__trend">
                    <Sparkline values={r.trend.map((t) => t.wr)} />
                    {r.trend_delta != null && <small className={r.trend_delta >= 0 ? 'c-good' : 'c-bad'}>{(r.trend_delta * 100).toFixed(1)}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function tip(r: TierRow, name?: string) {
  return `${name ?? ''}\nвинрейт ${fmtPct(r.wr)} (${r.games.toLocaleString('ru')} игр)\nпикрейт ${fmtPct(r.pick_rate)}${
    r.ban_share != null ? `\nдоля банов ${fmtPct(r.ban_share)}` : ''
  }${r.pos_wr != null ? `\nвинрейт на позиции ${fmtPct(r.pos_wr)}` : ''}`;
}
