/** Neutral items in a build: every tier with what drops there, the ones the hero's players hold
 * first (share within the tier), and what each item does in its tooltip. */
import { useQuery } from '@tanstack/react-query';

import { api } from '../api/client';
import { Tip } from './Tip';
import { fmtPct, ItemIcon } from './ui';

export interface NeutralItem {
  key: string;
  name: string;
  tier: number | null;
  abilities: { title: string; type: string; desc: string }[];
  stats: string[];
  cooldown: number | null;
  notes: string | null;
  games: number;
  share: number | null;
  wr: number | null;
  popular: boolean;
}
export interface NeutralsResponse {
  hero: number;
  pos: number | null;
  tiers: { tier: number; minute: number; games: number; items: NeutralItem[] }[];
  enchantments: NeutralItem[];
  enchantment_games: number;
  sources: string[];
}

export function useNeutrals(hero: number | null, pos: number | null) {
  return useQuery({
    queryKey: ['neutrals', hero, pos],
    enabled: !!hero,
    staleTime: 10 * 60_000,
    queryFn: () => api<NeutralsResponse>(`/heroes/${hero}/neutrals${pos ? `?pos=${pos}` : ''}`),
  });
}

const TYPE_RU: Record<string, string> = { active: 'активная', passive: 'пассивная', toggle: 'переключаемая' };

export function NeutralTip({ it, tierGames }: { it: NeutralItem; tierGames?: number }) {
  return (
    <>
      <b className="tip__title">{it.name}</b>
      {it.tier && <span className="tip__tag">тир {it.tier}</span>}
      {it.stats.length > 0 && (
        <ul className="ntip__stats">
          {it.stats.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      )}
      {it.abilities.map((a) => (
        <p key={a.title}>
          <b>{a.title}</b>
          {a.type && <span className="muted"> · {TYPE_RU[a.type] ?? a.type}</span>}
          {it.cooldown && a.type === 'active' && <span className="muted"> · {it.cooldown} с</span>}
          <br />
          {a.desc}
        </p>
      ))}
      {it.notes && <p className="tip__meta">{it.notes}</p>}
      {it.games > 0 && tierGames ? (
        <p className="tip__meta">
          У игроков на герое: {it.games} из {tierGames} игр с предметом этого тира ({fmtPct(it.share ?? 0, 0)})
          {it.wr != null ? `, побед ${fmtPct(it.wr, 0)}` : ''}
        </p>
      ) : null}
    </>
  );
}

/** Full block for the builds and hero pages; `compact` (overlay) shows only the popular ones. */
export function NeutralItems({ hero, pos, compact = false }: { hero: number; pos: number | null; compact?: boolean }) {
  const q = useNeutrals(hero, pos);
  const d = q.data;
  if (!d) return null;
  const anyPopular = d.tiers.some((t) => t.items.some((i) => i.popular));
  if (compact) {
    if (!anyPopular) return null;
    return (
      <>
      <span className="kicker">Нейтральные предметы</span>
      <div className="neutrals neutrals--compact">
        {d.tiers.map((t) => {
          const pop = t.items.filter((i) => i.popular);
          if (!pop.length) return null;
          return (
            <span key={t.tier} className="neutrals__ctier">
              <small className="neutrals__tier">Т{t.tier}</small>
              {pop.map((it) => (
                <Tip key={it.key} content={<NeutralTip it={it} tierGames={t.games} />}>
                  <span className="neutrals__item is-pop" tabIndex={0}>
                    <ItemIcon k={it.key} size={22} />
                  </span>
                </Tip>
              ))}
            </span>
          );
        })}
      </div>
      </>
    );
  }
  return (
    <div className="neutrals">
      <p className="muted small">
        {anyPopular
          ? 'Сначала — что чаще держат игроки на этом герое к концу игры (доля среди игр с предметом этого тира). Наведи на предмет, чтобы прочитать, что он делает.'
          : 'Данных, какие нейтралки берут на этом герое, пока нет — показан весь набор по тирам. Наведи на предмет, чтобы прочитать, что он делает.'}
      </p>
      {d.tiers.map((t) => (
        <div key={t.tier} className="neutrals__row">
          <span className="neutrals__head">
            <b>Тир {t.tier}</b>
            <small className="muted">с {t.minute} мин</small>
          </span>
          <div className="neutrals__items">
            {t.items.map((it) => (
              <Tip key={it.key} content={<NeutralTip it={it} tierGames={t.games} />}>
                <span className={`neutrals__item ${it.popular ? 'is-pop' : ''}`} tabIndex={0}>
                  <ItemIcon k={it.key} size={28} />
                  {it.popular && it.share != null && <small>{fmtPct(it.share, 0)}</small>}
                </span>
              </Tip>
            ))}
          </div>
        </div>
      ))}
      {d.enchantments.length > 0 && (
        <div className="neutrals__row">
          <span className="neutrals__head">
            <b>Зачарования</b>
            <small className="muted">к любому тиру</small>
          </span>
          <div className="neutrals__items">
            {d.enchantments.map((it) => (
              <Tip key={it.key} content={<NeutralTip it={it} tierGames={d.enchantment_games} />}>
                <span className={`neutrals__item ${it.popular ? 'is-pop' : ''}`} tabIndex={0}>
                  <ItemIcon k={it.key} size={24} />
                </span>
              </Tip>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
