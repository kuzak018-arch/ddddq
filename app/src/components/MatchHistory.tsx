/** Profile: recent ranked matches with a one-label estimate of how I played and why. */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { useUi } from '../state/ui';
import { Empty, ErrorBox, HeroIcon } from './ui';

interface MatchRow {
  id: number;
  start: number | null;
  duration: number;
  hero: number;
  pos: number | null;
  win: boolean;
  k: number;
  d: number;
  a: number;
  award: string | null;
  pending?: string;
  label?: string;
  label_key?: string;
  imp?: number;
  reasons?: string[];
  nw_place?: number;
  team_imp?: number;
}

interface History {
  fetched: number | null;
  matches: MatchRow[];
  summary: {
    matches: number;
    rated: number;
    pending: number;
    losses: number;
    losses_me: number;
    losses_team: number;
    losses_together: number;
    wins: number;
    wins_me: number;
    wins_team: number;
    wins_together: number;
  };
  job: { status?: string; step?: string; teams_done?: number; teams_total?: number; error?: string | null };
  good_imp: number;
}

const POS = ['', 'керри', 'мид', 'оффлейн', 'четвёрка', 'пятёрка'];
const TONE: Record<string, string> = {
  carried: 'is-great',
  won_together: 'is-good',
  team_carried: 'is-meh',
  lost_played_well: 'is-good',
  lost_together: 'is-meh',
  threw: 'is-bad',
};

const fmtDur = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const fmtDate = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';

export function MatchHistory() {
  const qc = useQueryClient();
  const heroes = useHeroes().data;
  const openHero = useUi((s) => s.openHero);
  const q = useQuery({
    queryKey: ['me', 'matches'],
    queryFn: () => api<History>('/me/matches'),
    retry: false,
    refetchInterval: (x) => (x.state.data?.job.status === 'loading' ? 3000 : false),
  });
  const h = q.data;
  const s = h?.summary;
  const loading = h?.job.status === 'loading';
  return (
    <div className="mh">
      {q.error && <ErrorBox error={q.error} />}
      {s && s.rated > 0 && (
        <div className="mh__sum">
          <div>
            <b>Поражения: {s.losses}</b>
            <span className="c-bad">скорее виноват я — {s.losses_me}</span>
            <span className="c-good">скорее команда — {s.losses_team}</span>
            <span className="muted">вместе — {s.losses_together}</span>
          </div>
          <div>
            <b>Победы: {s.wins}</b>
            <span className="c-good">вытащил — {s.wins_me}</span>
            <span className="muted">вместе — {s.wins_together}</span>
            <span className="c-bad">затащила команда — {s.wins_team}</span>
          </div>
        </div>
      )}
      <div className="mh__bar">
        <span className="muted small">
          {s ? `Последние ${s.matches} рейтинговых матчей${s.pending ? `, ${s.pending} ещё не разобраны Stratz` : ''}.` : ''}
          {loading && ` Обновляю${h?.job.step === 'teams' ? ` составы: ${h.job.teams_done ?? 0} из ${h.job.teams_total ?? 0}` : '…'}`}
        </span>
        <button
          className="btn btn--sm"
          disabled={loading}
          onClick={async () => {
            await api('/me/matches?refresh=true');
            qc.invalidateQueries({ queryKey: ['me', 'matches'] });
          }}
        >
          Обновить
        </button>
      </div>
      {h?.job.status === 'failed' && h.job.error && <p className="warn small">{h.job.error}</p>}
      {h && !h.matches.length && !loading && <Empty>Матчей пока нет: нужен токен Stratz и аккаунт в настройках.</Empty>}
      <ul className="mh__list">
        {h?.matches.map((m) => (
          <li key={m.id} className={`mh__row ${m.win ? 'is-win' : 'is-loss'}`}>
            <button className="mh__hero" onClick={() => openHero(m.hero)} title="Страница героя">
              <HeroIcon id={m.hero} size="sm" />
            </button>
            <div className="mh__main">
              <div className="mh__line">
                <b>{heroes?.byId.get(m.hero)?.name}</b>
                {m.pos && <span className="muted">{POS[m.pos]}</span>}
                <span className={m.win ? 'c-good' : 'c-bad'}>{m.win ? 'победа' : 'поражение'}</span>
                <span>
                  {m.k}/{m.d}/{m.a}
                </span>
                <span className="muted">{fmtDur(m.duration)}</span>
                <span className="muted mh__date">{fmtDate(m.start)}</span>
              </div>
              {m.label ? (
                <div className="mh__verdict">
                  <span className={`mh__label ${TONE[m.label_key ?? ''] ?? ''}`}>{m.label}</span>
                  <span className="mh__reasons">{m.reasons?.join(' · ')}</span>
                </div>
              ) : (
                <div className="muted small">{m.pending}</div>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="hint">
        Оценка приблизительная. Основа — IMP от Stratz (оценка вклада игрока: 0 — обычная игра на этом герое, «хорошо» от +{h?.good_imp ?? 10},
        «плохо» от −{h?.good_imp ?? 10}); причины — сравнение с нормой героя на этой позиции на твоём ранге. Статистика видит не всё: вижн,
        позиционку, сейвы и размены она почти не замечает, особенно на саппортах.
      </p>
    </div>
  );
}
