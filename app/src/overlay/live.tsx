/** What the overlay and its widgets share in a match: the draft request, my hero, the build plan
 * with top players' timings, and the live GSI hints (next item, timers, buyback, pace). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { api } from '../api/client';
import { useBuild, useSettings, useTopTimings, useTopVs } from '../api/hooks';
import type { AbilityInfo, DraftRequest } from '../api/types';
import { ItemIcon, Mins } from '../components/ui';
import { picked, useDraft } from '../state/draft';
import { mmss, NeutralTierLine, NightNote, ObjectivesRow, SkillAnnounce, SkillNow, useElapsed, type NeutralTierNow, type Objectives, type SkillNext } from './InGame';

export function useDraftRequest(): DraftRequest {
  const d = useDraft();
  const settings = useSettings().data;
  return useMemo(
    () => ({
      allies: picked(d.allies),
      enemies: picked(d.enemies),
      bans: d.bans,
      pos: d.pos ?? settings?.pos ?? 1,
      side: d.side,
      use_comfort: d.comfort ?? settings?.use_comfort ?? true,
    }),
    [d.allies, d.enemies, d.bans, d.pos, d.side, d.comfort, settings],
  );
}

/** My hero: GSI knows it; otherwise the ally I clicked, or the only ally. */
export function useMe(req: DraftRequest) {
  const d = useDraft();
  if (d.myHero) return d.myHero;
  if (d.myPick && req.allies.includes(d.myPick)) return d.myPick;
  return req.allies.length === 1 ? req.allies[0]! : null;
}

export interface PlanItem {
  key: string;
  name: string;
  minute: number | null;
  top?: boolean;
}

/** The build the overlay follows: top players' games against this draft (or my lane) when there
 * are some, else the hero's usual build; timings from top players' won games where known. */
export function useBuildPlan() {
  const d = useDraft();
  const req = useDraftRequest();
  const allies = picked(d.allies);
  const me = useMe(req);
  const hero = me ?? allies[0] ?? null;
  const build = useBuild(hero, req.pos ?? 1, req.enemies, true);
  const top = build.data ? (build.data.build.builds[0] ?? build.data.build.approximate) : null;
  // top players' games against a draft like this one: when there are some, their build is the one shown
  const topVs = useTopVs(hero, build.data?.build.pos ?? req.pos ?? 1, req.enemies).data;
  const found = topVs?.found ? topVs : null;
  // no game against the whole draft: top games against my lane (Axe + Lich against my Anti-Mage)
  const laneVs = !found && topVs?.lane?.found ? topVs.lane : null;
  const shownVs = found ?? laneVs;
  const shownBuild = build.data ? (build.data.build.builds[0] ?? build.data.build.approximate) : null;
  const skillOrder = shownBuild ? [...shownBuild.skills].sort((a, b) => a.level - b.level) : [];
  // timings: top players' won games on the hero (a good pace) when there are enough, else the build's own
  const tt = useTopTimings(hero, build.data?.build.pos ?? req.pos ?? 1).data;
  const raw = shownVs ? [...(shownVs.boots ? [shownVs.boots] : []), ...(shownVs.core ?? [])] : top ? [...(top.boots ? [top.boots] : []), ...top.core] : [];
  const plan = raw.map((it) => {
    const t = tt?.items[it.key];
    return { key: it.key, name: it.name, minute: t?.minute ?? it.minute, top: !!t || !!shownVs };
  });
  const at = (key: string, fallback: number | null | undefined) => tt?.items[key]?.minute ?? fallback ?? 0;
  const ab: Record<string, AbilityInfo> = build.data?.build.abilities ?? {};
  const pos = build.data?.build.pos ?? req.pos ?? 1;
  return { d, req, allies, me, hero, build, top, topVs, found, laneVs, shownVs, plan: plan as PlanItem[], skillOrder, ab, at, pos };
}

export interface Pace {
  networth: { minute: number; now: number; top: number; diff: number; ratio: number; games: number; estimated: boolean; verdict: 'bad' | 'ok' | 'good' } | null;
  last_hits: { minute: number; last_hits: number; per_min: number; median: number | null; expected: number | null; percentile: number | null; few: boolean } | null;
}

export interface GameLive {
  pace: Pace | null;
  live: {
    clock: number | null;
    gold: number | null;
    gpm: number | null;
    daytime: boolean | null;
    paused?: boolean;
    has_items: boolean;
    has_abilities?: boolean;
    neutral?: string | null;
    alive: boolean | null;
    respawn: number | null;
  } | null;
  skill?: SkillNext | null;
  neutral_tier?: NeutralTierNow | null;
  objectives?: Objectives | null;
  timers: { key: string; name: string; in: number }[];
  next: { key: string; name: string; cost: number; left: number; missing: number; ready: boolean; have: string[] } | null;
  passed?: { key: string; name: string; why: 'skipped' | 'later' | 'replaced'; by?: string; by_name?: string }[];
  buyback: { cost: number; enough: boolean; missing: number; cooldown: number } | null;
}


/** Net worth against the top players of the hero at this minute, and few last hits (backend pace.py). */
export function PaceLines({ pace }: { pace: Pace }) {
  const nw = pace.networth;
  const lh = pace.last_hits;
  const fmt = (n: number) => n.toLocaleString('ru');
  return (
    <div className="ov__pace">
      {nw && (
        <p className={`small ${nw.verdict === 'bad' ? 'c-bad' : nw.verdict === 'good' ? 'c-good' : 'muted'}`} title={`по ${nw.games} играм топов на этом герое${nw.estimated ? '; нетворс оценён по GPM' : ''}`}>
          {nw.verdict === 'bad' ? 'Нетворс ниже топов' : nw.verdict === 'good' ? 'Нетворс выше топов' : 'Нетворс как у топов'}: {nw.estimated ? '≈ ' : ''}
          {fmt(nw.now)} к {nw.minute}-й минуте, у них {fmt(nw.top)} ({nw.diff > 0 ? '+' : ''}
          {Math.round((nw.ratio - 1) * 100)}%)
        </p>
      )}
      {lh?.few && (
        <p className="small c-bad" title="сравнение с игроками этого героя по данным OpenDota">
          Мало добиваний: {lh.last_hits} к {lh.minute}-й минуте ({lh.per_min.toLocaleString('ru')} в минуту)
          {lh.expected ? `, обычно около ${lh.expected}` : ''}
        </p>
      )}
    </div>
  );
}

/** The live GSI hints, refreshed every second: `plan` is the build's item order, `order` its skill order. */
export function useGameLive(plan: PlanItem[], order: { key: string }[], pos: number) {
  const targets = plan.map((p) => p.key).join(',');
  const skills = order.map((s) => s.key).join(',');
  return useQuery({
    queryKey: ['game-live', targets, skills, pos],
    queryFn: () => api<GameLive>(`/game/live?targets=${encodeURIComponent(targets)}&skills=${encodeURIComponent(skills)}&pos=${pos}`),
    refetchInterval: 500,
  });
}

/** The next item of the build: gold missing, a bar, when at my pace and when top players have it. */
export function NextItem({ g, plan, size = 36 }: { g: GameLive; plan: PlanItem[]; size?: number }) {
  if (!g.live) return null;
  const clock = g.live.clock ?? 0;
  const n = g.next;
  if (!n)
    return g.live.has_items ? (
      plan.length > 0 ? <p className="hint">Весь кор билда уже собран.</p> : null
    ) : (
      <p className="hint">Дота пока не присылает предметы: перезапусти её один раз (конфиг GSI обновлён).</p>
    );
  const planned = plan.find((p) => p.key === n.key);
  const minute = planned?.minute ?? null;
  const late = minute != null ? Math.floor(clock / 60 - minute) : 0;
  const pct = Math.round((100 * (n.cost - n.left + Math.min(g.live.gold ?? 0, n.left))) / Math.max(1, n.cost));
  // when the item is affordable at the current gold per minute (Dota's GPM is the match average)
  const eta = !n.ready && g.live.gpm ? clock + (n.missing / g.live.gpm) * 60 : null;
  const replaced = (g.passed ?? []).filter((p) => p.why === 'replaced').slice(-1)[0];
  return (
    <div className={`ov__next ${n.ready ? 'is-ready' : ''}`}>
      <ItemIcon k={n.key} title={n.name} size={size} />
      <div>
        <span className="ov__next-head">
          <b>{n.name}</b>
          <SkipButton itemKey={n.key} />
        </span>
        {replaced && (
          <span className="small muted">
            {replaced.name} пропущен — собран {replaced.by_name ?? replaced.by}
          </span>
        )}
        <span className="small">
          {n.ready ? 'хватает — можно покупать' : `не хватает ${n.missing.toLocaleString('ru')}`}
          {n.have.length > 0 && ' · часть уже есть'}
        </span>
        <div className="ov__bar">
          <i style={{ width: `${pct}%` }} />
        </div>
        {(minute != null || eta != null) && (
          <span className={`small ${late > 0 || (eta != null && minute != null && eta / 60 > minute + 2) ? 'c-bad' : 'muted'}`}>
            {eta != null && (
              <>
                при твоём темпе ~<Mins m={eta / 60} />
              </>
            )}
            {eta != null && minute != null && ' · '}
            {minute != null && (
              <>
                {planned?.top ? 'у топов к ' : 'обычно к '}
                <Mins m={minute} />
              </>
            )}
            {late > 0 ? ` · опаздываешь на ${late} мин` : ''}
          </span>
        )}
      </div>
    </div>
  );
}

/** «не собираю»: the hint moves on to the build's next item (for this match; Dota can't tell
 * which items the player has given up on). */
function SkipButton({ itemKey }: { itemKey: string }) {
  const qc = useQueryClient();
  const skip = useMutation({
    mutationFn: () => api('/game/skip', { body: { key: itemKey } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-live'] }),
  });
  return (
    <button className="ov-chip ov-chip--x" title="Не собираю этот предмет — показать следующий" onClick={() => skip.mutate()} disabled={skip.isPending}>
      не собираю
    </button>
  );
}

/** `elapsed`: seconds since the hints were fetched, so the timers count down between polls. */
export function TimersRow({ g, max = 4, elapsed = 0 }: { g: GameLive; max?: number; elapsed?: number }) {
  return (
    <div className="ov__timers">
      {g.timers.slice(0, max).map((t) => {
        const left = Math.max(0, Math.round(t.in - elapsed));
        return (
          <span key={t.key} className={`ov__timer ${left <= 15 ? 'is-soon' : ''}`}>
            {t.name} <b>{t.key === 'night' ? `через ${mmss(left)}` : mmss(left)}</b>
          </span>
        );
      })}
    </div>
  );
}

export function Buyback({ g }: { g: GameLive }) {
  if (!g.buyback) return null;
  const b = g.buyback;
  return (
    <p className={`small ${b.cooldown ? 'muted' : b.enough ? 'c-good' : 'c-bad'}`}>
      Выкуп {b.cost.toLocaleString('ru')}: {b.cooldown ? `перезарядка ${mmss(b.cooldown)}` : b.enough ? 'хватает' : `не хватает ${b.missing.toLocaleString('ru')}`}
    </p>
  );
}

export function NightLine({ g, hero, enemies }: { g: GameLive; hero: number | null; enemies: number[] }) {
  const night = g.timers.find((t) => t.key === 'night');
  return <NightNote night={g.live?.daytime === false} nightIn={night && night.name === 'Ночь' ? night.in : null} me={hero} enemies={enemies} />;
}

/** «Сейчас» in the big window: everything above in one block. */
export function LiveHints({ plan, pos, order, ab, hero, enemies }: {
  plan: PlanItem[];
  pos: number;
  order: { level: number; key: string; name: string }[];
  ab: Record<string, AbilityInfo>;
  hero: number | null;
  enemies: number[];
}) {
  const q = useGameLive(plan, order, pos);
  const elapsed = useElapsed(q.dataUpdatedAt);
  const g = q.data;
  if (!g?.live) return <p className="hint">Подсказки появятся, как только Дота пришлёт данные матча.</p>;
  const clock = Math.floor((g.live.clock ?? 0) + (g.live.paused ? 0 : elapsed));
  return (
    <div className="ov__live">
      <div className="ov__live-head">
        <span className="kicker">Сейчас · {mmss(clock)}</span>
        {g.live.gold != null && <span className="ov__gold">{g.live.gold.toLocaleString('ru')} золота</span>}
      </div>
      <SkillAnnounce s={g.skill} order={order} ab={ab} />
      {g.skill && !g.skill.now && <SkillNow s={g.skill} order={order} ab={ab} />}
      {g.live.has_abilities === false && order.length > 0 && (
        <p className="hint">Дота пока не присылает способности: перезапусти её один раз (конфиг GSI обновлён).</p>
      )}
      <NextItem g={g} plan={plan} />
      <TimersRow g={g} elapsed={g.live.paused ? 0 : elapsed} />
      <Buyback g={g} />
      <NightLine g={g} hero={hero} enemies={enemies} />
      {g.neutral_tier && <NeutralTierLine t={g.neutral_tier} hero={hero} pos={pos} held={g.live.neutral ?? null} />}
      {g.objectives && <ObjectivesRow o={g.objectives} />}
      {g.pace && <PaceLines pace={g.pace} />}
    </div>
  );
}
