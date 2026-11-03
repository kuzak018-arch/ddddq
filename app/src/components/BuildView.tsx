/**
 * Whole builds from real purchase sequences: tabs per build, exact starting set, then the early
 * items, ONE boots choice, the core and the boots upgrade as one timeline with minutes (top players'
 * where known) and "or" alternatives, situational items, skill order by level and talents.
 */
import { createContext, useContext, useEffect, useState } from 'react';

import { useTopTimings } from '../api/hooks';
import type { AbilityInfo, Build, BuildEntry, BuildsResponse, VsItem } from '../api/types';
import { AbilityIcon, TalentIcon } from './Ability';
import { byMinute, clock, ItemTimeline, type TimelineStep } from './ItemTimeline';
import { NeutralItems } from './NeutralItems';
import { Tip } from './Tip';
import { fmtPct, ItemIcon, Segmented } from './ui';

/** Top players' timings for the hero shown (won games of this patch): they replace the bracket's
 * slower medians where known; the bracket's minute stays in the tooltip. */
const TopTimes = createContext<Record<string, { minute: number; n: number }> | undefined>(undefined);

/** Early items, boots, core and the boots upgrade as one timeline by minute. */
function Timings({ b }: { b: Build }) {
  const top = useContext(TopTimes);
  const step = (e: BuildEntry): TimelineStep => {
    const t = top?.[e.key];
    const usual = e.minute != null ? `обычно на твоём ранге к ${clock(e.minute)}` : '';
    return {
      key: e.key,
      name: e.name,
      minute: t ? t.minute : e.minute,
      share: e.share,
      title: t ? `у топов в выигранных играх (${t.n})${usual ? `; ${usual}` : ''}` : usual,
      alternatives: e.alternatives,
    };
  };
  const all = [...b.early, ...(b.boots ? [b.boots] : []), ...b.core, ...(b.boots_upgrade ? [b.boots_upgrade] : [])];
  const anyTop = !!top && all.some((e) => top[e.key]);
  return (
    <section className="build__group">
      <h4>
        Предметы по времени{' '}
        <span className="muted">· {anyTop ? 'минуты у топов в выигранных играх, где их нет — обычно на твоём ранге' : 'минуты — обычно на твоём ранге'}</span>
      </h4>
      <ItemTimeline steps={byMinute(all.map(step))} />
    </section>
  );
}

function AbilityTip({ info, name, extra }: { info?: AbilityInfo; name: string; extra?: string }) {
  return (
    <>
      <b className="tip__title">{info?.name ?? name}</b>
      {info?.innate && <span className="tip__tag">врождённая</span>}
      {info?.desc && <p>{info.desc}</p>}
      {extra && <p className="tip__meta">{extra}</p>}
    </>
  );
}

/** Skill order by hero level as ability icons; talent levels marked with the talent glyph.
 * `size`: icon size (the overlay uses a smaller strip without the legend). */
export function Skills({ b, ab, size = 30, legend = true }: { b: Build; ab: Record<string, AbilityInfo>; size?: number; legend?: boolean }) {
  if (b.skills.length) {
    const keys = [...new Set(b.skills.map((s) => s.key))].filter((k) => k !== 'talent');
    return (
      <div className="bv__skills">
        <ol className="skill-strip">
          {b.skills.map((s) => (
            <li key={s.level}>
              {s.key === 'talent' ? (
                <Tip content={<AbilityTip name="Талант" extra={`Уровень ${s.level}: здесь берут талант (${fmtPct(s.share, 0)}). Какой — в «Талантах» ниже.`} />}>
                  <span className="skill-strip__cell is-talent" tabIndex={0}>
                    <TalentIcon size={size} />
                  </span>
                </Tip>
              ) : (
                <Tip content={<AbilityTip info={ab[s.key]} name={s.name} extra={`Уровень ${s.level} · так качают ${fmtPct(s.share, 0)} игр`} />}>
                  <span className={`skill-strip__cell k${keys.indexOf(s.key) % 5}`} tabIndex={0}>
                    <AbilityIcon info={ab[s.key]} name={s.name} size={size} />
                  </span>
                </Tip>
              )}
              <small>{s.level}</small>
            </li>
          ))}
        </ol>
        {legend && <div className="skill-legend">
          {keys.map((k, i) => {
            const s = b.skills.find((x) => x.key === k)!;
            return (
              <Tip key={k} content={<AbilityTip info={ab[k]} name={s.name} />}>
                <span className={`skill-legend__item k${i % 5}`} tabIndex={0}>
                  <AbilityIcon info={ab[k]} name={s.name} size={20} />
                  {ab[k]?.name ?? s.name}
                </span>
              </Tip>
            );
          })}
        </div>}
      </div>
    );
  }
  return (
    <ol className="build__skills">
      {(b.skill_order ?? []).map((s) => (
        <li key={s.key}>
          <Tip content={<AbilityTip info={ab[s.key]} name={s.name} />}>
            <span className="skill-order__icon" tabIndex={0}>
              <AbilityIcon info={ab[s.key]} name={s.name} size={Math.min(26, size)} />
            </span>
          </Tip>
          <span>
            <b>{ab[s.key]?.name ?? s.name}</b> <span className="muted">первый уровень на {s.first_level}, максимум к {s.max_level}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Talent tree: level in the middle, the two options on its sides with the ability they upgrade. */
function Talents({ b, ab }: { b: Build; ab: Record<string, AbilityInfo> }) {
  return (
    <div className="talents">
      {[...b.talents].reverse().map((t) => (
        <div key={t.level} className="talent">
          {t.options.map((o, i) => {
            const target = o.ability ? ab[o.ability] : undefined;
            const share = t.enough ? `Берут в ${fmtPct(o.share, 0)} игр` : `Мало данных: талант на ${t.level} уровне выбран всего в ${t.picks} играх`;
            return (
              <Tip
                key={o.key}
                className={`talent__opt ${i === 0 ? 'is-left' : 'is-right'} ${t.enough && o.share >= 0.5 ? 'is-pop' : ''}`}
                content={
                  <>
                    <b className="tip__title">{o.name}</b>
                    <p>{target ? `Усиливает «${target.name}».` : 'Общий талант: усиливает героя, а не способность.'}</p>
                    <p className="tip__meta">{share}</p>
                  </>
                }
              >
                <span className="talent__body" tabIndex={0}>
                  {target ? <AbilityIcon info={target} size={22} /> : <TalentIcon size={22} />}
                  <span className="talent__text">
                    {o.name}
                    <small>{t.enough ? fmtPct(o.share, 0) : 'мало данных'}</small>
                  </span>
                </span>
              </Tip>
            );
          })}
          <span className="talent__lvl">{t.level}</span>
        </div>
      ))}
    </div>
  );
}

function BuildBody({ b, vs, reliableGames, ab }: { b: Build; vs: VsItem[]; reliableGames: number; ab: Record<string, AbilityInfo> }) {
  return (
    <div className="build">
      <div className="bv__head">
        <b>{b.title}</b>
        {b.approximate ? (
          <span className="pill warn" title="Нет покупок по матчам: популярность предметов в среднем">
            приблизительно
          </span>
        ) : (
          <span className="muted">
            {b.games} игр · винрейт <b>{fmtPct(b.wr)}</b>
            {!b.reliable && (
              <span className="pill warn" title={`Меньше ${reliableGames} игр — винрейт может сильно ошибаться`}>
                ненадёжно
              </span>
            )}
          </span>
        )}
      </div>

      {vs.length > 0 && (
        <section className="build__vs">
          <h4>Против этого драфта</h4>
          <ul>
            {vs.map((v) => (
              <li key={v.item} className={v.rare_on_hero ? 'is-rare' : ''}>
                <ItemIcon k={v.item} title={v.name} size={30} />
                <div>
                  <b>{v.name}</b>{' '}
                  <span className="muted">
                    {v.in_build
                      ? '— уже в билде, держи в приоритете'
                      : v.rare_on_hero
                        ? '— на этом герое почти не собирают'
                        : v.hero_share
                          ? `— собирают в ${fmtPct(v.hero_share, 0)} игр`
                          : ''}
                  </span>
                  {v.reasons.map((r) => (
                    <p key={r.tag} className="build__why">{r.text}</p>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="build__group">
        <h4>
          Старт {b.starting_share != null && <span className="muted">· ровно так начинают {fmtPct(b.starting_share, 0)}</span>}
        </h4>
        <div className="build__items">
          {b.starting.map((s) => (
            <div key={s.key} className="build__item" title={s.name}>
              <ItemIcon k={s.key} title={s.name} />
              {s.count > 1 && <span className="build__count">×{s.count}</span>}
            </div>
          ))}
        </div>
      </section>

      <Timings b={b} />

      {b.situational.length > 0 && (
        <section className="build__group">
          <h4>Ситуативные</h4>
          <div className="build__items">
            {b.situational.map((it) => (
              <div
                key={it.key}
                className="build__item"
                title={`${it.name}: ${fmtPct(it.share, 0)} игр${it.wr != null ? `, винрейт с ним ${fmtPct(it.wr)}${it.games ? ` (${it.games} игр)` : ''}` : ''}`}
              >
                <ItemIcon k={it.key} title={it.name} />
                <span className="build__meta">{fmtPct(it.share, 0)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="build__group">
        <h4>Прокачка</h4>
        <Skills b={b} ab={ab} />
      </section>

      <section className="build__group">
        <h4>Таланты</h4>
        <Talents b={b} ab={ab} />
      </section>
    </div>
  );
}

export function BuildView({ r, vs }: { r: BuildsResponse; vs: VsItem[] }) {
  const all = r.builds.length ? r.builds : r.approximate ? [r.approximate] : [];
  const [tab, setTab] = useState(0);
  useEffect(() => setTab(0), [r.hero, r.pos, r.mode]);
  const b = all[Math.min(tab, all.length - 1)];
  const tt = useTopTimings(r.hero, r.pos).data;
  return (
    <TopTimes.Provider value={tt && tt.games ? tt.items : undefined}>
    <div className="bv">
      {r.requested_pos && (
        <p className="hint">
          На позиции {r.requested_pos} этого героя почти не играют — билд для позиции {r.pos}.
        </p>
      )}
      {r.status === 'loading' && (
        <div className="bv__loading">
          <span>
            Загружаю матчи из Stratz: {r.progress.have} из {r.target}
            {r.games < r.min_games ? ' — пока показываю приблизительный билд' : ''}
          </span>
          <div className="winbar__track">
            <div className="winbar__fill" style={{ width: `${Math.min(100, (100 * r.progress.have) / r.target)}%` }} />
          </div>
        </div>
      )}
      {r.error && <p className="warn">{r.error}</p>}
      {r.status !== 'loading' && r.note && (
        <p className="muted small">
          Загружено {r.games} из {r.target} матчей. {r.note}
        </p>
      )}
      {all.length > 1 && (
        <Segmented
          small
          value={tab}
          onChange={setTab}
          options={all.map((x, i) => ({ value: i, label: `Билд ${i + 1} · ${fmtPct(x.share, 0)}`, title: x.title }))}
        />
      )}
      {b ? <BuildBody b={b} vs={vs} reliableGames={r.reliable_games} ab={r.abilities ?? {}} /> : <p className="muted">Пока нет данных.</p>}
      <section className="build__group">
        <h4>
          Нейтральные предметы
        </h4>
        <NeutralItems hero={r.hero} pos={r.pos} />
      </section>
    </div>
    </TopTimes.Provider>
  );
}
