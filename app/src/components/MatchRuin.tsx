/** «Кто заруинил»: the breakdown of one match — every player rated, the ruiner and the MVP named. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Crown, Skull, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { Ti } from './Icons';
import { Empty, ErrorBox, HeroIcon, Loading } from './ui';

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

interface Ruin {
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
      {r.gold_adv.length > 2 && <GoldChart adv={r.gold_adv} deaths={ruiner && v?.kind !== 'together' ? ruiner.deaths_t : []} radiantWin={r.radiant_win} />}
      {[true, false].map((radiant) => (
        <Team key={String(radiant)} r={r} radiant={radiant} name={name} />
      ))}
      <p className="hint">
        Рейтинг 0–100, где 50 — обычная игра на этом герое. Его складывают фарм, опыт, драки (урон и участие в убийствах),
        выживание, строения, работа саппорта (варды, лечение) и линия против нормы героя. Если есть Stratz, учитывается ещё
        его IMP. Веса зависят от роли: саппорта не судят по фарму, керри — по вардам. Заруинившим называется худший в
        проигравшей команде, только когда он заметно ниже остальных. Статистика не видит вижн, позиционку и сейвы, так что это
        оценка, а не приговор.
      </p>
      {r.errors.length > 0 && <p className="muted small">Не всё загрузилось: {r.errors.join('; ')}</p>}
    </>
  );
}

function Team({ r, radiant, name }: { r: Ruin; radiant: boolean; name: (h: number) => string }) {
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
          <li key={p.hero} className={`ruin__row ${p.tag ? `is-${p.tag}` : ''}`}>
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
function GoldChart({ adv, deaths, radiantWin }: { adv: number[]; deaths: number[]; radiantWin: boolean | null }) {
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
        Перевес по золоту: выше линии — Силы Света, ниже — Силы Тьмы{deaths.length ? '; красные отметки — смерти заруинившего' : ''}.
      </div>
      <svg viewBox={`0 0 ${W} ${H + 10}`} preserveAspectRatio="none" role="img" aria-label="Перевес по золоту">
        <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="ruin__axis" />
        <path d={line} className={`ruin__line ${radiantWin ? 'is-radiant' : 'is-dire'}`} />
        {deaths.map((t, i) => (
          <line key={i} x1={x(t / 60)} x2={x(t / 60)} y1={H + 2} y2={H + 10} className="ruin__death" />
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
