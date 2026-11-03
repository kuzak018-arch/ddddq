/** The hero's best Steam Workshop guides (the ones Dota's guide panel shows): the item build by
 * the author's categories and the skill order, with votes, subscribers and the update date. */
import { useQuery } from '@tanstack/react-query';
import { ExternalLink as LinkIcon, RefreshCw } from 'lucide-react';
import { useState } from 'react';

import { api } from '../api/client';
import { AbilityIcon, TalentIcon } from './Ability';
import { ExternalLink } from './ExternalLink';
import { Ti } from './Icons';
import { ItemIcon, Loading } from './ui';

export interface SteamGuide {
  id: string;
  title: string;
  author: string | null;
  url: string;
  subscriptions: number;
  lifetime_subscriptions: number;
  votes_up: number;
  votes_down: number;
  updated: number;
  description: string | null;
  items: { name: string; items: string[] }[];
  abilities: string[];
}
interface GuidesResponse {
  status: 'ok' | 'no_key' | 'error';
  error: string | null;
  guides: SteamGuide[];
  fetched: number | null;
  patch_ts: number;
  item_names?: Record<string, string>;
  diag?: { queried: number; with_file: number; downloaded: number; guides: number; this_hero: number } | null;
}

export function useSteamGuides(hero: number | null, refresh = 0) {
  return useQuery({
    queryKey: ['steam-guides', hero, refresh],
    enabled: !!hero,
    staleTime: 60 * 60_000,
    retry: false,
    queryFn: () => api<GuidesResponse>(`/heroes/${hero}/guides${refresh ? '?refresh=true' : ''}`),
  });
}

const date = (t: number) => new Date(t * 1000).toLocaleDateString('ru', { day: 'numeric', month: 'short', year: 'numeric' });

function Meta({ g, patch }: { g: SteamGuide; patch: number }) {
  const votes = g.votes_up + g.votes_down;
  return (
    <span className="muted small">
      {g.author ?? 'автор скрыт'} · обновлено {date(g.updated)}
      {g.updated < patch && <b className="c-bad"> · до текущего патча</b>}
      {votes > 0 && ` · 👍 ${Math.round((100 * g.votes_up) / votes)}% из ${votes.toLocaleString('ru')}`}
      {g.subscriptions > 0 && ` · подписчиков ${g.subscriptions.toLocaleString('ru')}`}
    </span>
  );
}

function GuideBody({ g, size = 30, names = {} }: { g: SteamGuide; size?: number; names?: Record<string, string> }) {
  return (
    <>
      {g.items.map((c, i) => (
        <div key={`${c.name}${i}`} className="sguide__cat">
          <span className="label">{c.name}</span>
          <div className="sguide__items">
            {c.items.map((k, j) => (
              <ItemIcon key={`${k}${j}`} k={k} title={names[k] ?? k} size={size} />
            ))}
          </div>
        </div>
      ))}
      {g.abilities.length > 0 && (
        <div className="sguide__cat">
          <span className="label">Прокачка</span>
          <ol className="sguide__skills">
            {g.abilities.map((k, i) => (
              <li key={i}>
                {k.startsWith('special_bonus') ? <TalentIcon size={size - 8} /> : <AbilityIcon name={k} info={{ key: k, name: k, desc: '', innate: false, icon: `/icons/abilities/${k}.png` }} size={size - 8} />}
                <small>{i + 1}</small>
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

export function SteamGuides({ hero }: { hero: number }) {
  const [refresh, setRefresh] = useState(0);
  const [open, setOpen] = useState(0);
  const q = useSteamGuides(hero, refresh);
  const d = q.data;
  if (q.isPending) return <Loading>Ищу руководства в мастерской Steam…</Loading>;
  if (q.error) return <p className="muted small">{(q.error as Error).message}</p>;
  if (!d) return null;
  if (d.status === 'no_key')
    return (
      <p className="muted small">
        Чтобы показать лучшие руководства из мастерской Steam, нужен бесплатный ключ Steam Web API: открой{' '}
        <ExternalLink href="https://steamcommunity.com/dev/apikey">steamcommunity.com/dev/apikey</ExternalLink>
        , в поле «домен» впиши что угодно (например localhost), и вставь ключ в Настройки → Аккаунт.
      </p>
    );
  const g = d.guides[Math.min(open, d.guides.length - 1)];
  return (
    <div className="sguide">
      {d.status === 'error' && <p className="warn">{d.error}{d.guides.length ? ' — показаны сохранённые' : ''}</p>}
      {!d.guides.length && d.status === 'ok' && (
        <p className="muted small">
          В мастерской не нашлось руководств с билдом для этого героя.
          {d.diag && (
            <>
              {' '}
              <span title="Что нашёл Steam на каждом шаге: если пришлёшь эту строку, будет видно, где теряются руководства">
                (Steam: найдено {d.diag.queried}, с файлом {d.diag.with_file}, скачано {d.diag.downloaded}, руководств {d.diag.guides}, на героя {d.diag.this_hero})
              </span>
            </>
          )}
        </p>
      )}
      {d.guides.length > 1 && (
        <div className="sguide__tabs">
          {d.guides.map((x, i) => (
            <button key={x.id} className={`chip ${i === open ? 'is-on' : ''}`} onClick={() => setOpen(i)} title={x.title}>
              {i + 1}. {x.title.length > 28 ? `${x.title.slice(0, 27)}…` : x.title}
            </button>
          ))}
        </div>
      )}
      {g && (
        <>
          <div className="sguide__head">
            <b>{g.title}</b>
            <span className="sguide__actions">
              <ExternalLink className="btn btn--sm btn--ghost" href={g.url}>
                <Ti icon={LinkIcon} />
                В Steam
              </ExternalLink>
              <button className="btn btn--sm btn--ghost" onClick={() => setRefresh(Date.now())} title="Проверить мастерскую заново">
                <Ti icon={RefreshCw} />
              </button>
            </span>
          </div>
          <Meta g={g} patch={d.patch_ts} />
          {g.description && <p className="muted small sguide__desc">{g.description}</p>}
          <GuideBody g={g} names={d.item_names} />
        </>
      )}
    </div>
  );
}

/** Overlay: the best guide's build only, small, when there is one. */
export function SteamGuideCompact({ hero }: { hero: number }) {
  const d = useSteamGuides(hero).data;
  const g = d?.guides[0];
  if (!g) return null;
  return (
    <>
      <span className="kicker" title={`${g.title} · ${g.author ?? ''}`}>
        Руководство Steam · {g.title.length > 34 ? `${g.title.slice(0, 33)}…` : g.title}
      </span>
      <div className="sguide sguide--compact">
        <GuideBody g={{ ...g, items: g.items.slice(0, 4), abilities: [] }} size={20} names={d?.item_names} />
      </div>
    </>
  );
}
