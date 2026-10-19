/**
 * «Профиль → Найти игрока»: any player by Friend ID, Steam ID64 or a profile link (Steam, Dotabuff,
 * Stratz, OpenDota). Only what the user typed is looked up — never the players of the current match.
 * A closed profile (no public match data) says so plainly; its rank medal is still shown.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { rankName } from '../lib/ranks';
import { ExternalLink } from './ExternalLink';
import { Empty, ErrorBox, fmtPct, HeroIcon } from './ui';

interface PlayerMatch {
  id: number;
  hero: number | null;
  win: boolean;
  k: number | null;
  d: number | null;
  a: number | null;
  duration: number | null;
  start: number | null;
  gpm: number | null;
  xpm: number | null;
  lh: number | null;
  pos: number | null;
  ranked: boolean;
}
interface Player {
  account_id: number;
  name: string | null;
  avatar: string | null;
  rank_tier: number | null;
  leaderboard: number | null;
  plus: boolean;
  smurf: number | null;
  wins: number | null;
  losses: number | null;
  games: number;
  winrate: number | null;
  heroes: { hero: number; games: number; wins: number }[];
  matches: PlayerMatch[];
  sources: { opendota: boolean; stratz: boolean };
  closed: boolean;
  closed_note?: string;
  found: boolean;
  links: Record<'dotabuff' | 'stratz' | 'opendota' | 'steam', string>;
  errors: string[];
}

const RECENT_KEY = 'player-search-recent';
const POS = ['', 'керри', 'мид', 'оффлейн', 'четвёрка', 'пятёрка'];
const fmtDur = (s: number | null) => (s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : '');
const fmtDate = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';

function loadRecent(): { q: string; name: string | null }[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
  } catch {
    return [];
  }
}

export function PlayerSearch() {
  const qc = useQueryClient();
  const heroes = useHeroes().data;
  const [text, setText] = useState('');
  const [q, setQ] = useState<string | null>(null);
  const [recent, setRecent] = useState(loadRecent);
  const res = useQuery({
    queryKey: ['player', q],
    queryFn: () => api<Player>(`/players/lookup?q=${encodeURIComponent(q!)}`),
    enabled: !!q,
    retry: false,
    staleTime: 10 * 60_000,
  });
  const p = res.data;
  useEffect(() => {
    if (!p) return;
    setRecent((list) => {
      const next = [{ q: String(p.account_id), name: p.name }, ...list.filter((r) => r.q !== String(p.account_id))].slice(0, 8);
      try {
        localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch {
        // private mode: the list just isn't kept
      }
      return next;
    });
  }, [p]);
  const go = (value: string) => {
    const v = value.trim();
    if (!v) return;
    setText(v);
    setQ(v);
  };
  const name = (id: number | null) => (id ? heroes?.byId.get(id)?.name ?? `#${id}` : '?');

  return (
    <div className="psearch">
      <form
        className="psearch__bar"
        onSubmit={(e) => {
          e.preventDefault();
          go(text);
        }}
      >
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Friend ID или ссылка на профиль Steam, Dotabuff, Stratz"
          spellCheck={false}
        />
        <button className="btn btn--accent" type="submit" disabled={!text.trim() || res.isFetching}>
          {res.isFetching ? 'Ищу…' : 'Найти'}
        </button>
      </form>
      {!q && (
        <p className="hint">
          Friend ID — число в профиле Доты («Друзья → Добавить» или под ником). Подойдёт и ссылка на профиль Steam
          (steamcommunity.com/id/… или /profiles/…), Dotabuff, Stratz или OpenDota. Данные — с OpenDota и Stratz; у Dotabuff нет
          открытого API, поэтому он — ссылкой. Ищутся только те, кого ты ввёл сам.
        </p>
      )}
      {!!recent.length && (
        <div className="psearch__recent">
          <span className="muted small">Недавно:</span>
          {recent.map((r) => (
            <button key={r.q} className="chip-btn" onClick={() => go(r.q)} title={r.q}>
              {r.name ?? r.q}
            </button>
          ))}
        </div>
      )}
      {res.error && <ErrorBox error={res.error} />}
      {p && (
        <div className="psearch__result">
          <div className="psearch__head">
            {p.avatar ? <img className="psearch__avatar" src={p.avatar} alt="" /> : <div className="psearch__avatar" />}
            <div className="psearch__who">
              <h3>{p.name ?? `Игрок ${p.account_id}`}</h3>
              <p className="muted small">
                {rankName(p.rank_tier)}
                {p.leaderboard ? ` · #${p.leaderboard} в таблице лидеров` : ''}
                {p.plus ? ' · Dota Plus' : ''} · ID {p.account_id}
              </p>
              {p.games > 0 && (
                <p>
                  <b className={(p.winrate ?? 0) >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(p.winrate)}</b> побед ·{' '}
                  <span className="muted">
                    {p.wins} – {p.losses}, {p.games} матчей
                  </span>
                </p>
              )}
            </div>
            <div className="psearch__links">
              <ExternalLink className="btn btn--sm" href={p.links.dotabuff}>
                Dotabuff
              </ExternalLink>
              <ExternalLink className="btn btn--sm" href={p.links.stratz}>
                Stratz
              </ExternalLink>
              <ExternalLink className="btn btn--sm" href={p.links.opendota}>
                OpenDota
              </ExternalLink>
              <ExternalLink className="btn btn--sm" href={p.links.steam}>
                Steam
              </ExternalLink>
              <button className="btn btn--sm btn--ghost" onClick={() => api<Player>(`/players/lookup?q=${p.account_id}&refresh=true`).then((d) => qc.setQueryData(['player', q], d))}>
                Обновить
              </button>
            </div>
          </div>
          {!p.found && !p.closed_note && <p className="warn small">Такого игрока ни OpenDota, ни Stratz не знают.</p>}
          {p.closed_note && <p className="warn small">{p.closed_note}</p>}
          {p.errors.map((e) => (
            <p key={e} className="muted small">
              {e}
            </p>
          ))}
          {!!p.heroes.length && (
            <>
              <h3 className="section-title">Герои</h3>
              <div className="psearch__heroes">
                {p.heroes.map((h) => (
                  <div key={h.hero} className="psearch__hero" title={name(h.hero)}>
                    <HeroIcon id={h.hero} size="sm" />
                    <span>
                      <b>{h.games}</b> <span className="muted small">игр</span>
                    </span>
                    <span className={h.wins / h.games >= 0.5 ? 'c-good small' : 'c-bad small'}>{fmtPct(h.wins / h.games)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {!!p.matches.length && (
            <>
              <h3 className="section-title">Последние матчи</h3>
              <ul className="mh__list">
                {p.matches.map((m) => (
                  <li key={m.id} className={`mh__row ${m.win ? 'is-win' : 'is-loss'}`}>
                    <span className="mh__hero">{m.hero ? <HeroIcon id={m.hero} size="sm" /> : null}</span>
                    <div className="mh__main">
                      <div className="mh__line">
                        <b>{name(m.hero)}</b>
                        {m.pos && <span className="muted">{POS[m.pos]}</span>}
                        <span className={m.win ? 'c-good' : 'c-bad'}>{m.win ? 'победа' : 'поражение'}</span>
                        <span>
                          {m.k}/{m.d}/{m.a}
                        </span>
                        {m.gpm != null && (
                          <span className="muted">
                            {m.gpm}/{m.xpm} GPM/XPM
                          </span>
                        )}
                        <span className="muted">{fmtDur(m.duration)}</span>
                        {!m.ranked && <span className="muted small">не рейтинг</span>}
                        <span className="muted mh__date">{fmtDate(m.start)}</span>
                        <ExternalLink className="small" href={`https://stratz.com/matches/${m.id}`}>
                          матч
                        </ExternalLink>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {p.found && !p.closed && !p.matches.length && !p.heroes.length && <Empty>Матчей нет.</Empty>}
        </div>
      )}
    </div>
  );
}
