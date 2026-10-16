import type { Build, BuildItem, VsItem } from '../api/types';
import { fmtPct, ItemIcon } from './ui';

function Items({ title, items, timing = true }: { title: string; items: BuildItem[]; timing?: boolean }) {
  if (!items.length) return null;
  return (
    <section className="build__group">
      <h4>{title}</h4>
      <div className="build__items">
        {items.map((it) => (
          <div key={it.key} className="build__item" title={`${it.name}: покупают в ${fmtPct(it.share, 0)} игр${it.wr != null ? `, винрейт ${fmtPct(it.wr)}` : ''}`}>
            <ItemIcon k={it.key} title={it.name} />
            {it.count && it.count > 1 && <span className="build__count">×{it.count}</span>}
            <span className="build__meta">
              {timing && it.minute != null ? `${Math.round(it.minute)}′` : fmtPct(it.share, 0)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function BuildView({ b, vs }: { b: Build; vs: VsItem[] }) {
  return (
    <div className="build">
      <p className="muted">
        {b.matches.toLocaleString('ru')} матчей на {b.bracket.replace('_', '–').toLowerCase()} за неделю
        {b.hero_wr != null && <> · винрейт {fmtPct(b.hero_wr)}</>}
      </p>
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
      <Items title="Старт" items={b.starting} timing={false} />
      <Items title="Сапоги" items={b.boots} />
      <Items title="Ранние" items={b.early} />
      <Items title="Коровые" items={b.core} />
      <Items title="Ситуативные (по винрейту)" items={b.situational} />
      <section className="build__group">
        <h4>Прокачка</h4>
        <ol className="build__skills">
          {b.skills.map((s) => (
            <li key={s.key}>
              <b>{s.name}</b> <span className="muted">первый уровень на {s.first_level}, максимум к {s.max_level}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="build__group">
        <h4>Таланты</h4>
        <div className="talents">
          {[...b.talents].reverse().map((t) => (
            <div key={t.level} className="talent">
              {t.options.map((o, i) => (
                <span
                  key={o.key}
                  className={`talent__opt ${t.enough && o.share >= 0.5 ? 'is-pop' : ''}`}
                  style={{ order: i === 0 ? 0 : 2 }}
                >
                  {o.name}
                  <small>{t.enough ? fmtPct(o.share, 0) : 'мало данных'}</small>
                </span>
              ))}
              <span className="talent__lvl">{t.level}</span>
            </div>
          ))}
        </div>
      </section>
      {b.facets.length > 0 && (
        <section className="build__group">
          <h4>Facets</h4>
          {b.facets.map((f) => (
            <p key={f.name}>
              <b>{f.title ?? f.name}</b> <span className="muted">{f.description}</span>
            </p>
          ))}
        </section>
      )}
    </div>
  );
}
