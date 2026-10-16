import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '../api/client';
import { useHeroes, useProfile } from '../api/hooks';
import { Glass } from '../components/Glass';
import { Empty, ErrorBox, fmtPct, fmtSigned, HeroIcon } from '../components/ui';
import { useUi } from '../state/ui';

const RANKS = ['', 'Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];
const rankName = (t: number | null) => (t ? `${RANKS[Math.floor(t / 10)]} ${t % 10}` : 'нет ранга');
const pp = (logit: number) => (1 / (1 + Math.exp(-logit)) - 0.5) * 100;

export function ProfilePage() {
  const prof = useProfile();
  const heroes = useHeroes().data;
  const openHero = useUi((s) => s.openHero);
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: () => api('/me/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const p = prof.data;
  const exp = p?.experience;

  return (
    <div className="profile">
      <Glass className="panel profile__head" refracting>
        <div className="panel__head">
          <h2>Профиль</h2>
          <button className="btn" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? 'Загружаю…' : 'Обновить историю'}
          </button>
        </div>
        {prof.error && <ErrorBox error={prof.error} />}
        {refresh.error && <ErrorBox error={refresh.error} />}
        {p && (
          <div className="me">
            {p.avatar && <img className="me__avatar" src={p.avatar} alt="" />}
            <div>
              <h1>{p.name ?? p.account_id}</h1>
              <p className="muted">
                {rankName(p.rank_tier)} · рейтинговый All Pick: {p.overall?.games ?? 0} игр, {fmtPct(p.overall?.wr)} побед
              </p>
            </div>
          </div>
        )}
        {exp && (
          <div className="exp">
            <h3 className="section-title">Твоя кривая опыта на героях</h3>
            <p className="muted">
              Подогнана на {exp.games} твоих играх: насколько реже ты выигрываешь на герое, на котором мало играл.
            </p>
            <ExperienceChart A={exp.A} k={exp.k} />
          </div>
        )}
      </Glass>
      <Glass className="panel profile__pool">
        <h3 className="section-title">Пул героев</h3>
        {!p && !prof.error && <Empty>Загрузка…</Empty>}
        {p && (
          <table className="table">
            <thead>
              <tr>
                <th>Герой</th>
                <th>Игр</th>
                <th>Побед</th>
                <th title="Насколько ты играешь лучше или хуже ожидаемого при таком опыте">Личный перевес</th>
                <th title="Поправка за опыт: чем больше игр, тем ближе к нулю">Опыт</th>
              </tr>
            </thead>
            <tbody>
              {p.heroes.map((h) => (
                <tr key={h.hero} onClick={() => openHero(h.hero)}>
                  <td className="table__hero">
                    <HeroIcon id={h.hero} size="sm" /> {heroes?.byId.get(h.hero)?.name}
                  </td>
                  <td>{h.games}</td>
                  <td className={h.wins / h.games >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(h.wins / h.games, 0)}</td>
                  <td className={h.edge >= 0 ? 'c-good' : 'c-bad'}>{fmtSigned(pp(h.edge))}%</td>
                  <td className="muted">{fmtSigned(pp(h.experience))}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Glass>
    </div>
  );
}

function ExperienceChart({ A, k }: { A: number; k: number }) {
  const W = 420;
  const H = 120;
  const xs = Array.from({ length: 51 }, (_, n) => n);
  const ys = xs.map((n) => pp(-A * (k / (k + n))));
  const lo = Math.min(...ys, -1);
  const x = (n: number) => 30 + (n / 50) * (W - 40);
  const y = (v: number) => 10 + ((0 - v) / (0 - lo)) * (H - 30);
  const d = xs.map((n, i) => `${i ? 'L' : 'M'}${x(n)},${y(ys[i]!)}`).join(' ');
  return (
    <svg className="exp-chart" viewBox={`0 0 ${W} ${H}`} width="100%">
      <line x1={30} x2={W - 10} y1={y(0)} y2={y(0)} className="exp-chart__axis" />
      {[0, 10, 20, 30, 40, 50].map((n) => (
        <text key={n} x={x(n)} y={H - 4} textAnchor="middle">
          {n}
        </text>
      ))}
      <text x={2} y={y(lo) + 4}>{lo.toFixed(0)}%</text>
      <text x={8} y={y(0) + 4}>0</text>
      <path d={d} className="exp-chart__line" />
      <text x={W - 10} y={H - 16} textAnchor="end" className="muted">
        игр на герое →
      </text>
    </svg>
  );
}
