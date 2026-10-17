/**
 * Lane matchup: who wins the lane (Stratz lane outcomes) and how it goes minute by minute in real
 * matches of the pair: the gap in networth or experience, pressure windows and both heroes' spikes.
 */
import { useEffect, useMemo, useState } from 'react';

import { useHeroes, useLane, useLaneOpponents } from '../api/hooks';
import type { LaneEvent, LanePoint, LaneResponse, LaneWindow } from '../api/types';
import { ErrorBox, fmtPct, HeroIcon, ItemIcon, Segmented } from './ui';

const POS_SHORT = ['', 'керри', 'мид', 'оффлейн', 'четвёрка', 'пятёрка'];
const POS_ACC = ['', 'керри', 'мид', 'оффлейн', 'четвёрку', 'пятёрку'];
const POS_GEN = ['', 'керри', 'мида', 'оффлейна', 'четвёрки', 'пятёрки'];
const BRACKET = (b: string) => (b === 'ALL' ? 'все ранги' : b.replace('_', '–').toLowerCase().replace(/(^|–)\w/g, (m) => m.toUpperCase()));

/** Lane block for a draft: picks the lane opponent among the enemies (main one first). */
export function LaneView({ hero, pos, enemies }: { hero: number | null; pos: number; enemies: number[] }) {
  const heroes = useHeroes().data;
  const opp = useLaneOpponents(pos, enemies, hero).data;
  const [chosen, setChosen] = useState<number | null>(null);
  const list = opp?.opponents ?? [];
  const auto = list.find((o) => o.main)?.hero ?? list.find((o) => o.on_lane)?.hero ?? null;
  const enemy = chosen && enemies.includes(chosen) ? chosen : auto;
  useEffect(() => setChosen(null), [pos, hero]);
  const o = list.find((x) => x.hero === enemy);
  const enemyPos = o ? (o.on_lane ? o.pos : o.lane_pos) : null;
  const lanePos = opp?.pos ?? pos;
  const lane = useLane(hero, lanePos, o && enemyPos ? enemy : null, enemyPos);

  if (!hero) return <p className="muted small">Выбери своего героя, и здесь появится разбор линии.</p>;
  if (!enemies.length) return <p className="muted small">Добавь врагов: соперник по линии подставится сам.</p>;
  const myName = heroes?.byId.get(hero)?.name ?? '';
  return (
    <div className="lane">
      {opp?.requested_pos && (
        <p className="muted small">
          {myName} почти не играет {POS_ACC[opp.requested_pos]}, показываю линию {POS_GEN[opp.pos]}.
        </p>
      )}
      <div className="lane__opps">
        {list.map((x) => (
          <button
            key={x.hero}
            className={`lane__opp ${x.hero === enemy ? 'is-on' : ''} ${x.on_lane ? 'is-lane' : ''} ${x.lane_pos ? '' : 'is-never'}`}
            onClick={() => setChosen(x.hero)}
            title={
              x.on_lane
                ? `На твоей линии (${POS_SHORT[x.pos]})`
                : x.lane_pos
                  ? `Скорее всего ${POS_SHORT[x.pos]}, но может прийти на твою линию как ${POS_SHORT[x.lane_pos]}`
                  : `Скорее всего ${POS_SHORT[x.pos]}, на твоей линии почти не бывает`
            }
          >
            <HeroIcon id={x.hero} size="sm" />
          </button>
        ))}
      </div>
      {opp && !enemy && <p className="muted small">На твоей линии из этих врагов обычно никто не стоит. Выбери соперника вручную.</p>}
      {o && !enemyPos && (
        <p className="muted small">
          {heroes?.byId.get(o.hero)?.name} почти никогда не стоит на линии {POS_GEN[lanePos]}: такой пары на линии не бывает, данных нет.
        </p>
      )}
      {lane.error && <ErrorBox error={lane.error} />}
      {lane.data && !lane.data.off_lane && o && enemyPos ? <LaneBody r={lane.data} /> : null}
    </div>
  );
}

function LaneBody({ r }: { r: LaneResponse }) {
  const heroes = useHeroes().data;
  const me = heroes?.byId.get(r.hero)?.name ?? '';
  const them = heroes?.byId.get(r.enemy)?.name ?? '';
  const a = r.analysis;
  const [metric, setMetric] = useState<'nw' | 'xp'>('nw');
  return (
    <>
      <div className="lane__vs">
        <b>{me}</b> <span className="muted">({POS_SHORT[r.pos]})</span> <span className="muted">против</span> <b>{them}</b>{' '}
        <span className="muted">({POS_SHORT[r.enemy_pos]})</span>
      </div>

      <Outcome r={r} me={me} them={them} />

      {r.status === 'loading' && (
        <div className="lane__loading">
          <span className="muted small">
            Загружаю матчи этой пары: {r.progress.have} из {r.target}
          </span>
          <div className="lane__progress">
            <i style={{ width: `${Math.min(100, (100 * r.progress.have) / r.target)}%` }} />
          </div>
        </div>
      )}
      {r.error && <p className="warn small">{r.error}</p>}
      {r.status !== 'loading' && r.note && (
        <p className="muted small">
          Загружено {r.games} из {r.target}. {r.note}
        </p>
      )}

      {r.rare && r.status !== 'loading' && !a.games ? null : a.curves && a.curves.length > 1 ? (
        <>
          <div className="lane__head">
            <h3 className="section-title">По минутам</h3>
            <Segmented
              small
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'nw', label: 'Золото' },
                { value: 'xp', label: 'Опыт' },
              ]}
            />
          </div>
          <Chart curves={a.curves} windows={(a.windows ?? []).filter((w) => w.metric === metric)} metric={metric} me={me} them={them} />
          <Spikes events={a.events ?? []} horizon={a.curves[a.curves.length - 1]!.minute} r={r} />
          <Story r={r} me={me} them={them} />
          <p className="muted small">
            {a.games} матчей этой пары (Legend+, текущий патч, оба на этих позициях и на одной линии)
            {!a.reliable && <span className="pill warn">мало матчей</span>}. Линия — медиана, полоса — половина игр вокруг неё.
          </p>
        </>
      ) : (
        r.status !== 'loading' && (
          <p className="muted small">
            Матчей этой пары пока {a.games}, для графика нужно {a.min_games}.
          </p>
        )
      )}
    </>
  );
}

function Outcome({ r, me, them }: { r: LaneResponse; me: string; them: string }) {
  const o = r.outcome;
  if (!o) return <p className="muted small">{r.outcome_error ? `Stratz: ${r.outcome_error}` : 'Stratz не знает исходов линии для этой пары.'}</p>;
  if (!o.enough)
    return (
      <div className="lane__outcome">
        <div className="lane__verdict muted">Недостаточно данных</div>
        <p className="muted small">
          У Stratz всего {o.rated} оценённых линий этой пары ({BRACKET(o.bracket)}, за неделю), для вывода нужно хотя бы {o.min_verdict}.
        </p>
      </div>
    );
  const verdict = o.edge >= 0.08 ? `Линию чаще выигрывает ${me}` : o.edge <= -0.08 ? `Линию чаще выигрывает ${them}` : 'Линия примерно ровная';
  return (
    <div className="lane__outcome">
      <div className={`lane__verdict ${o.edge >= 0.08 ? 'c-good' : o.edge <= -0.08 ? 'c-bad' : ''}`}>{verdict}</div>
      <div className="lane__bar" title="Исходы линии с твоей стороны">
        <i className="is-win" style={{ flex: o.win_share }} />
        <i className="is-draw" style={{ flex: o.draw_share }} />
        <i className="is-loss" style={{ flex: o.loss_share }} />
      </div>
      <div className="lane__legend small">
        <span className="c-good">выигрыш {fmtPct(o.win_share, 0)}</span>
        <span className="muted">ничья {fmtPct(o.draw_share, 0)}</span>
        <span className="c-bad">проигрыш {fmtPct(o.loss_share, 0)}</span>
      </div>
      <p className="muted small">
        Разгромы: {o.stomp_win} в твою пользу, {o.stomp_loss} против. Stratz, {BRACKET(o.bracket)}, {o.rated} оценённых линий за неделю
        {!o.reliable && <span className="pill warn">мало</span>}
      </p>
    </div>
  );
}

const W = 420;
const H = 170;
const PAD = { l: 40, r: 8, t: 10, b: 20 };

function Chart({ curves, windows, metric, me, them }: { curves: LanePoint[]; windows: LaneWindow[]; metric: 'nw' | 'xp'; me: string; them: string }) {
  const last = curves[curves.length - 1]!.minute;
  const med = curves.map((c) => c[metric]);
  // scale to the median, so its shape shows; the spread band is clipped at the edges
  const top = Math.max(300, ...med.map((v) => Math.abs(v) * 1.6));
  const x = (m: number) => PAD.l + (m / last) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + ((top - Math.max(-top, Math.min(top, v))) / (2 * top)) * (H - PAD.t - PAD.b);
  const line = curves.map((c, i) => `${i ? 'L' : 'M'}${x(c.minute)},${y(c[metric])}`).join(' ');
  const band =
    curves.map((c, i) => `${i ? 'L' : 'M'}${x(c.minute)},${y(c[`${metric}_hi`])}`).join(' ') +
    ' ' +
    [...curves].reverse().map((c) => `L${x(c.minute)},${y(c[`${metric}_lo`])}`).join(' ') +
    ' Z';
  const tick = top >= 1000 ? Math.round(top / 2 / 100) * 100 : Math.round(top / 2 / 50) * 50;
  return (
    <svg className="lane-chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Разница по минутам">
      {windows.map((w, i) => (
        <rect
          key={i}
          x={x(w.from)}
          y={PAD.t}
          width={x(Math.min(w.to, last)) - x(w.from)}
          height={H - PAD.t - PAD.b}
          className={`lane-chart__win ${w.leader === 'hero' ? 'is-hero' : 'is-enemy'} ${w.sure ? 'is-sure' : ''}`}
        />
      ))}
      <path d={band} className="lane-chart__band" />
      <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="lane-chart__zero" />
      {[tick, -tick].map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="lane-chart__grid" />
          <text x={PAD.l - 4} y={y(v) + 3} textAnchor="end">
            {v > 0 ? '+' : ''}
            {v}
          </text>
        </g>
      ))}
      <text x={PAD.l + 4} y={PAD.t + 10} className="lane-chart__who is-hero">
        ↑ {me} впереди
      </text>
      <text x={PAD.l + 4} y={H - PAD.b - 4} className="lane-chart__who is-enemy">
        ↓ {them} впереди
      </text>
      <path d={line} className="lane-chart__line" />
      {curves.map((c) => (
        <circle key={c.minute} cx={x(c.minute)} cy={y(c[metric])} r={2.4} className="lane-chart__dot">
          <title>
            {c.minute} мин: {c[metric] > 0 ? '+' : ''}
            {c[metric]} {metric === 'nw' ? 'золота' : 'опыта'}, {me} впереди в {fmtPct(c.ahead, 0)} игр
          </title>
        </circle>
      ))}
      {Array.from({ length: last + 1 }, (_, m) => m)
        .filter((m) => m % 3 === 0)
        .map((m) => (
          <text key={m} x={x(m)} y={H - 4} textAnchor="middle">
            {m}′
          </text>
        ))}
    </svg>
  );
}

function Spikes({ events, horizon, r }: { events: LaneEvent[]; horizon: number; r: LaneResponse }) {
  const rows = useMemo(
    () =>
      (['hero', 'enemy'] as const).map((side) => {
        // markers closer than ~1.2 minutes go to the next tier instead of covering each other
        const last: number[] = [];
        const items = events
          .filter((e) => e.side === side && e.minute <= horizon + 0.5)
          .map((e) => {
            let tier = last.findIndex((m) => e.minute - m >= horizon * 0.08);
            if (tier < 0) tier = last.length;
            last[tier] = e.minute;
            return { e, tier };
          });
        return { side, hero: side === 'hero' ? r.hero : r.enemy, items, tiers: Math.max(1, last.length) };
      }),
    [events, horizon, r.hero, r.enemy],
  );
  // same horizontal scale as the chart
  const left = (m: number) => `calc(${(PAD.l / W) * 100}% + ${(m / horizon) * (1 - (PAD.l + PAD.r) / W) * 100}%)`;
  return (
    <div className="lane-spikes">
      {rows.map((row) => (
        <div key={row.side} className={`lane-spikes__row is-${row.side}`} style={{ height: 24 * row.tiers + 2 }}>
          <span className="lane-spikes__who">
            <HeroIcon id={row.hero} size="sm" />
          </span>
          {row.items.map(({ e, tier }) => (
            <span
              key={e.key}
              className={`lane-spikes__ev ${e.spike ? 'is-spike' : ''}`}
              style={{ left: left(e.minute), top: 3 + 24 * tier }}
              title={`${e.name} — ${fmtMinute(e.minute)} (${fmtPct(e.share, 0)} игр)${e.spike && e.window ? `. Оверспайк: после него давление ${e.window.metric === 'nw' ? 'по золоту' : 'по опыту'} ${e.window.from}–${e.window.to} мин` : ''}`}
            >
              {e.kind === 'level' ? <b>{e.key.slice(5)}</b> : <ItemIcon k={e.key} size={16} />}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}

const fmtMinute = (m: number) => `${Math.floor(m)}:${String(Math.round((m % 1) * 60)).padStart(2, '0')}`;

function Story({ r, me, them }: { r: LaneResponse; me: string; them: string }) {
  const a = r.analysis;
  const lines: string[] = [];
  for (const w of a.windows ?? []) {
    const who = w.leader === 'hero' ? me : them;
    lines.push(
      `${w.from}–${w.to} мин: давит ${who} по ${w.metric === 'nw' ? 'золоту' : 'опыту'}, разрыв растёт на ~${w.per_min} в минуту${w.sure ? '' : ' (заметно, но не наверняка)'}` +
        (w.spike ? ` — начинается с: ${w.spike}` : ''),
    );
  }
  const l6 = (side: 'hero' | 'enemy') => a.events?.find((e) => e.side === side && e.key === 'level6');
  const m6 = l6('hero');
  const t6 = l6('enemy');
  return (
    <div className="lane__story">
      {a.at && (
        <p>
          К {a.at.minute}-й минуте обычно: золото {a.at.nw > 0 ? '+' : ''}
          {a.at.nw}, опыт {a.at.xp > 0 ? '+' : ''}
          {a.at.xp} в пользу {a.at.nw >= 0 ? me : them}; {me} впереди по золоту в {fmtPct(a.at.ahead, 0)} игр.
        </p>
      )}
      {m6 && t6 && (
        <p>
          6 уровень: {me} ~{fmtMinute(m6.minute)}, {them} ~{fmtMinute(t6.minute)}
          {Math.abs(m6.minute - t6.minute) >= 0.4 && ` — ${m6.minute < t6.minute ? me : them} раньше`}.
        </p>
      )}
      {lines.length ? (
        <ul>
          {lines.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">Явных окон давления нет: по минутам линия идёт ровно.</p>
      )}
    </div>
  );
}
