import { useEffect, useState } from 'react';

import { useBuild, useHeroPage } from '../api/hooks';
import type { Matchup } from '../api/types';
import { BuildView } from '../components/BuildView';
import { heroArt } from '../components/Chrome';
import { Panel } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { Empty, ErrorBox, fmtPct, fmtSigned, HeroIcon, Segmented } from '../components/ui';
import { useUi } from '../state/ui';

export function HeroPage() {
  const id = useUi((s) => s.heroPageId);
  const openHero = useUi((s) => s.openHero);
  const page = useHeroPage(id);
  const p = page.data;
  const [pos, setPos] = useState<number | null>(null);
  useEffect(() => setPos(null), [id]);
  const bestPos = p ? p.positions.indexOf(Math.max(...p.positions)) + 1 : 1;
  const buildPos = pos ?? (p?.builds_for_positions.includes(bestPos) ? bestPos : p?.builds_for_positions[0] ?? bestPos);
  const build = useBuild(p ? id : null, buildPos, []);

  return (
    <div className="hero-page">
      <Panel className="hero-page__head" refracting>
        <HeroSearch placeholder="Найти героя…" onPick={(h) => openHero(h.id)} compact />
        {!id && <Empty>Выбери героя: поиск выше или двойной клик по герою в драфте.</Empty>}
        {id && page.isPending && <Empty>Загрузка…</Empty>}
        {page.error && <ErrorBox error={page.error} />}
        {p && (
          <div className="hero-card">
            <div className="hero-card__art" style={{ backgroundImage: `url("${heroArt(p.hero.key)}")` }} />
            <div className="hero-card__info">
              <h1>{p.hero.name}</h1>
              <p className="muted">{p.hero.ru.slice(0, 3).join(' · ')}</p>
              <div className="stats">
                <Stat label="Винрейт в мете" value={fmtPct(p.meta_wr)} good={p.meta_wr >= 0.5} />
                <Stat label="Пикрейт" value={fmtPct(p.pick_rate)} />
                {p.me && (
                  <Stat
                    label="Мои игры"
                    value={`${p.me.games} · ${fmtPct(p.me.wins / p.me.games, 0)}`}
                    good={p.me.wins / p.me.games >= 0.5}
                  />
                )}
              </div>
              <div className="posbars">
                {p.positions.map((s, i) => (
                  <div key={i} className="posbar" title={`Позиция ${i + 1}: ${fmtPct(s)} игр`}>
                    <div className="posbar__fill" style={{ height: `${Math.max(4, s * 100)}%` }} />
                    <span>{i + 1}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Panel>

      {p && (
        <>
          <Panel className="hero-page__matchups">
            <MatchupList title="Хорош против" rows={p.matchups.counters} />
            <MatchupList title="Его контрят" rows={p.matchups.countered_by} />
            <MatchupList title="Лучшие союзники" rows={p.matchups.synergy} />
            <MatchupList title="Плохо сочетается" rows={p.matchups.anti_synergy} />
          </Panel>
          <Panel className="hero-page__build">
            <div className="panel__head">
              <h2>Билд</h2>
              <Segmented
                small
                value={buildPos}
                onChange={(v) => setPos(v)}
                options={[1, 2, 3, 4, 5].map((n) => ({
                  value: n,
                  label: `Поз ${n}`,
                  title: p.builds_for_positions.includes(n) ? '' : 'на этой позиции почти не играют',
                }))}
              />
            </div>
            {build.isPending && <Empty>Загрузка…</Empty>}
            {build.error && <ErrorBox error={build.error} />}
            {build.data && <BuildView b={build.data.build} vs={[]} />}
          </Panel>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      <span className={`stat__value ${good === undefined ? '' : good ? 'c-good' : 'c-bad'}`}>{value}</span>
    </div>
  );
}

function MatchupList({ title, rows }: { title: string; rows: Matchup[] }) {
  const openHero = useUi((s) => s.openHero);
  return (
    <section className="matchups">
      <h3 className="section-title">{title}</h3>
      <ul>
        {rows.map((r) => (
          <li key={r.hero} onClick={() => openHero(r.hero)} title={`${r.games.toLocaleString('ru')} игр`}>
            <HeroIcon id={r.hero} size="sm" />
            <span className={r.delta >= 0 ? 'c-good' : 'c-bad'}>{fmtSigned(r.delta)}%</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
