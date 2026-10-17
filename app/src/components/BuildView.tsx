/**
 * Whole builds from real purchase sequences: tabs per build, exact starting set, ONE boots choice
 * ("or" alternatives with share), core items in order with median timings and alternatives,
 * situational items, skill order by level and talents from the same games.
 */
import { useEffect, useState } from 'react';

import type { Build, BuildEntry, BuildsResponse, VsItem } from '../api/types';
import { fmtPct, ItemIcon, Segmented } from './ui';

const minute = (m: number | null | undefined) => (m == null ? '' : `${Math.round(m)}′`);

function Alternatives({ alts }: { alts?: BuildEntry[] }) {
  if (!alts?.length) return null;
  return (
    <span className="bv__alts">
      {alts.map((a) => (
        <span key={a.key} className="bv__alt" title={`${a.name}: ${fmtPct(a.share, 0)} игр, ~${Math.round(a.minute ?? 0)} мин`}>
          <i>или</i>
          <ItemIcon k={a.key} title={a.name} size={22} />
          <span>{a.name}</span>
          <small>{fmtPct(a.share, 0)}</small>
        </span>
      ))}
    </span>
  );
}

function Step({ e, index }: { e: BuildEntry; index?: number }) {
  return (
    <li className="bv__step">
      {index != null && <span className="bv__n">{index}</span>}
      <ItemIcon k={e.key} title={e.name} size={30} />
      <span className="bv__step-main">
        <b>{e.name}</b>
        <small className="muted">
          {minute(e.minute)} · {fmtPct(e.share, 0)} игр
        </small>
      </span>
      <Alternatives alts={e.alternatives} />
    </li>
  );
}

/** "Mana Break" -> "MB", "Blink" -> "Bl": two abilities rarely share it. */
const abbr = (name: string) => {
  const w = name.split(/[\s-]+/).filter((x) => /^\p{L}/u.test(x));
  return w.length >= 2 ? (w[0]![0]! + w[1]![0]!).toUpperCase() : name.slice(0, 2);
};

function Skills({ b }: { b: Build }) {
  if (b.skills.length) {
    const names = [...new Set(b.skills.map((s) => s.key))].filter((k) => k !== 'talent');
    return (
      <div className="bv__skills">
        {b.skills.map((s) =>
          s.key === 'talent' ? (
            <span key={s.level} className="bv__skill is-talent" title={`Уровень ${s.level}: талант (${fmtPct(s.share, 0)}) — какой, см. ниже`}>
              <small>{s.level}</small>Т
            </span>
          ) : (
            <span key={s.level} className={`bv__skill a${names.indexOf(s.key) % 5}`} title={`Уровень ${s.level}: ${s.name} (${fmtPct(s.share, 0)})`}>
              <small>{s.level}</small>
              {abbr(s.name)}
            </span>
          ),
        )}
        <div className="bv__skill-legend">
          {names.map((k, i) => (
            <span key={k} className={`a${i % 5}`}>
              {b.skills.find((s) => s.key === k)!.name}
            </span>
          ))}
        </div>
      </div>
    );
  }
  return (
    <ol className="build__skills">
      {(b.skill_order ?? []).map((s) => (
        <li key={s.key}>
          <b>{s.name}</b> <span className="muted">первый уровень на {s.first_level}, максимум к {s.max_level}</span>
        </li>
      ))}
    </ol>
  );
}

function BuildBody({ b, vs, reliableGames }: { b: Build; vs: VsItem[]; reliableGames: number }) {
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
            {b.games} игр · винрейт <b className={(b.wr ?? 0) >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(b.wr)}</b>
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
        <h4>Старт {b.starting_share != null && <span className="muted">· ровно так начинают {fmtPct(b.starting_share, 0)}</span>}</h4>
        <div className="build__items">
          {b.starting.map((s) => (
            <div key={s.key} className="build__item" title={s.name}>
              <ItemIcon k={s.key} title={s.name} />
              {s.count > 1 && <span className="build__count">×{s.count}</span>}
            </div>
          ))}
        </div>
      </section>

      {b.early.length > 0 && (
        <section className="build__group">
          <h4>Ранние</h4>
          <ul className="bv__steps">
            {b.early.map((e) => (
              <Step key={e.key} e={e} />
            ))}
          </ul>
        </section>
      )}

      <section className="build__group">
        <h4>Сапоги</h4>
        <ul className="bv__steps">
          {b.boots && <Step e={b.boots} />}
          {b.boots_upgrade && (
            <li className="bv__step bv__step--up">
              <span className="bv__n">↑</span>
              <ItemIcon k={b.boots_upgrade.key} title={b.boots_upgrade.name} size={30} />
              <span className="bv__step-main">
                <b>позже: {b.boots_upgrade.name}</b>
                <small className="muted">
                  {minute(b.boots_upgrade.minute)} · {fmtPct(b.boots_upgrade.share, 0)} игр
                </small>
              </span>
              <Alternatives alts={b.boots_upgrade.alternatives} />
            </li>
          )}
        </ul>
      </section>

      <section className="build__group">
        <h4>Кор по порядку</h4>
        <ul className="bv__steps">
          {b.core.map((e, i) => (
            <Step key={e.key} e={e} index={i + 1} />
          ))}
        </ul>
      </section>

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
        <Skills b={b} />
      </section>

      <section className="build__group">
        <h4>Таланты</h4>
        <div className="talents">
          {[...b.talents].reverse().map((t) => (
            <div key={t.level} className="talent">
              {t.options.map((o, i) => (
                <span key={o.key} className={`talent__opt ${t.enough && o.share >= 0.5 ? 'is-pop' : ''}`} style={{ order: i === 0 ? 0 : 2 }}>
                  {o.name}
                  <small>{t.enough ? fmtPct(o.share, 0) : 'мало данных'}</small>
                </span>
              ))}
              <span className="talent__lvl">{t.level}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export function BuildView({ r, vs }: { r: BuildsResponse; vs: VsItem[] }) {
  const all = r.builds.length ? r.builds : r.approximate ? [r.approximate] : [];
  const [tab, setTab] = useState(0);
  useEffect(() => setTab(0), [r.hero, r.pos, r.mode]);
  const b = all[Math.min(tab, all.length - 1)];
  return (
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
      {b ? <BuildBody b={b} vs={vs} reliableGames={r.reliable_games} /> : <p className="muted">Пока нет данных.</p>}
    </div>
  );
}
