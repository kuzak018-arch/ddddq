/** Profile → «Статистика»: the user's ranked history read like a stats site (backend me_stats.py). */
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { useUi } from '../state/ui';
import { Empty, ErrorBox, fmtPct, HeroIcon, HowTo, Loading } from './ui';

interface Row {
  games: number;
  wins: number;
  wr: number | null;
}
interface HeroRow extends Row {
  hero: number;
  k: number;
  d: number;
  a: number;
  kda: number;
  last: number;
  recent_games: number;
  recent_wr: number | null;
  trend: number | null;
  minutes: number;
}
interface Stats {
  games: number;
  wins?: number;
  wr?: number | null;
  first?: number;
  last?: number;
  heroes?: HeroRow[];
  when?: {
    hours: (Row & { hour: number })[];
    blocks: (Row & { label: string })[];
    days: (Row & { day: string })[];
    lengths: (Row & { label: string })[];
    best_block: (Row & { label: string }) | null;
    worst_block: (Row & { label: string }) | null;
  };
  tilt?: {
    after_loss: (Row & { streak: number })[];
    after_win: (Row & { streak: number })[];
    session: (Row & { game: number })[];
    advice: string | null;
  };
  party?: {
    solo: Row;
    party: Row;
    peers: (Row & { account_id: number; name: string | null; last: number | null })[];
  };
  matchups?: {
    hard: (Row & { hero: number })[];
    easy: (Row & { hero: number })[];
    with_best: (Row & { hero: number })[];
    with_worst: (Row & { hero: number })[];
  };
  records?: {
    win_streak: number;
    loss_streak: number;
    kills: { value: number; hero: number; match: number };
    longest: { minutes: number; hero: number; match: number; win: boolean };
    avg_minutes: number;
  };
  has_peers?: boolean;
}

type SortKey = 'games' | 'wr' | 'kda' | 'recent_games' | 'last';

const wrCls = (wr: number | null, base = 0.5) => (wr == null ? 'muted' : wr >= base + 0.02 ? 'c-good' : wr <= base - 0.02 ? 'c-bad' : '');
const date = (t: number | null | undefined) => (t ? new Date(t * 1000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '—');
const ago = (t: number) => {
  const d = Math.floor((Date.now() / 1000 - t) / 86400);
  return d <= 0 ? 'сегодня' : d === 1 ? 'вчера' : d < 31 ? `${d} дн. назад` : date(t);
};

export function MyStats({ onAnalyze }: { onAnalyze?: (matchId: number) => void }) {
  const q = useQuery({ queryKey: ['me', 'stats'], queryFn: () => api<Stats>('/me/stats'), retry: false });
  const s = q.data;
  if (q.isLoading) return <Loading>Считаю статистику…</Loading>;
  if (q.error) return <ErrorBox error={q.error} />;
  if (!s || !s.games) return <Empty>Рейтинговых игр в истории пока нет.</Empty>;
  const base = s.wr ?? 0.5;
  return (
    <div className="mys">
      <Overview s={s} onAnalyze={onAnalyze} />
      {s.tilt?.advice && <p className="mys__advice">{s.tilt.advice}</p>}
      <HeroesTable rows={s.heroes ?? []} base={base} />
      <div className="mys__grid">
        {s.when && <When w={s.when} base={base} />}
        {s.tilt && <Tilt t={s.tilt} base={base} />}
        {s.matchups && <Matchups m={s.matchups} base={base} />}
        {s.party && <Party p={s.party} base={base} hasPeers={!!s.has_peers} />}
      </div>
      <HowTo>
        <p>
          Все рейтинговые матчи All Pick из истории OpenDota. Время — по часам этого компьютера. Тренд — винрейт за последние 30 дней против
          более раннего, когда в обоих периодах хотя бы по 5 игр. Сессия — игры с перерывом меньше полутора часов; серия обрывается на
          перерыве. Матчапы — как часто ты выигрываешь, когда этот герой у врагов или у союзников (от 8 игр).
        </p>
      </HowTo>
    </div>
  );
}

function Overview({ s, onAnalyze }: { s: Stats; onAnalyze?: (id: number) => void }) {
  const heroes = useHeroes().data;
  const r = s.records;
  const losses = s.games - (s.wins ?? 0);
  const name = (h: number) => heroes?.byId.get(h)?.name ?? '';
  return (
    <div className="mys__over">
      <Stat label="Матчей" value={s.games.toLocaleString('ru')} sub={`${date(s.first)} – ${date(s.last)}`} />
      <Stat label="Победы" value={fmtPct(s.wr ?? null)} sub={`${s.wins} – ${losses}`} cls={wrCls(s.wr ?? null)} />
      {r && <Stat label="Средняя игра" value={`${r.avg_minutes} мин`} />}
      {r && <Stat label="Лучшая серия" value={`${r.win_streak} побед`} sub={`худшая — ${r.loss_streak} поражений`} />}
      {r && (
        <Stat
          label="Больше всего убийств"
          value={String(r.kills.value)}
          sub={name(r.kills.hero)}
          onClick={onAnalyze ? () => onAnalyze(r.kills.match) : undefined}
        />
      )}
      {r && (
        <Stat
          label="Самая долгая"
          value={`${r.longest.minutes} мин`}
          sub={`${name(r.longest.hero)} · ${r.longest.win ? 'победа' : 'поражение'}`}
          onClick={onAnalyze ? () => onAnalyze(r.longest.match) : undefined}
        />
      )}
    </div>
  );
}

function Stat({ label, value, sub, cls, onClick }: { label: string; value: string; sub?: string; cls?: string; onClick?: () => void }) {
  return (
    <div className={`mys__stat ${onClick ? 'is-link' : ''}`} onClick={onClick} title={onClick ? 'Открыть разбор этого матча' : undefined}>
      <span className="mys__label">{label}</span>
      <b className={cls}>{value}</b>
      {sub && <span className="muted small">{sub}</span>}
    </div>
  );
}

function HeroesTable({ rows, base }: { rows: HeroRow[]; base: number }) {
  const heroes = useHeroes().data;
  const openHero = useUi((s) => s.openHero);
  const [sort, setSort] = useState<SortKey>('games');
  const [all, setAll] = useState(false);
  const sorted = useMemo(() => {
    const r = [...rows];
    r.sort((a, b) => ((b[sort] as number | null) ?? -1) - ((a[sort] as number | null) ?? -1));
    return r;
  }, [rows, sort]);
  const shown = all ? sorted : sorted.slice(0, 15);
  const maxGames = Math.max(1, ...rows.map((r) => r.games));
  const th = (key: SortKey, text: string, title?: string) => (
    <th className={`is-sortable ${sort === key ? 'is-sorted' : ''}`} onClick={() => setSort(key)} title={title}>
      {text}
    </th>
  );
  return (
    <section>
      <h3 className="section-title">Герои · {rows.length}</h3>
      <table className="table mys__heroes">
        <thead>
          <tr>
            <th>Герой</th>
            {th('games', 'Матчи')}
            {th('wr', 'Победы')}
            {th('kda', 'KDA', 'Убийства + помощь на смерть; ниже — средние у/с/п')}
            {th('recent_games', '30 дней', 'Матчи и винрейт за последние 30 дней')}
            <th title="Винрейт за 30 дней против более раннего">Тренд</th>
            <th>Длина</th>
            {th('last', 'Последний')}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.hero} onClick={() => openHero(r.hero)}>
              <td className="table__hero">
                <span className="mys__hero">
                  <HeroIcon id={r.hero} size="sm" />
                  {heroes?.byId.get(r.hero)?.name}
                </span>
              </td>
              <td>
                <span className="mys__bar">
                  <i style={{ width: `${(r.games / maxGames) * 100}%` }} />
                  <span>{r.games}</span>
                </span>
              </td>
              <td className={wrCls(r.wr, base)}>{fmtPct(r.wr)}</td>
              <td>
                {r.kda.toFixed(2)}
                <small className="muted">
                  {' '}
                  {r.k}/{r.d}/{r.a}
                </small>
              </td>
              <td>
                {r.recent_games ? (
                  <>
                    {r.recent_games} <small className={wrCls(r.recent_wr, base)}>{fmtPct(r.recent_wr, 0)}</small>
                  </>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className={r.trend == null ? 'muted' : r.trend >= 0 ? 'c-good' : 'c-bad'}>
                {r.trend == null ? '—' : `${r.trend >= 0 ? '▲' : '▼'} ${Math.abs(r.trend * 100).toFixed(0)}%`}
              </td>
              <td className="muted">{r.minutes} мин</td>
              <td className="muted">{ago(r.last)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 15 && (
        <button className="btn btn--sm btn--ghost" onClick={() => setAll((v) => !v)}>
          {all ? 'Только первые 15' : `Все герои (${rows.length})`}
        </button>
      )}
    </section>
  );
}

/** Win rate by hour: a column per hour, its height the games, its colour the win rate. */
function When({ w, base }: { w: NonNullable<Stats['when']>; base: number }) {
  const max = Math.max(1, ...w.hours.map((h) => h.games));
  return (
    <section>
      <h3 className="section-title">Когда ты играешь</h3>
      <div className="mys__hours">
        {w.hours.map((h) => (
          <span
            key={h.hour}
            className={`mys__hour ${h.games >= 8 ? wrCls(h.wr, base) : 'muted'}`}
            title={`${h.hour}:00–${h.hour + 1}:00 · ${h.games} матчей${h.wr != null ? ` · ${fmtPct(h.wr)} побед` : ''}`}
          >
            <i style={{ height: `${(h.games / max) * 100}%` }} />
          </span>
        ))}
      </div>
      <div className="mys__hours-axis muted small">
        <span>0</span>
        <span>6</span>
        <span>12</span>
        <span>18</span>
        <span>24</span>
      </div>
      <table className="table mys__mini">
        <tbody>
          {w.blocks.map((b) => (
            <MiniRow key={b.label} label={b.label} r={b} base={base} />
          ))}
          {w.lengths.map((b) => (
            <MiniRow key={b.label} label={`игра ${b.label}`} r={b} base={base} />
          ))}
        </tbody>
      </table>
      <div className="mys__days">
        {w.days.map((d) => (
          <span key={d.day} title={`${d.games} матчей`}>
            <small className="muted">{d.day}</small>
            <b className={d.games >= 8 ? wrCls(d.wr, base) : 'muted'}>{d.games ? fmtPct(d.wr, 0) : '—'}</b>
          </span>
        ))}
      </div>
    </section>
  );
}

function Tilt({ t, base }: { t: NonNullable<Stats['tilt']>; base: number }) {
  const lbl = (n: number, one: string, many: string) => (n >= 3 ? `после 3+ ${many}` : n === 2 ? `после 2 ${many}` : `после ${one}`);
  return (
    <section>
      <h3 className="section-title">Серии и тильт</h3>
      <table className="table mys__mini">
        <thead>
          <tr>
            <th>Следующая игра</th>
            <th>Матчи</th>
            <th>Победы</th>
          </tr>
        </thead>
        <tbody>
          {t.after_loss.map((r) => (
            <MiniRow key={`l${r.streak}`} label={lbl(r.streak, 'поражения', 'поражений')} r={r} base={base} />
          ))}
          {t.after_win.map((r) => (
            <MiniRow key={`w${r.streak}`} label={lbl(r.streak, 'победы', 'побед')} r={r} base={base} />
          ))}
          {t.session.map((r) => (
            <MiniRow key={`s${r.game}`} label={r.game >= 4 ? '4-я и дальше за сессию' : `${r.game}-я за сессию`} r={r} base={base} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Matchups({ m, base }: { m: NonNullable<Stats['matchups']>; base: number }) {
  const heroes = useHeroes().data;
  const list = (rows: (Row & { hero: number })[]) =>
    rows.map((r) => (
      <li key={r.hero}>
        <HeroIcon id={r.hero} size="sm" />
        <span>{heroes?.byId.get(r.hero)?.name}</span>
        <b className={wrCls(r.wr, base)}>{fmtPct(r.wr, 0)}</b>
        <small className="muted">{r.games}</small>
      </li>
    ));
  if (!m.hard.length && !m.with_best.length) return null;
  return (
    <section>
      <h3 className="section-title">Матчапы</h3>
      <div className="mys__mu">
        <div>
          <span className="mys__label">Тяжело против</span>
          <ul>{list(m.hard.slice(0, 6))}</ul>
        </div>
        <div>
          <span className="mys__label">Лучше всего с</span>
          <ul>{list(m.with_best.slice(0, 6))}</ul>
        </div>
      </div>
    </section>
  );
}

function Party({ p, base, hasPeers }: { p: NonNullable<Stats['party']>; base: number; hasPeers: boolean }) {
  return (
    <section>
      <h3 className="section-title">Соло и пати</h3>
      <table className="table mys__mini">
        <tbody>
          <MiniRow label="соло" r={p.solo} base={base} />
          <MiniRow label="в пати" r={p.party} base={base} />
        </tbody>
      </table>
      {p.peers.length ? (
        <table className="table mys__mini">
          <thead>
            <tr>
              <th>С кем играешь</th>
              <th>Матчи</th>
              <th>Победы</th>
            </tr>
          </thead>
          <tbody>
            {p.peers.map((x) => (
              <MiniRow key={x.account_id} label={x.name ?? String(x.account_id)} r={x} base={base} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted small">{hasPeers ? 'Нет игроков, с кем сыграно 3+ матча.' : 'Список тиммейтов появится после «Обновить историю».'}</p>
      )}
    </section>
  );
}

function MiniRow({ label, r, base }: { label: string; r: Row; base: number }) {
  return (
    <tr>
      <td className="table__hero">{label}</td>
      <td>{r.games}</td>
      <td className={r.games >= 8 ? wrCls(r.wr, base) : 'muted'}>{r.games ? fmtPct(r.wr) : '—'}</td>
    </tr>
  );
}
