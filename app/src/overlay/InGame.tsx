/** In-match pieces of the overlay: the skill to take now, the neutral tier, Roshan and the
 * Tormentor (with kill buttons), the night note, the draft's win chance strip and «Враги». */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import { useEvaluate, useHeroes, usePlan } from '../api/hooks';
import type { AbilityInfo, DraftRequest } from '../api/types';
import { AbilityIcon, TalentIcon } from '../components/Ability';
import { useNeutrals } from '../components/NeutralItems';
import { NeutralTip } from '../components/NeutralItems';
import { Tip } from '../components/Tip';
import { fmtPct, HeroIcon, ItemIcon } from '../components/ui';

export const mmss = (s: number) => `${s < 0 ? '-' : ''}${Math.floor(Math.abs(s) / 60)}:${String(Math.abs(Math.round(s)) % 60).padStart(2, '0')}`;

export interface SkillNext {
  key: string;
  at: number;
  points: number;
  now: boolean;
}
export interface NeutralTierNow {
  tier: number | null;
  ago: number | null;
  next: number | null;
  in: number | null;
}
export interface Objectives {
  roshan: { source: 'dota' | 'mark' | 'none'; state: 'alive' | 'maybe' | 'dead'; in?: number | null; aegis?: number | null; pit: 'top' | 'bottom' | null };
  tormentor: { source: 'mark' | 'none'; state: 'alive' | 'dead'; in: number | null; side: 'radiant' | 'dire' };
  night: boolean;
}

/** «Качай: Blink» when a point is free, else the next one by the build. */
export function SkillNow({ s, order, ab }: { s: SkillNext; order: { level: number; key: string; name: string }[]; ab: Record<string, AbilityInfo> }) {
  const lvl = order[s.at - 1]?.level ?? s.at;
  const info = ab[s.key];
  const name = s.key === 'talent' ? 'талант' : (info?.name ?? order[s.at - 1]?.name ?? s.key);
  return (
    <div className={`ov__skillnow ${s.now ? 'is-now' : ''}`}>
      {s.key === 'talent' ? <TalentIcon size={28} /> : <AbilityIcon info={info} name={name} size={28} />}
      <span>
        {s.now ? (
          <>
            <b>Качай: {name}</b>
            {s.points > 1 && <span className="muted small"> · свободных очков {s.points}</span>}
          </>
        ) : (
          <span className="small">
            Следующий скилл на {lvl} ур.: <b>{name}</b>
          </span>
        )}
      </span>
    </div>
  );
}

/** «Качай: …» that slides in when a point is free and, once the skill is taken, says so for a
 * moment and slides away (it used to pop in and vanish at once). */
export function SkillAnnounce({ s, order, ab }: { s: SkillNext | null | undefined; order: { level: number; key: string; name: string }[]; ab: Record<string, AbilityInfo> }) {
  const now = s?.now ? s : null;
  const last = useRef<SkillNext | null>(null);
  const [done, setDone] = useState<SkillNext | null>(null);
  useEffect(() => {
    if (now) {
      last.current = now;
      setDone(null);
      return;
    }
    if (last.current) {
      setDone(last.current);
      last.current = null;
      const t = setTimeout(() => setDone(null), 1300);
      return () => clearTimeout(t);
    }
  }, [now?.key, now?.at, !!now]);  // eslint-disable-line react-hooks/exhaustive-deps
  const show = now ?? done;
  const name = (k: SkillNext) => (k.key === 'talent' ? 'талант' : (ab[k.key]?.name ?? order[k.at - 1]?.name ?? k.key));
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div
          key={`${show.key}-${show.at}`}
          className={`ov__skillnow ${now ? 'is-now' : 'is-done'}`}
          initial={{ opacity: 0, y: 14, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.97, transition: { duration: 0.25 } }}
          transition={{ type: 'spring', stiffness: 420, damping: 28 }}
        >
          {show.key === 'talent' ? <TalentIcon size={28} /> : <AbilityIcon info={ab[show.key]} name={name(show)} size={28} />}
          <span>
            {now ? (
              <>
                <b>Качай: {name(show)}</b>
                {now.points > 1 && <span className="muted small"> · свободных очков {now.points}</span>}
              </>
            ) : (
              <b>✓ {name(show)}</b>
            )}
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Seconds since `updatedAt` (ms), ticking 4 times a second: the clock and timers move between polls. */
export function useElapsed(updatedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);
  return Math.max(0, Math.min(2, (now - updatedAt) / 1000));
}

/** The neutral tier: just opened (with the hero's popular items) or when the next one opens. */
export function NeutralTierLine({ t, hero, pos, held }: { t: NeutralTierNow; hero: number | null; pos: number; held: string | null }) {
  const d = useNeutrals(hero, pos).data;
  const fresh = t.tier != null && t.ago != null && t.ago < 120;
  const row = fresh ? d?.tiers.find((x) => x.tier === t.tier) : undefined;
  const pop = row?.items.filter((i) => i.popular) ?? [];
  const heldItem = held ? d?.tiers.flatMap((x) => x.items).find((i) => i.key === held) : undefined;
  return (
    <div className="ov__ntier small">
      {fresh ? (
        <b>Открылся тир {t.tier} нейтралок</b>
      ) : t.next ? (
        <span className="muted">
          Тир {t.next} нейтралок через {mmss(t.in ?? 0)}
        </span>
      ) : (
        <span className="muted">Открыты все тиры нейтралок</span>
      )}
      {pop.length > 0 && (
        <span className="ov__ntier-items">
          {pop.map((it) => (
            <Tip key={it.key} content={<NeutralTip it={it} tierGames={row?.games} />}>
              <span tabIndex={0}>
                <ItemIcon k={it.key} size={18} />
              </span>
            </Tip>
          ))}
        </span>
      )}
      {held && (
        <span className="ov__ntier-held" title="В слоте нейтралки">
          {heldItem ? (
            <Tip content={<NeutralTip it={heldItem} />}>
              <span tabIndex={0}>
                <ItemIcon k={held} size={18} />
              </span>
            </Tip>
          ) : (
            <ItemIcon k={held} size={18} />
          )}
        </span>
      )}
    </div>
  );
}

/** Roshan and the Tormentor with «убит» buttons; Dota's own Roshan state when it sends one. */
export function ObjectivesRow({ o }: { o: Objectives }) {
  const qc = useQueryClient();
  const mark = useMutation({
    mutationFn: (body: { kind: 'roshan' | 'tormentor'; undo?: boolean }) => api('/game/mark', { body }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-live'] }),
  });
  const r = o.roshan;
  const t = o.tormentor;
  const pit = r.pit === 'top' ? 'верхнее логово' : r.pit === 'bottom' ? 'нижнее логово' : null;
  const rText =
    r.state === 'alive'
      ? `жив${pit ? ` · ${pit}` : ''}`
      : r.state === 'maybe'
        ? `может быть жив${r.in != null ? ` · точно через ${mmss(r.in)}` : ''}`
        : `мёртв${r.in != null ? ` · появится не раньше чем через ${mmss(r.in)}` : ''}`;
  const tText = t.state === 'alive' ? `жив · сторона ${t.side === 'radiant' ? 'Света' : 'Тьмы'}` : `через ${mmss(t.in ?? 0)} · сторона ${t.side === 'radiant' ? 'Света' : 'Тьмы'}`;
  return (
    <div className="ov__obj">
      <div className={`ov__obj-row ${r.state === 'alive' ? 'is-up' : ''}`}>
        <span className="small">
          <b>Рошан</b> {rText}
          {r.aegis != null && <span> · аегис ещё {mmss(r.aegis)}</span>}
          {r.source === 'dota' && <span className="muted"> · по Доте</span>}
        </span>
        {r.source !== 'dota' &&
          (r.source === 'mark' ? (
            <button className="ov-chip" onClick={() => mark.mutate({ kind: 'roshan', undo: true })} title="Отменить отметку">
              ×
            </button>
          ) : (
            <button className="ov-chip" onClick={() => mark.mutate({ kind: 'roshan' })} title="Отметить, что Рошана убили сейчас">
              убит
            </button>
          ))}
      </div>
      <div className={`ov__obj-row ${t.state === 'alive' ? 'is-up' : ''}`}>
        <span className="small">
          <b>Терзатель</b> {tText}
        </span>
        {t.source === 'mark' ? (
          <button className="ov-chip" onClick={() => mark.mutate({ kind: 'tormentor', undo: true })} title="Отменить отметку">
            ×
          </button>
        ) : (
          t.state === 'alive' && (
            <button className="ov-chip" onClick={() => mark.mutate({ kind: 'tormentor' })} title="Отметить, что Терзателя убили сейчас">
              убит
            </button>
          )
        )}
      </div>
    </div>
  );
}

// ---------- the enemies' abilities ---------------------------------------------------------------

export interface Threat {
  key: string;
  name: string;
  icon: string | null;
  ultimate: boolean;
  cooldown: string | null;
  pierces: boolean;
  dispel: string | null;
  tags: string[];
  desc: string;
}
export interface HeroThreats {
  hero: number;
  abilities: Threat[];
  night: boolean;
}

export function useThreats(ids: number[]) {
  const key = [...ids].sort((a, b) => a - b).join(',');
  return useQuery({
    queryKey: ['threats', key],
    enabled: ids.length > 0,
    staleTime: Infinity,
    queryFn: () => api<{ heroes: HeroThreats[] }>(`/heroes/threats?ids=${key}`),
  });
}

/** «Ночь через 0:40 — Night Stalker (враг) сильнее ночью». */
export function NightNote({ night, nightIn, me, enemies }: { night: boolean; nightIn: number | null; me: number | null; enemies: number[] }) {
  const heroes = useHeroes().data;
  const th = useThreats([...(me ? [me] : []), ...enemies]).data;
  const who = (th?.heroes ?? []).filter((h) => h.night);
  if (!who.length) return null;
  const names = who.map((h) => `${heroes?.byId.get(h.hero)?.name ?? ''}${h.hero === me ? ' (ты)' : ' (враг)'}`).join(', ');
  return (
    <p className={`small ${night ? '' : 'muted'}`}>
      {night ? 'Сейчас ночь' : nightIn != null ? `Ночь через ${mmss(nightIn)}` : 'Днём'} — ночью сильнее: {names}
    </p>
  );
}

export function EnemiesMode({ enemies }: { enemies: number[] }) {
  const heroes = useHeroes().data;
  const q = useThreats(enemies);
  if (!enemies.length) return <p className="muted ov__center">Заполни врагов в драфте — здесь появятся их опасные способности.</p>;
  if (!q.data) return <p className="muted ov__center">Загружаю способности…</p>;
  return (
    <div className="ov__enemies">
      <p className="hint">Перезарядки — справочно по уровням: когда враг применил способность, программа не видит.</p>
      {q.data.heroes.map((h) => (
        <section key={h.hero} className="ov__enemy">
          <div className="ov__enemy-head">
            <HeroIcon id={h.hero} size="sm" />
            <b>{heroes?.byId.get(h.hero)?.name}</b>
            {h.night && <span className="ov-badge" title="Какие-то способности сильнее ночью">ночью сильнее</span>}
          </div>
          <ul className="ov__threats">
            {h.abilities.map((a) => (
              <li key={a.key} className={a.ultimate ? 'is-ult' : ''}>
                <Tip
                  content={
                    <>
                      <b className="tip__title">{a.name}</b>
                      <p>{a.desc}</p>
                      {a.cooldown && <p className="tip__meta">Перезарядка {a.cooldown} с</p>}
                    </>
                  }
                >
                  <span tabIndex={0}>
                    <AbilityIcon info={{ key: a.key, name: a.name, desc: a.desc, innate: false, icon: a.icon }} size={26} />
                  </span>
                </Tip>
                <div>
                  <span className="small">
                    <b>{a.name}</b>
                    {a.cooldown && <span className="muted"> · {a.cooldown} с</span>}
                  </span>
                  <span className="ov__tags">
                    {a.pierces && <span className="ov-badge is-bad">сквозь BKB</span>}
                    {a.tags.map((t) => (
                      <span key={t} className="ov-badge">
                        {t}
                      </span>
                    ))}
                    {a.dispel && <span className={`ov-badge ${a.dispel === 'развеивается' ? 'is-good' : ''}`}>{a.dispel}</span>}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** One line over every tab but «Драфт»: the draft's win chance and when we are stronger. */
export function WinStrip({ req, me, inGame }: { req: DraftRequest; me: number | null; inGame: boolean }) {
  const full = req.allies.length > 0 && req.enemies.length > 0;
  const ev = useEvaluate(req);
  const plan = usePlan(full ? req.allies : [], full ? req.enemies : [], me, inGame).data;
  if (!full || !ev.data) return null;
  const p = ev.data.p_win;
  const when =
    plan?.shape === 'early'
      ? `сильнее в начале${plan.cross ? `, до ~${plan.cross} мин` : ''}`
      : plan?.shape === 'late'
        ? `сильнее позже${plan.cross ? `, после ~${plan.cross} мин` : ''}`
        : plan?.shape === 'ahead'
          ? 'сильнее во всех фазах'
          : plan?.shape === 'behind'
            ? 'враги сильнее во всех фазах'
            : null;
  return (
    <div className={`ov__winstrip ${p >= 0.5 ? 'is-good' : 'is-bad'}`} title={`Оценка драфта: ${req.allies.length} на ${req.enemies.length}`}>
      <span>
        Ваш драфт <b>{fmtPct(p, 0)}</b>
      </span>
      {when && <span className="muted">· {when}</span>}
    </div>
  );
}
