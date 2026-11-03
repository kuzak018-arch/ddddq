import type { CSSProperties } from 'react';
import { useEffect, useState } from 'react';

import { asset } from '../api/client';
import { useBuild, useHeroes, useHeroPage, useProfile } from '../api/hooks';
import type { HeroPage as HeroPageData, Matchup } from '../api/types';
import { heroArt } from '../components/Chrome';
import { BuildView } from '../components/BuildView';
import { HeroModel, useHeroModel } from '../components/HeroModel';
import { Panel } from '../components/Glass';
import { AttrIcon, PosTag } from '../components/DotaIcons';
import { HeroAbilities } from '../components/HeroAbilities';
import { HeroModeSwitch } from '../components/HeroModeSwitch';
import { HeroSearch } from '../components/HeroSearch';
import { SteamGuides } from '../components/SteamGuides';
import { Empty, ErrorBox, fmtPct, fmtSigned, HeroIcon, Loading, Segmented } from '../components/ui';
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
    <div className={`hero-page ${id ? '' : 'is-empty'}`}>
      <Panel className={`hero-page__head ${p ? 'has-hero' : ''}`} refracting>
        <div className="hero-page__bar">
          <HeroModeSwitch />
          <HeroSearch placeholder="Найти героя…" onPick={(h) => openHero(h.id)} compact />
        </div>
        {!id && <HeroPicks onPick={openHero} />}
        {id && page.isPending && <Loading>Загружаю героя…</Loading>}
        {page.error && <ErrorBox error={page.error} />}
        {p && <HeroHeader p={p} />}
      </Panel>

      {p && (
        <>
          <Panel className="hero-page__matchups">
            <section>
              <h3 className="section-title">Способности</h3>
              {id && <HeroAbilities hero={id} />}
            </section>
            <MatchupList title="Хорош против" rows={p.matchups.counters} />
            <MatchupList title="Его контрят" rows={p.matchups.countered_by} />
            <MatchupList title="Лучшие союзники" rows={p.matchups.synergy} />
            <MatchupList title="Плохо сочетается" rows={p.matchups.anti_synergy} />
          </Panel>
          <Panel className="hero-page__build">
            <div className="panel__head">
              <h2>
                Билд
              </h2>
              <Segmented
                small
                value={buildPos}
                onChange={(v) => setPos(v)}
                options={[1, 2, 3, 4, 5].map((n) => ({
                  value: n,
                  label: <PosTag pos={n} bare={n !== buildPos} />,
                  title: `Позиция ${n}${p.builds_for_positions.includes(n) ? '' : ': на ней почти не играют'}`,
                }))}
              />
            </div>
            {build.isPending && <Empty>Загрузка…</Empty>}
            {build.error && <ErrorBox error={build.error} />}
            {build.data && <BuildView r={build.data.build} vs={[]} />}
            <section className="build__group">
              <h4>
                Руководства Steam
              </h4>
              {id && <SteamGuides hero={id} />}
            </section>
          </Panel>
        </>
      )}
    </div>
  );
}

const ROLES_RU: Record<string, string> = {
  Carry: 'Керри', Support: 'Саппорт', Nuker: 'Нюкер', Disabler: 'Контроль', Jungler: 'Лесник',
  Durable: 'Живучий', Escape: 'Побег', Pusher: 'Пушер', Initiator: 'Инициатор',
};
const ATTR_RU: Record<string, string> = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', all: 'Универсальный' };

/** The hero's header across the page: the model over its scene in the hero's colour, the name,
 * the roles, the numbers and the positions (builds and top games are the mode switch and the tab above). */
function HeroHeader({ p }: { p: HeroPageData }) {
  const color = useHeroModel(p.hero.key).color;
  const best = p.positions.indexOf(Math.max(...p.positions)) + 1;
  return (
    <div className="hero-hdr" style={{ '--glow': color ?? 'var(--accent)' } as CSSProperties}>
      <div className="hero-hdr__scene" style={{ backgroundImage: `url("${heroArt(p.hero.key)}")` }} aria-hidden />
      <div className="hero-hdr__tint" aria-hidden />
      <HeroModel className="hero-hdr__art" heroKey={p.hero.key} heroId={p.hero.id} fallback={asset(p.hero.icon)} animated />
      <div className="hero-hdr__info">
        <p className="hero-hdr__kicker">
          <AttrIcon attr={p.hero.attr} size={18} />
          {ATTR_RU[p.hero.attr]} · {p.hero.attack === 'Melee' ? 'ближний бой' : 'дальний бой'}
        </p>
        <h1 className="hero-hdr__name">{p.hero.name}</h1>
        <p className="muted">{p.hero.ru.slice(0, 3).join(' · ')}</p>
        <div className="hero-hdr__roles">
          {p.hero.roles.map((r) => (
            <span key={r} className="hero-hdr__role">
              {ROLES_RU[r] ?? r}
            </span>
          ))}
        </div>
        <div className="stats hero-hdr__stats">
          <Stat label="Винрейт в мете" value={fmtPct(p.meta_wr)} vs={{ delta: p.meta_wr - 0.5, to: 'к среднему' }} />
          <Stat label="Пикрейт" value={fmtPct(p.pick_rate)} />
          {p.bans && (
            <Stat
              label="Доля банов"
              value={`${fmtPct(p.bans.share)}${p.bans.place ? ` · ${p.bans.place}-й` : ''}`}
              title={
                p.bans.place
                  ? `${p.bans.place}-й по банам из ${p.bans.of} героев на твоём ранге (Stratz). Доля от всех банов, а не процент матчей.`
                  : 'Этого героя на твоём ранге не банят (Stratz)'
              }
            />
          )}
          {p.me && (
            <Stat label="Мои игры" value={`${p.me.games} · ${fmtPct(p.me.wins / p.me.games, 0)}`} vs={{ delta: p.me.wins / p.me.games - 0.5, to: 'к среднему' }} />
          )}
        </div>
      </div>
      <div className="hero-hdr__side">
        <span className="label">Позиции</span>
        <div className="posbars">
          {p.positions.map((s, i) => (
            <div key={i} className={`posbar ${i + 1 === best ? 'is-best' : ''}`} title={`Позиция ${i + 1}: ${fmtPct(s)} игр`}>
              <small>{Math.round(s * 100)}%</small>
              <div className="posbar__fill" style={{ height: `${Math.max(4, s * 100)}%` }} />
              <PosTag pos={i + 1} className="posbar__tag" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** A figure, neutral; colour only on the comparison under it, which says what it is compared to. */
function Stat({ label, value, vs, title }: { label: string; value: string; vs?: { delta: number; to: string }; title?: string }) {
  return (
    <div className="stat" title={title}>
      <span className="stat__label">{label}</span>
      <span className="stat__value">{value}</span>
      {vs && (
        <small className={`stat__vs ${vs.delta >= 0 ? 'c-good' : 'c-bad'}`}>
          {fmtSigned(vs.delta * 100)}% {vs.to}
        </small>
      )}
    </div>
  );
}

function MatchupList({ title, rows }: { title: string; rows: Matchup[] }) {
  const openHero = useUi((s) => s.openHero);
  const heroes = useHeroes().data;
  return (
    <section className="matchups">
      <h3 className="section-title" title="Насколько меняется шанс на победу против этого героя (или вместе с ним) по сравнению с обычным шансом без этой пары">
        {title} <small className="muted">· % к обычному шансу</small>
      </h3>
      <ul className="matchups__rows">
        {rows.map((r) => (
          <li key={r.hero} onClick={() => openHero(r.hero)} title={`${r.games.toLocaleString('ru')} игр`}>
            <HeroIcon id={r.hero} size="sm" />
            <span className="matchups__name">{heroes?.byId.get(r.hero)?.name}</span>
            <small className="muted">{r.games.toLocaleString('ru')}</small>
            <b className={r.delta >= 0 ? 'c-good' : 'c-bad'}>{fmtSigned(r.delta)}%</b>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Empty hero page: the user's most played heroes, then every hero by attribute, one click away. */
function HeroPicks({ onPick }: { onPick: (id: number) => void }) {
  const pool = useProfile().data?.heroes.slice(0, 8) ?? [];
  const heroes = useHeroes().data;
  const groups: { attr: string; name: string }[] = [
    { attr: 'str', name: 'Сила' },
    { attr: 'agi', name: 'Ловкость' },
    { attr: 'int', name: 'Интеллект' },
    { attr: 'all', name: 'Универсальные' },
  ];
  return (
    <div className="hero-picks">
      {pool.length > 0 && (
        <>
          <h3 className="section-title">
            Твои герои
          </h3>
          <div className="hero-picks__list">
            {pool.map((h) => (
              <button key={h.hero} className="hero-picks__item tilt" data-tilt="8" onClick={() => onPick(h.hero)}>
                <HeroIcon id={h.hero} size="sm" />
                <span>{heroes?.byId.get(h.hero)?.name}</span>
                <small className="muted">{h.games}</small>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="all-heroes">
        {groups.map((g) => (
          <section key={g.attr}>
            <h3 className="section-title">
              <AttrIcon attr={g.attr} size={18} className="title-attr" />
              {g.name}
            </h3>
            <div className="all-heroes__grid">
              {heroes?.heroes
                .filter((h) => h.attr === g.attr)
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((h) => (
                  <button key={h.id} className="all-heroes__item tilt" data-tilt="14" onClick={() => onPick(h.id)} title={h.name}>
                    <HeroIcon id={h.id} size="md" />
                  </button>
                ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
