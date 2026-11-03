/** Hero page → «Способности»: every ability as the game's tooltip tells it, and the talent tree. */
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../api/client';
import type { AbilityInfo } from '../api/types';
import { AbilityIcon, TalentIcon } from './Ability';
import { Loading } from './ui';

interface AbilityFull {
  key: string;
  name: string;
  icon: string | null;
  innate: boolean;
  ultimate: boolean;
  desc: string;
  notes: string[];
  scepter: string | null;
  shard: string | null;
  cooldown: string | null;
  mana: string | null;
  range: string | null;
  values: { label: string; value: string }[];
}
interface Details {
  abilities: AbilityFull[];
  talents: { level: number; left: string | null; right: string | null }[];
  source: 'valve' | 'opendota';
}

export function HeroAbilities({ hero }: { hero: number }) {
  const q = useQuery({ queryKey: ['hero-abilities', hero], queryFn: () => api<Details>(`/heroes/${hero}/abilities`), staleTime: Infinity });
  const [open, setOpen] = useState<string | null>(null);
  const d = q.data;
  if (q.isLoading) return <Loading>Загружаю способности…</Loading>;
  if (!d) return null;
  const pick = d.abilities.find((a) => a.key === open) ?? d.abilities.find((a) => !a.innate) ?? d.abilities[0];
  return (
    <div className="habs">
      <div className="habs__row" role="tablist">
        {d.abilities.map((a) => (
          <button
            key={a.key}
            role="tab"
            className={`habs__pick ${pick?.key === a.key ? 'is-on' : ''}`}
            onClick={() => setOpen(a.key)}
            title={a.name}
          >
            <AbilityIcon info={a as unknown as AbilityInfo} name={a.name} size={46} />
            <small>{a.innate ? 'врождённая' : a.ultimate ? 'ульта' : ''}</small>
          </button>
        ))}
      </div>
      {pick && <AbilityCard a={pick} />}
      {d.talents.length > 0 && (
        <div className="habs__talents">
          <span className="mys__label">Таланты</span>
          <table className="table habs__tree">
            <tbody>
              {d.talents.map((t) => (
                <tr key={t.level}>
                  <td className="table__hero habs__tl">{t.left}</td>
                  <td className="habs__lvl">
                    <TalentIcon size={18} />
                    {t.level}
                  </td>
                  <td className="table__hero habs__tr">{t.right}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AbilityCard({ a }: { a: AbilityFull }) {
  return (
    <article className="habs__card">
      <header>
        <AbilityIcon info={a as unknown as AbilityInfo} name={a.name} size={56} />
        <div>
          <b>{a.name}</b>
          <span className="muted small">{a.innate ? 'Врождённая способность' : a.ultimate ? 'Ультимейт' : 'Способность'}</span>
        </div>
      </header>
      <p>{a.desc}</p>
      {(a.values.length > 0 || a.cooldown || a.mana || a.range) && (
        <dl className="habs__vals">
          {a.values.map((v) => (
            <div key={v.label}>
              <dt>{v.label}</dt>
              <dd>{v.value}</dd>
            </div>
          ))}
          {a.range && (
            <div>
              <dt>Дальность</dt>
              <dd>{a.range}</dd>
            </div>
          )}
          {a.cooldown && (
            <div>
              <dt>Перезарядка</dt>
              <dd className="habs__cd">{a.cooldown} с</dd>
            </div>
          )}
          {a.mana && (
            <div>
              <dt>Мана</dt>
              <dd className="habs__mana">{a.mana}</dd>
            </div>
          )}
        </dl>
      )}
      {a.scepter && (
        <p className="habs__upgrade">
          <b>Aghanim's Scepter.</b> {a.scepter}
        </p>
      )}
      {a.shard && (
        <p className="habs__upgrade">
          <b>Aghanim's Shard.</b> {a.shard}
        </p>
      )}
      {a.notes.length > 0 && (
        <ul className="habs__notes">
          {a.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
