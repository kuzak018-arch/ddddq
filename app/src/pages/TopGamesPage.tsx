/**
 * «Игры топов»: a hero's current-patch matches by Immortal / Divine+ players (Stratz) and pros
 * (OpenDota). On top a summary over the filtered matches (winrate, median timings of key items, the
 * most frequent builds), then the matches; a match opens into its purchase timeline, the skill build
 * by level and the net worth curve. Loaded when the hero is opened and cached by the backend; it never
 * looks at the user's current match.
 */
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import type { AbilityInfo } from '../api/types';
import { AbilityIcon, TalentIcon } from '../components/Ability';
import { Panel } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { Empty, ErrorBox, HeroIcon, ItemIcon, Loading, plural, Segmented, Toggle } from '../components/ui';
import { clock, coreTimings, filterMatches, skillLevels, summarize, type TopMatch } from '../lib/topgames';
import { useDraft } from '../state/draft';
import { useUi } from '../state/ui';

type Source = 'immortal' | 'divine' | 'pro';

interface TopResponse {
  hero_id: number;
  source: Source;
  label: string;
  patch: string;
  matches: TopMatch[];
  fetched: number | null;
  loading: boolean;
  requests: number;
  error: string | null;
  note: string | null;
  core: string[];
  item_names: Record<string, string>;
  abilities: Record<string, AbilityInfo>;
  talents: Record<string, string>;
}

const POS = ['', 'Керри', 'Мид', 'Оффлейн', 'Роумер', 'Саппорт'];
const RANKS: Record<number, string> = { 8: 'Immortal', 7: 'Divine', 6: 'Ancient', 5: 'Legend' };
const fmt = (n: number | null | undefined) => (n == null ? '—' : n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) : '');

export function TopGamesPage() {
  const ui = useUi();
  const heroes = useHeroes().data;
  const myPos = useDraft((s) => s.pos);
  const [hero, setHero] = useState<number | null>(ui.heroPageId);
  const [source, setSource] = useState<Source>('immortal');
  const [pos, setPos] = useState<number | null>(myPos);
  const [winsOnly, setWinsOnly] = useState(false);
  const [against, setAgainst] = useState<number | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const data = useQuery({
    queryKey: ['top-games', hero, source],
    queryFn: () => api<TopResponse>(`/top-games/${hero}?source=${source}`),
    enabled: hero != null,
    // while the backend is loading, ask again: matches come in as they arrive
    refetchInterval: (q) => (q.state.data?.loading ? 2000 : false),
    staleTime: 60_000,
  });
  const d = data.data;
  const core = useMemo(() => new Set(d?.core ?? []), [d?.core]);
  const list = useMemo(() => (d ? filterMatches(d.matches, { pos, winsOnly, against }) : []), [d, pos, winsOnly, against]);
  const sum = useMemo(() => summarize(list, core), [list, core]);
  const h = hero != null ? heroes?.byId.get(hero) : null;
  const name = (k: string) => d?.item_names[k] ?? k;

  return (
    <div className="top">
      <Panel className="top__head">
        <div className="top__bar">
          <div className="top__hero">
            {h ? <HeroIcon id={h.id} size="md" /> : null}
            <div className="top__search">
              <HeroSearch compact placeholder={h ? `${h.name} — сменить героя` : 'Выбери героя: «ам», «пудж», «вр»…'} onPick={(x) => (setHero(x.id), setOpen(null))} />
            </div>
          </div>
          <Segmented
            value={source}
            onChange={(s) => (setSource(s), setOpen(null))}
            options={[
              { value: 'immortal', label: 'Immortal' },
              { value: 'divine', label: 'Divine+' },
              { value: 'pro', label: 'Про' },
            ]}
          />
        </div>
        <div className="top__filters">
          <Segmented
            small
            value={pos ?? 0}
            onChange={(v) => setPos(v || null)}
            options={[{ value: 0, label: 'Все позиции' }, ...[1, 2, 3, 4, 5].map((p) => ({ value: p, label: String(p), title: POS[p] }))]}
          />
          <Toggle on={winsOnly} onChange={setWinsOnly} label="Только победы" />
          <div className="top__against">
            {against != null ? (
              <button className="chip-btn" onClick={() => setAgainst(null)} title="Убрать фильтр">
                против <HeroIcon id={against} size="xs" /> ✕
              </button>
            ) : (
              <HeroSearch compact placeholder="Против героя…" onPick={(x) => setAgainst(x.id)} />
            )}
          </div>
        </div>
        {!hero && <Empty>Выбери героя — покажу его матчи у топов за текущий патч.</Empty>}
        {hero && d && (
          <div className="top__sum">
            <div className="top__stat">
              <b>{sum.count}</b>
              <span>{plural(sum.count, 'матч', 'матча', 'матчей')}</span>
            </div>
            <div className="top__stat">
              <b className={sum.winrate == null ? '' : sum.winrate >= 0.5 ? 'c-good' : 'c-bad'}>{sum.winrate == null ? '—' : `${(sum.winrate * 100).toFixed(0)}%`}</b>
              <span>побед</span>
            </div>
            <div className="top__stat">
              <b>{sum.duration ? clock(sum.duration) : '—'}</b>
              <span>длительность</span>
            </div>
            <div className="top__timings">
              {sum.items.slice(0, 8).map((i) => (
                <div key={i.key} className="top__timing" title={`${name(i.key)}: в ${Math.round(i.share * 100)}% матчей, медиана ${clock(i.median)}`}>
                  <ItemIcon k={i.key} size={24} />
                  <span>{clock(i.median)}</span>
                </div>
              ))}
            </div>
            {!!sum.builds.length && (
              <div className="top__builds">
                {sum.builds.slice(0, 3).map((b) => (
                  <div key={b.items.join()} className="top__build" title={`${b.count} ${plural(b.count, 'матч', 'матча', 'матчей')}, побед ${b.wins}`}>
                    {b.items.map((k, i) => (
                      <span key={k} className="top__build-step">
                        {i > 0 && <i>›</i>}
                        <ItemIcon k={k} size={20} title={name(k)} />
                      </span>
                    ))}
                    <span className="muted small">
                      {b.count} · {Math.round((b.wins / b.count) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Panel>

      {hero && (
        <Panel className="top__list">
          <div className="panel__head">
            <h2>{d ? `${d.label} · патч ${d.patch}` : 'Матчи'}</h2>
            {d?.loading && <span className="pill">загружаю… запросов: {d.requests}</span>}
            {d && !d.loading && (
              <button className="btn btn--sm btn--ghost" onClick={() => void api(`/top-games/${hero}?source=${source}&refresh=true`).then(() => data.refetch())}>
                Обновить
              </button>
            )}
          </div>
          {data.isPending && <Loading>Загружаю матчи…</Loading>}
          {data.error && <ErrorBox error={data.error} />}
          {d?.error && <ErrorBox error={d.error} />}
          {d?.note && <p className="hint">{d.note}</p>}
          {d && !d.matches.length && !d.loading && !d.error && (
            <Empty>{source === 'pro' ? 'Про-матчей на этом герое в текущем патче не нашлось.' : 'Разобранных матчей топов на этом герое за патч пока нет.'}</Empty>
          )}
          {d && !!d.matches.length && !list.length && <Empty>Под фильтры не подходит ни один матч — ослабь фильтры.</Empty>}
          {!!list.length && (
            <div className="top__line top__cols" aria-hidden>
              <span>Исход</span>
              <span>Игрок</span>
              <span className="top__num">У/С/П</span>
              <span className="top__num">Нетворс</span>
              <span className="top__num">Добито</span>
              <span className="top__num">GPM/XPM</span>
              <span className="top__num">Урон</span>
              <span className="top__num">Время</span>
              <span className="top__items">Предметы и тайминги</span>
            </div>
          )}
          <div className="top__rows">
            {list.map((m) => (
              <MatchRow key={m.m} m={m} d={d!} core={core} open={open === m.m} onToggle={() => setOpen(open === m.m ? null : m.m)} />
            ))}
          </div>
          {d && d.source !== 'pro' && (
            <p className="hint">
              Матчи — топ-игроков героя из таблицы лидеров Stratz ({d.label}), только разобранные и только этого патча. Запросы берегут лимит токена:
              одна загрузка — до 16 запросов, повторное открытие — из кэша.
            </p>
          )}
        </Panel>
      )}
    </div>
  );
}

function MatchRow({ m, d, core, open, onToggle }: { m: TopMatch; d: TopResponse; core: Set<string>; open: boolean; onToggle: () => void }) {
  const timings = coreTimings(m, core);
  const rank = m.rank ? RANKS[Math.floor(m.rank / 10)] : null;
  return (
    <div className={`top__row ${open ? 'is-open' : ''}`}>
      <button className="top__line" onClick={onToggle} aria-expanded={open}>
        <span className={`top__res ${m.w ? 'c-good' : 'c-bad'}`}>{m.w ? 'Победа' : 'Поражение'}</span>
        <span className="top__who">
          <b>{m.name ?? (m.src === 'pro' ? 'Про-игрок' : rank ?? 'Топ-игрок')}</b>
          <span className="muted small">
            {[m.team, m.league, m.pos ? `поз. ${m.pos}` : null, when(m.t)].filter(Boolean).join(' · ')}
          </span>
        </span>
        <span className="top__num" title="Убийства / смерти / помощь">
          {m.k ?? '—'}/{m.d ?? '—'}/{m.a ?? '—'}
        </span>
        <span className="top__num" title="Нетворс">{fmt(m.nw)}</span>
        <span className="top__num" title="Добито / не отдано">
          {m.lh ?? '—'}/{m.dn ?? '—'}
        </span>
        <span className="top__num" title="GPM / XPM">
          {m.gpm ?? '—'}/{m.xpm ?? '—'}
        </span>
        <span className="top__num" title="Урон по героям">{fmt(m.dmg)}</span>
        <span className="top__num" title="Длительность">{m.dur ? clock(m.dur) : '—'}</span>
        <span className="top__items">
          {timings.slice(0, 6).map(([k, t]) => (
            <span key={k} className="top__item" title={`${d.item_names[k] ?? k} — ${clock(t)}`}>
              <ItemIcon k={k} size={22} />
              <small>{clock(t)}</small>
            </span>
          ))}
          {m.neutral && (
            <span className="top__item" title={`Нейтральный: ${d.item_names[m.neutral] ?? m.neutral}`}>
              <ItemIcon k={m.neutral} size={22} />
            </span>
          )}
        </span>
      </button>
      {open && <MatchDetails m={m} d={d} />}
    </div>
  );
}

function MatchDetails({ m, d }: { m: TopMatch; d: TopResponse }) {
  const skills = skillLevels(m.skills);
  return (
    <div className="top__details">
      <div className="top__block">
        <h3>Покупки</h3>
        <div className="top__timeline">
          {[...m.items]
            .sort((a, b) => a[0] - b[0])
            .map(([t, k], i) => (
              <span key={`${k}-${i}`} className="top__buy" title={d.item_names[k] ?? k}>
                <ItemIcon k={k} size={26} />
                <small>{clock(t)}</small>
              </span>
            ))}
        </div>
        {m.final && (
          <div className="top__final">
            <span className="muted small">В конце:</span>
            {m.final.map((k, i) => (k ? <ItemIcon key={i} k={k} size={24} title={d.item_names[k] ?? k} /> : <span key={i} className="top__slot" />))}
          </div>
        )}
      </div>
      <div className="top__block">
        <h3>Прокачка</h3>
        <div className="top__skills">
          {skills.map((s) => (
            <span key={s.level} className="top__skill" title={s.talent ? `Талант: ${d.talents[s.key] ?? s.key}` : (d.abilities[s.key]?.name ?? s.key)}>
              {s.talent ? <TalentIcon size={28} /> : <AbilityIcon info={d.abilities[s.key]} name={s.key} size={28} />}
              <small>{s.level}</small>
            </span>
          ))}
        </div>
        {skills.some((s) => s.talent) && (
          <ul className="top__talents">
            {skills
              .filter((s) => s.talent)
              .map((s) => (
                <li key={s.level}>
                  <span className="muted small">ур. {s.level}</span> {d.talents[s.key] ?? s.key}
                </li>
              ))}
          </ul>
        )}
      </div>
      <div className="top__block">
        <h3>{m.curve_kind === 'gold' ? 'Золото по минутам' : 'Нетворс по минутам'}</h3>
        {m.curve?.length ? <Curve values={m.curve} /> : <p className="hint">Stratz не отдал график для этого матча.</p>}
      </div>
      <div className="top__block">
        <h3>Матч</h3>
        <div className="top__teams">
          <span className="muted small">Союзники</span>
          {m.allies.map((x) => (
            <HeroIcon key={x} id={x} size="sm" />
          ))}
          <span className="muted small">Враги</span>
          {m.enemies.map((x) => (
            <HeroIcon key={x} id={x} size="sm" />
          ))}
        </div>
        <a className="small" href={`https://stratz.com/matches/${m.m}`} target="_blank" rel="noreferrer">
          Матч {m.m} на Stratz
        </a>
      </div>
    </div>
  );
}

/** A small line chart of a per-minute curve, with the minutes and the end value. */
function Curve({ values }: { values: number[] }) {
  const W = 460;
  const H = 120;
  const max = Math.max(1, ...values);
  const pts = values.map((v, i) => [(i / Math.max(1, values.length - 1)) * W, H - (v / max) * (H - 8)] as const);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <svg
      className="top__curve"
      viewBox={`-14 0 ${W + 28} ${H + 18}`}
      onPointerMove={(e) => {
        const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
        setHover(Math.round(((e.clientX - r.left) / r.width) * (values.length - 1)));
      }}
      onPointerLeave={() => setHover(null)}
    >
      <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" />
      {[0, 10, 20, 30, 40, 50, 60].filter((t) => t < values.length).map((t) => (
        <text key={t} x={(t / Math.max(1, values.length - 1)) * W} y={H + 14} fontSize="11" fill="currentColor" opacity="0.6" textAnchor="middle">
          {t}′
        </text>
      ))}
      {hover != null && values[hover] != null && (
        <>
          <line x1={pts[hover][0]} x2={pts[hover][0]} y1={0} y2={H} stroke="currentColor" opacity="0.3" />
          <text x={Math.min(W - 60, pts[hover][0] + 6)} y={14} fontSize="12" fill="currentColor">
            {hover}′: {values[hover].toLocaleString('ru-RU')}
          </text>
        </>
      )}
    </svg>
  );
}
