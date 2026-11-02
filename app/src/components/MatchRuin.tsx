/** «Кто заруинил»: the breakdown of one match — every player rated, the ruiner and the MVP named. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Crown, Skull, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { Ti } from './Icons';
import { Empty, ErrorBox, HeroIcon, HowTo, ItemIcon, Loading } from './ui';

interface RuinPlayer {
  hero: number;
  radiant: boolean;
  win: boolean | null;
  name: string | null;
  pos: number | null;
  k: number;
  d: number;
  a: number;
  gpm: number;
  xpm: number;
  nw: number;
  kp: number;
  imp: number | null;
  rating: number;
  parts: Record<string, number>;
  worst: string[];
  best: string[];
  deaths_t: number[];
  tag?: 'ruiner' | 'weakest' | 'mvp' | 'unlucky' | 'carried';
}

interface LaneSide {
  hero: number;
  pos: number | null;
  lh: number | null;
  dn: number | null;
  nw: number | null;
  xp: number | null;
}
interface RuinDetail {
  lanes: { lane: 'top' | 'mid' | 'bot'; radiant: LaneSide[]; dire: LaneSide[]; nw_lead: number | null; ahead: 'radiant' | 'dire' | null }[];
  fights: { start: number | null; end: number | null; died: { radiant: number[]; dire: number[] }; swing: number; lost: 'radiant' | 'dire' | null; absent: number[] }[];
  items: Record<string, { key: string; name: string; minute: number; norm: number | null; late: number | null }[]>;
  mistakes: Record<string, { t: number; kind: string; text: string }[]>;
  map: {
    deaths: { hero: number; radiant: boolean | null; x: number; y: number; n: number; t: number | null }[];
    wards: { hero: number; radiant: boolean | null; kind: 'obs' | 'sen'; x: number; y: number; t: number | null }[];
  };
  objectives: { t: number; kind: 'roshan' | 'tower'; radiant: boolean }[];
}

interface Ruin {
  detail: RuinDetail | null;
  id: number;
  duration: number;
  radiant_win: boolean | null;
  start: number | null;
  gold_adv: number[];
  parsed: boolean;
  sources: string[];
  players: RuinPlayer[];
  parse: { state?: string } | null;
  errors: string[];
  verdict: {
    kind: 'sure' | 'likely' | 'together';
    ruiner: number;
    gap: number;
    mvp: number;
    turn: { lead: number; minute: number } | null;
  } | null;
}

const POS = ['', 'керри', 'мид', 'оффлейн', 'четвёрка', 'пятёрка'];
const PART: Record<string, string> = {
  farm: 'фарм',
  xp: 'опыт',
  fight: 'драки',
  survival: 'выживание',
  objectives: 'строения',
  support: 'саппорт',
  lane: 'линия',
};
const TAG: Record<NonNullable<RuinPlayer['tag']>, { text: string; cls: string }> = {
  ruiner: { text: 'заруинил', cls: 'is-bad' },
  weakest: { text: 'слабее всех', cls: 'is-meh' },
  mvp: { text: 'MVP', cls: 'is-great' },
  unlucky: { text: 'тащил, но проиграл', cls: 'is-good' },
  carried: { text: 'затащили', cls: 'is-meh' },
};

const fmtDur = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const k = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1).replace('.0', '')}k` : String(Math.round(v)));
const tone = (r: number) => (r >= 60 ? 'is-good' : r <= 40 ? 'is-bad' : 'is-meh');

/** A match id from what the user pastes: the number itself or a Dotabuff / OpenDota / Stratz link. */
export function parseMatchId(text: string): number | null {
  const m = text.match(/(\d{8,12})/);
  return m ? Number(m[1]) : null;
}

export function MatchRuin({ initial }: { initial?: number | null }) {
  const [text, setText] = useState(initial ? String(initial) : '');
  const [id, setId] = useState<number | null>(initial ?? null);
  useEffect(() => {
    if (initial) {
      setText(String(initial));
      setId(initial);
    }
  }, [initial]);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['ruin', id],
    enabled: !!id,
    retry: false,
    queryFn: () => api<Ruin>(`/match/${id}/ruin`),
    // the replay is being parsed: the breakdown refines itself
    refetchInterval: (x) => (x.state.data && !x.state.data.parsed && x.state.data.parse?.state === 'queued' ? 60_000 : false),
  });
  const go = () => setId(parseMatchId(text));
  return (
    <div className="ruin">
      <form
        className="ruin__ask"
        onSubmit={(e) => {
          e.preventDefault();
          go();
        }}
      >
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Номер матча или ссылка (Dotabuff, OpenDota, Stratz)"
        />
        <button className="btn btn--accent" type="submit" disabled={!parseMatchId(text)}>
          <Ti icon={Search} />
          Разобрать
        </button>
      </form>
      {!id && <Empty>Вставь номер матча — увидишь, как сыграл каждый из десяти и кто заруинил. Номер есть в истории матчей Доты и в списке «Матчи».</Empty>}
      {q.isLoading && <Loading>Загружаю матч…</Loading>}
      {q.error && <ErrorBox error={q.error} />}
      {q.data && <Breakdown r={q.data} onRefresh={async () => {
        await api(`/match/${id}/ruin?refresh=true`);
        qc.invalidateQueries({ queryKey: ['ruin', id] });
      }} />}
    </div>
  );
}

function Breakdown({ r, onRefresh }: { r: Ruin; onRefresh: () => void }) {
  const heroes = useHeroes().data;
  const name = (h: number) => heroes?.byId.get(h)?.name ?? '';
  const v = r.verdict;
  const ruiner = v && r.players.find((p) => p.hero === v.ruiner);
  const mvp = v && r.players.find((p) => p.hero === v.mvp);
  const [picked, setPicked] = useState<number | null>(null);
  const focus = r.players.find((p) => p.hero === (picked ?? ruiner?.hero)) ?? null;
  return (
    <>
      <div className="ruin__head">
        <b>Матч {r.id}</b>
        {r.radiant_win !== null && <span>{r.radiant_win ? 'победа Сил Света' : 'победа Сил Тьмы'}</span>}
        <span className="muted">{fmtDur(r.duration)}</span>
        <span className="muted small">данные: {r.sources.join(' + ')}</span>
        <button className="btn btn--sm btn--ghost" onClick={onRefresh}>
          Обновить
        </button>
      </div>
      {!r.parsed && (
        <p className="warn small">
          {r.parse?.state === 'unavailable'
            ? 'Запись игры недоступна: разбор по итоговым цифрам, без линии, вардов и времени смертей.'
            : 'Запись игры ещё разбирается (OpenDota, обычно несколько минут): пока оценка по итоговым цифрам, она уточнится сама.'}
        </p>
      )}
      {v && ruiner && (
        <div className={`ruin__verdict ${v.kind === 'together' ? 'is-together' : ''}`}>
          <HeroIcon id={ruiner.hero} />
          <div>
            <b>
              <Ti icon={Skull} />
              {v.kind === 'sure' ? 'Заруинил' : v.kind === 'likely' ? 'Скорее всего заруинил' : 'Проиграли все вместе'}
              {v.kind !== 'together' ? `: ${name(ruiner.hero)}` : ''}
              {ruiner.name && v.kind !== 'together' ? ` (${ruiner.name})` : ''}
            </b>
            <p>
              {v.kind === 'together'
                ? `Явно слабее остальных никого нет. Слабее всех — ${name(ruiner.hero)}, рейтинг ${ruiner.rating}, всего на ${v.gap} ниже следующего.`
                : `Рейтинг ${ruiner.rating} из 100 — на ${v.gap} ниже следующего в команде.`}
              {ruiner.worst.length ? ` ${ruiner.worst.join(' · ')}.` : ''}
            </p>
            {v.turn && (
              <p className="muted small">
                У проигравших было +{k(v.turn.lead)} золота на {v.turn.minute}-й минуте — игру отдали.
              </p>
            )}
          </div>
          {mvp && (
            <div className="ruin__mvp">
              <HeroIcon id={mvp.hero} size="sm" />
              <span>
                <Ti icon={Crown} />
                MVP: {name(mvp.hero)}, {mvp.rating}
              </span>
            </div>
          )}
        </div>
      )}
      {r.gold_adv.length > 2 && (
        <GoldChart adv={r.gold_adv} deaths={focus ? focus.deaths_t : []} who={focus ? name(focus.hero) : ''} radiantWin={r.radiant_win} objectives={r.detail?.objectives ?? []} />
      )}
      {[true, false].map((radiant) => (
        <Team key={String(radiant)} r={r} radiant={radiant} name={name} picked={focus?.hero ?? null} onPick={setPicked} />
      ))}
      {focus && <PlayerDetail p={focus} d={r.detail} name={name} />}
      {r.detail && <Lanes d={r.detail} name={name} />}
      {r.detail && r.detail.fights.length > 0 && <Fights d={r.detail} />}
      {r.detail && (r.detail.map.deaths.length > 0 || r.detail.map.wards.length > 0) && <MatchMap d={r.detail} focus={focus?.hero ?? null} />}
      <HowTo>
        Рейтинг 0–100, где 50 — обычная игра на этом герое. Его складывают фарм, опыт, драки (урон и участие в убийствах),
        выживание, строения, работа саппорта (варды, лечение) и линия против нормы героя. Если есть Stratz, учитывается ещё
        его IMP. Веса зависят от роли: саппорта не судят по фарму, керри — по вардам. Заруинившим называется худший в
        проигравшей команде, только когда он заметно ниже остальных. Статистика не видит вижн, позиционку и сейвы, так что это
        оценка, а не приговор.
      </HowTo>
      {r.errors.length > 0 && <p className="muted small">Не всё загрузилось: {r.errors.join('; ')}</p>}
    </>
  );
}

function Team({ r, radiant, name, picked, onPick }: {
  r: Ruin;
  radiant: boolean;
  name: (h: number) => string;
  picked: number | null;
  onPick: (h: number) => void;
}) {
  const team = r.players.filter((p) => p.radiant === radiant);
  const won = r.radiant_win === null ? null : r.radiant_win === radiant;
  return (
    <div className={`ruin__team ${radiant ? 'is-radiant' : 'is-dire'}`}>
      <h3 className="section-title">
        {radiant ? 'Силы Света' : 'Силы Тьмы'}
        {won !== null && <span className={won ? 'c-good' : 'c-bad'}>{won ? 'победа' : 'поражение'}</span>}
      </h3>
      <ul className="ruin__list">
        {team.map((p) => (
          <li
            key={p.hero}
            className={`ruin__row ${p.tag ? `is-${p.tag}` : ''} ${picked === p.hero ? 'is-picked' : ''}`}
            onClick={() => onPick(p.hero)}
            title="Подробно: ошибки, предметы, смерти"
          >
            <HeroIcon id={p.hero} size="sm" />
            <div className="ruin__who">
              <b>{name(p.hero)}</b>
              <span className="muted small">
                {p.pos ? POS[p.pos] : ''}
                {p.name ? ` · ${p.name}` : ''}
              </span>
            </div>
            <span className="ruin__kda">
              {p.k}/{p.d}/{p.a}
            </span>
            <span className="muted small ruin__eco">
              {p.gpm}/{p.xpm} · {k(p.nw)}
            </span>
            <span className={`ruin__rating ${tone(p.rating)}`} title={Object.entries(p.parts).map(([c, s]) => `${PART[c] ?? c}: ${s}`).join(', ')}>
              <i style={{ width: `${p.rating}%` }} />
              <b>{p.rating}</b>
            </span>
            {p.tag ? <span className={`mh__label ${TAG[p.tag].cls}`}>{TAG[p.tag].text}</span> : <span />}
            <span className="ruin__why small">
              {(p.rating < 50 ? p.worst : p.best).slice(0, 2).join(' · ')}
              {p.imp !== null && <span className="muted"> · IMP {p.imp > 0 ? '+' : ''}{p.imp}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Radiant's gold lead by minute; the ruiner's deaths marked under the axis. */
function GoldChart({ adv, deaths, who, radiantWin, objectives }: {
  adv: number[];
  deaths: number[];
  who: string;
  radiantWin: boolean | null;
  objectives: RuinDetail['objectives'];
}) {
  const W = 640;
  const H = 120;
  const max = Math.max(2000, ...adv.map(Math.abs));
  const x = (i: number) => (i / (adv.length - 1)) * W;
  const y = (v: number) => H / 2 - (v / max) * (H / 2 - 6);
  const line = adv.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const minutes = adv.length - 1;
  return (
    <div className="ruin__chart">
      <div className="muted small">
        Перевес по золоту: выше линии — Силы Света, ниже — Силы Тьмы{deaths.length ? `; красные отметки — смерти: ${who}` : ''}
        {objectives.some((o) => o.kind === 'roshan') ? '; R — Рошан' : ''}.
      </div>
      <svg viewBox={`0 0 ${W} ${H + 10}`} preserveAspectRatio="none" role="img" aria-label="Перевес по золоту">
        <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="ruin__axis" />
        <path d={line} className={`ruin__line ${radiantWin ? 'is-radiant' : 'is-dire'}`} />
        {deaths.map((t, i) => (
          <line key={i} x1={x(t / 60)} x2={x(t / 60)} y1={H + 2} y2={H + 10} className="ruin__death" />
        ))}
        {objectives
          .filter((o) => o.kind === 'roshan' && o.t / 60 <= minutes)
          .map((o, i) => (
            <text key={`r${i}`} x={x(o.t / 60)} y={10} className={`ruin__obj ${o.radiant ? 'is-radiant' : 'is-dire'}`} textAnchor="middle">
              R
            </text>
          ))}
      </svg>
      <div className="ruin__ticks muted small">
        <span>0</span>
        <span>{Math.round(minutes / 2)} мин</span>
        <span>{minutes} мин</span>
      </div>
    </div>
  );
}

const mmss = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
const LANE: Record<string, string> = { top: 'Верхняя', mid: 'Центр', bot: 'Нижняя' };

/** One player in detail: the costly moments with their minute, the big items against top players, the lane. */
function PlayerDetail({ p, d, name }: { p: RuinPlayer; d: RuinDetail | null; name: (h: number) => string }) {
  const mistakes = d?.mistakes[String(p.hero)] ?? [];
  const items = d?.items[String(p.hero)] ?? [];
  return (
    <section className="ruin__player">
      <h3 className="section-title">
        {name(p.hero)}
        {p.name ? ` · ${p.name}` : ''} — рейтинг {p.rating}
      </h3>
      <div className="ruin__parts">
        {Object.entries(p.parts).map(([c, sc]) => (
          <span key={c} className={tone(sc)}>
            <small>{PART[c] ?? c}</small>
            <b>{sc}</b>
          </span>
        ))}
      </div>
      {!d ? (
        <p className="muted small">Ошибки по минутам, предметы и драки появятся, когда OpenDota разберёт запись игры.</p>
      ) : (
        <div className="ruin__cols">
          <div>
            <span className="mys__label">Что стоило игры</span>
            {mistakes.length ? (
              <ul className="ruin__mistakes">
                {mistakes.map((m, i) => (
                  <li key={i}>
                    <code>{mmss(m.t)}</code>
                    <span>{m.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Явных ошибок по цифрам не видно.</p>
            )}
            {(p.worst.length > 0 || p.best.length > 0) && (
              <p className="small ruin__sum">
                {p.best.length > 0 && <span className="c-good">{p.best.join(' · ')}</span>}
                {p.best.length > 0 && p.worst.length > 0 && <br />}
                {p.worst.length > 0 && <span className="c-bad">{p.worst.join(' · ')}</span>}
              </p>
            )}
          </div>
          <div>
            <span className="mys__label">Предметы · минута / у топов</span>
            {items.length ? (
              <ul className="ruin__items">
                {items.map((it) => (
                  <li key={it.key} title={it.name}>
                    <ItemIcon k={it.key} size={22} title={it.name} />
                    <span>{it.name}</span>
                    <b>{Math.round(it.minute)}′</b>
                    <small className={it.late == null ? 'muted' : it.late >= 5 ? 'c-bad' : it.late <= -2 ? 'c-good' : 'muted'}>
                      {it.norm == null ? '—' : `${Math.round(it.norm)}′`}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Больших предметов нет.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function Lanes({ d, name }: { d: RuinDetail; name: (h: number) => string }) {
  const side = (xs: LaneSide[]) =>
    xs.map((x) => (
      <div key={x.hero} className="ruin__lane-hero">
        <HeroIcon id={x.hero} size="sm" />
        <span>{name(x.hero)}</span>
        <small className="muted">
          {x.lh ?? '—'}/{x.dn ?? '—'} · {x.nw != null ? k(x.nw) : '—'}
        </small>
      </div>
    ));
  return (
    <section>
      <h3 className="section-title">Линии к 10-й минуте · добивания/денаи · нетворс</h3>
      <div className="ruin__lanes">
        {d.lanes.map((ln) => (
          <div key={ln.lane} className="ruin__lane">
            <div className="ruin__lane-head">
              <b>{LANE[ln.lane]}</b>
              {ln.nw_lead != null && (
                <span className={ln.ahead === 'radiant' ? 'c-good' : ln.ahead === 'dire' ? 'c-bad' : 'muted'}>
                  {ln.ahead ? `${ln.ahead === 'radiant' ? 'Свет' : 'Тьма'} +${k(Math.abs(ln.nw_lead))}` : 'ровно'}
                </span>
              )}
            </div>
            <div className="ruin__lane-sides">
              <div>{side(ln.radiant)}</div>
              <div>{side(ln.dire)}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Fights({ d }: { d: RuinDetail }) {
  return (
    <section>
      <h3 className="section-title">Драки · {d.fights.length}</h3>
      <table className="table ruin__fights">
        <thead>
          <tr>
            <th>Время</th>
            <th>Умерли у Света</th>
            <th>Умерли у Тьмы</th>
            <th>Золото</th>
            <th>Не пришли (у проигравших)</th>
          </tr>
        </thead>
        <tbody>
          {d.fights.map((f, i) => (
            <tr key={i}>
              <td>{f.start != null ? mmss(f.start) : '—'}</td>
              <td className="ruin__heroes">
                {f.died.radiant.map((h) => (
                  <HeroIcon key={h} id={h} size="xs" />
                ))}
              </td>
              <td className="ruin__heroes">
                {f.died.dire.map((h) => (
                  <HeroIcon key={h} id={h} size="xs" />
                ))}
              </td>
              <td className={f.swing > 0 ? 'c-good' : f.swing < 0 ? 'c-bad' : 'muted'}>
                {f.swing > 0 ? 'Свет +' : f.swing < 0 ? 'Тьма +' : ''}
                {k(Math.abs(f.swing))}
              </td>
              <td className="ruin__heroes">
                {f.absent.map((h) => (
                  <HeroIcon key={h} id={h} size="xs" />
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

/** Deaths and wards on a sketch of the map (OpenDota's cells, about 64..192, y up). */
function MatchMap({ d, focus }: { d: RuinDetail; focus: number | null }) {
  const S = 300;
  const px = (x: number) => ((x - 64) / 128) * S;
  const py = (y: number) => S - ((y - 64) / 128) * S;
  return (
    <section>
      <h3 className="section-title">Карта · смерти и варды</h3>
      <div className="ruin__mapwrap">
        <svg viewBox={`0 0 ${S} ${S}`} className="ruin__map" role="img" aria-label="Карта смертей и вардов">
          <rect width={S} height={S} className="ruin__map-bg" />
          <path d={`M0,${S * 0.3} C${S * 0.3},${S * 0.38} ${S * 0.7},${S * 0.62} ${S},${S * 0.7}`} className="ruin__map-river" />
          <path d={`M${S * 0.06},${S} L${S * 0.06},${S * 0.06} L${S},${S * 0.06}`} className="ruin__map-lane" />
          <path d={`M0,${S * 0.94} L${S * 0.94},${S * 0.94} L${S * 0.94},0`} className="ruin__map-lane" />
          <path d={`M${S * 0.08},${S * 0.92} L${S * 0.92},${S * 0.08}`} className="ruin__map-lane" />
          {d.map.wards.map((w, i) => (
            <rect key={`w${i}`} x={px(w.x) - 2.5} y={py(w.y) - 2.5} width={5} height={5} className={`ruin__ward is-${w.kind}`} />
          ))}
          {d.map.deaths.map((x, i) => (
            <circle
              key={`d${i}`}
              cx={px(x.x)}
              cy={py(x.y)}
              r={x.hero === focus ? 5 : 3.2}
              className={`ruin__dead ${x.radiant ? 'is-radiant' : 'is-dire'} ${x.hero === focus ? 'is-focus' : ''}`}
            />
          ))}
        </svg>
        <ul className="ruin__legend small muted">
          <li>
            <i className="ruin__dot is-radiant" /> смерть игрока Света
          </li>
          <li>
            <i className="ruin__dot is-dire" /> смерть игрока Тьмы
          </li>
          <li>
            <i className="ruin__dot is-focus" /> выбранный игрок
          </li>
          <li>
            <i className="ruin__sq is-obs" /> обычный вард, <i className="ruin__sq is-sen" /> сентри
          </li>
        </ul>
      </div>
    </section>
  );
}
