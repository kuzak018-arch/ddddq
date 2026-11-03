/** The in-match pieces drawn as the game draws them: icons with a ring that fills up to the spawn,
 * colours for states, few words. Used by the widgets over the HUD and the overlay's «Сейчас». */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Clock,
  Coins,
  Crosshair,
  Droplet,
  Flower2,
  Gem,
  Hexagon,
  Moon,
  RotateCcw,
  Skull,
  Sun,
  TrendingDown,
  TrendingUp,
  Trophy,
  X,
  Zap,
  type LucideIcon,
} from '../components/glyphs';
import type { CSSProperties } from 'react';

import { api, asset } from '../api/client';
import type { DraftRequest } from '../api/types';
import { useEvaluate } from '../api/hooks';
import { NeutralTip, useNeutrals } from '../components/NeutralItems';
import { Tip } from '../components/Tip';
import { HeroIcon, ItemIcon, Mins } from '../components/ui';
import { mmss, useThreats, type NeutralTierNow, type Objectives } from './InGame';
import type { GameLive, PlanItem } from './live';

/** Dota's own HUD pictures (public/dota-icons/hud, from the game's panorama files). */
const HUD = (name: string) => `/dota-icons/hud/${name}.webp`;

// the runes and the lotus as the game's map timers draw them
const LOOK: Record<string, { icon: LucideIcon; color: string; label: string; item?: string; src?: string }> = {
  power: { icon: Zap, color: '#c77dff', label: 'Сила', src: HUD('power') },
  water: { icon: Droplet, color: '#4fb3ff', label: 'Вода' },
  bounty: { icon: Coins, color: '#f2c14e', label: 'Богатство', src: HUD('bounty') },
  wisdom: { icon: BookOpen, color: '#7ee08a', label: 'Мудрость', src: HUD('wisdom') },
  lotus: { icon: Flower2, color: '#ff8fc8', label: 'Лотос', src: HUD('lotus') },
};

/** A small picture from Dota's HUD in a line of text (gold, buyback). */
function HudImg({ name, size = 16 }: { name: string; size?: number }) {
  return <img className="hud-img" src={HUD(name)} alt="" width={size} height={size} draggable={false} />;
}

/** A round icon with a ring that closes as the moment comes; `left` seconds of `period`. */
export function Ring({ icon: Icon, item, src, color, left, period, label, size = 30, pulse }: {
  icon: LucideIcon;
  item?: string;   // a game item's picture instead of the vector icon
  src?: string;    // a picture of Dota's HUD (the rune, Roshan, the Tormentor…), before `item`
  color: string;
  left: number | null;
  period: number | null;
  label: string;
  size?: number;
  pulse?: boolean;
}) {
  const r = size / 2 - 2;
  const c = 2 * Math.PI * r;
  const done = left != null && period ? Math.min(1, Math.max(0, 1 - left / period)) : 1;
  return (
    <span className={`hud-ring ${pulse ? 'is-soon' : ''}`} style={{ '--c': color, width: size, height: size } as CSSProperties} title={label}>
      <svg className="hud-ring__svg" width={size} height={size} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} className="hud-ring__track" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          className="hud-ring__fill"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - done)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {src ? (
        <img className="hud-ring__img hud-ring__img--hud" src={src} alt="" style={{ width: size * 0.7, height: size * 0.7 }} draggable={false} />
      ) : item ? (
        <img className="hud-ring__img" src={asset(`/icons/items/${item}.png`)} alt="" style={{ width: size * 0.62, height: size * 0.62 }} draggable={false} />
      ) : (
        <Icon size={size * 0.46} className="hud-ring__icon" />
      )}
    </span>
  );
}

function Chip({ children, className = '', title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span className={`hud-chip ${className}`} title={title}>
      {children}
    </span>
  );
}

/** Runes, lotuses, day and night: an icon with a ring, the time under it. */
export function TimersHud({ g, elapsed = 0, max = 5 }: { g: GameLive; elapsed?: number; max?: number }) {
  return (
    <div className="hud-timers">
      {g.timers.slice(0, max).map((t) => {
        const left = Math.max(0, Math.round(t.in - elapsed));
        const night = t.key === 'night';
        const look: { icon: LucideIcon; color: string; label: string; item?: string; src?: string } = night
          ? { icon: t.name === 'Ночь' ? Moon : Sun, color: t.name === 'Ночь' ? '#9db4ff' : '#ffcf5a', label: t.name }
          : (LOOK[t.key] ?? { icon: Clock, color: '#bbb', label: t.name });
        return (
          <Chip key={t.key} className="hud-chip--col" title={`${t.name} через ${mmss(left)}`}>
            <Ring icon={look.icon} item={look.item} src={look.src} color={look.color} left={left} period={t.period ?? null} label={t.name} pulse={left <= 15} />
            <b className={left <= 15 ? 'is-soon' : ''}>{mmss(left)}</b>
            <small>{look.label}</small>
          </Chip>
        );
      })}
    </div>
  );
}

/** Roshan and the Tormentor: the state as a colour, the countdown, a cross-hair to mark the kill. */
export function ObjectivesHud({ o }: { o: Objectives }) {
  const qc = useQueryClient();
  const mark = useMutation({
    mutationFn: (body: { kind: 'roshan' | 'tormentor'; undo?: boolean }) => api('/game/mark', { body }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-live'] }),
  });
  const r = o.roshan;
  const t = o.tormentor;
  const color = (s: string) => (s === 'alive' ? '#5ad07a' : s === 'maybe' ? '#f2c14e' : '#ff6b6b');
  const rPeriod = r.state === 'dead' ? 8 * 60 : r.state === 'maybe' ? 3 * 60 : null;
  const pit = r.pit === 'top' ? 'верхнее логово' : r.pit === 'bottom' ? 'нижнее логово' : '';
  const rTitle = r.state === 'alive' ? `Рошан жив${pit ? ` · ${pit}` : ''}` : r.state === 'maybe' ? 'Рошан может быть жив' : 'Рошан мёртв';
  const side = t.side === 'radiant' ? 'Свет' : 'Тьма';
  return (
    <div className="hud-obj">
      <Chip className={`hud-chip--obj is-${r.state}`} title={rTitle}>
        <Ring icon={Skull} src={HUD('roshan')} color={color(r.state)} left={r.in ?? null} period={rPeriod} label={rTitle} />
        <span className="hud-obj__text">
          <b>{r.state === 'alive' ? (r.pit === 'top' ? 'жив ▲' : r.pit === 'bottom' ? 'жив ▼' : 'жив') : r.in != null ? mmss(r.in) : '?'}</b>
          <small>Рошан{r.state === 'maybe' ? ' · может' : ''}</small>
        </span>
        {r.aegis != null && (
          <span className="hud-aegis" title={`Аегис ещё ${mmss(r.aegis)}`}>
            <HudImg name="aegis" size={14} /> {mmss(r.aegis)}
          </span>
        )}
        {r.source !== 'dota' &&
          (r.source === 'mark' ? (
            <button className="hud-btn" title="Отменить отметку" onClick={() => mark.mutate({ kind: 'roshan', undo: true })}>
              <X size={12} />
            </button>
          ) : (
            <button className="hud-btn" title="Рошана убили сейчас" onClick={() => mark.mutate({ kind: 'roshan' })}>
              <Crosshair size={12} />
            </button>
          ))}
      </Chip>
      <Chip className={`hud-chip--obj is-${t.state}`} title={`Терзатель ${t.state === 'alive' ? 'жив' : `через ${mmss(t.in ?? 0)}`} · сторона ${side}`}>
        <Ring icon={Hexagon} src={HUD(t.side === 'dire' ? 'tormentor_dire' : 'tormentor_radiant')} color={color(t.state)} left={t.in} period={t.state === 'dead' ? 10 * 60 : null} label="Терзатель" />
        <span className="hud-obj__text">
          <b>{t.state === 'alive' ? `жив · ${side}` : mmss(t.in ?? 0)}</b>
          <small>Терзатель</small>
        </span>
        {t.source === 'mark' ? (
          <button className="hud-btn" title="Отменить отметку" onClick={() => mark.mutate({ kind: 'tormentor', undo: true })}>
            <X size={12} />
          </button>
        ) : (
          t.state === 'alive' && (
            <button className="hud-btn" title="Терзателя убили сейчас" onClick={() => mark.mutate({ kind: 'tormentor' })}>
              <Crosshair size={12} />
            </button>
          )
        )}
      </Chip>
    </div>
  );
}

/** The neutral tier: a gem with the tier, the countdown to the next one; a flash when one opens. */
export function NeutralHud({ t, hero, pos, held }: { t: NeutralTierNow; hero: number | null; pos: number; held: string | null }) {
  const d = useNeutrals(hero, pos).data;
  const fresh = t.tier != null && t.ago != null && t.ago < 120;
  const row = fresh ? d?.tiers.find((x) => x.tier === t.tier) : undefined;
  const pop = row?.items.filter((i) => i.popular) ?? [];
  const periods: Record<number, number> = { 1: 300, 2: 600, 3: 600, 4: 600, 5: 1500 };
  return (
    <div className={`hud-neutral ${fresh ? 'is-fresh' : ''}`}>
      <Chip className="hud-chip--col" title={fresh ? `Открылся тир ${t.tier}` : t.next ? `Тир ${t.next} через ${mmss(t.in ?? 0)}` : 'Открыты все тиры'}>
        <span className="hud-gem">
          <Ring icon={Gem} src={HUD('neutral_timer')} color="#59d7c8" left={fresh ? 0 : t.in} period={t.next ? periods[t.next] ?? 600 : null} label="Нейтралки" />
          <i>{fresh ? t.tier : (t.next ?? t.tier ?? '')}</i>
        </span>
        <b>{fresh ? 'открыт' : t.in != null ? mmss(t.in) : '—'}</b>
        <small>Тир {fresh ? t.tier : (t.next ?? t.tier ?? '')}</small>
      </Chip>
      {pop.map((it) => (
        <Tip key={it.key} content={<NeutralTip it={it} tierGames={row?.games} />}>
          <span className="hud-item" tabIndex={0}>
            <ItemIcon k={it.key} size={20} />
          </span>
        </Tip>
      ))}
      {held && (
        <span className="hud-item hud-item--held" title="В слоте нейтралки">
          <ItemIcon k={held} size={20} />
        </span>
      )}
    </div>
  );
}

/** The next item: its icon filling up with the gold, then coins missing, my pace, top players'. */
export function GoldHud({ g, plan }: { g: GameLive; plan: PlanItem[] }) {
  const qc = useQueryClient();
  const skip = useMutation({
    mutationFn: (key: string) => api('/game/skip', { body: { key } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-live'] }),
  });
  const n = g.next;
  if (!g.live || !n) return null;
  const clock = g.live.clock ?? 0;
  const pct = Math.round((100 * (n.cost - n.left + Math.min(g.live.gold ?? 0, n.left))) / Math.max(1, n.cost));
  const planned = plan.find((p) => p.key === n.key);
  const top = planned?.minute ?? null;
  const eta = !n.ready && g.live.gpm ? clock + (n.missing / g.live.gpm) * 60 : null;
  const late = (eta ?? clock) / 60 > (top ?? Infinity) + 1;
  const replaced = (g.passed ?? []).filter((p) => p.why === 'replaced').slice(-1)[0];
  return (
    <div className={`hud-gold ${n.ready ? 'is-ready' : ''}`}>
      <span className="hud-fill" style={{ '--p': `${pct}%` } as CSSProperties} title={n.name}>
        <ItemIcon k={n.key} title={n.name} size={34} />
        <i>
          <ItemIcon k={n.key} size={34} />
        </i>
      </span>
      <div className="hud-gold__nums">
        <b className="hud-gold__name">{n.name}</b>
        <span className="hud-stat">
          <Chip className={n.ready ? 'c-good' : ''} title={n.ready ? 'Хватает — можно покупать' : `Не хватает ${n.missing.toLocaleString('ru')} золота`}>
            <HudImg name="gold_small" size={14} /> {n.ready ? 'хватает' : `−${n.missing.toLocaleString('ru')}`}
          </Chip>
          <small>золото</small>
        </span>
        {eta != null && (
          <span className="hud-stat">
            <Chip className={late ? 'c-bad' : ''} title="Когда купишь при своём темпе">
              <Mins m={eta / 60} />
            </Chip>
            <small>ты купишь</small>
          </span>
        )}
        {top != null && (
          <span className="hud-stat">
            <Chip className="muted" title={planned?.top ? 'У топов в выигранных играх' : 'Обычно на твоём ранге'}>
              <Trophy size={12} /> {Math.floor(top)}:{String(Math.round((top % 1) * 60)).padStart(2, '0')}
            </Chip>
            <small>{planned?.top ? 'у топов' : 'обычно'}</small>
          </span>
        )}
      </div>
      <button className="hud-btn hud-btn--corner" title="Не собираю — показать следующий предмет" onClick={() => skip.mutate(n.key)}>
        <X size={12} />
      </button>
      {replaced && (
        <span className="hud-note" title={`${replaced.name} пропущен — собран ${replaced.by_name ?? replaced.by}`}>
          <ItemIcon k={replaced.key} size={14} />→<ItemIcon k={replaced.by ?? ''} size={14} />
        </span>
      )}
    </div>
  );
}

export function BuybackHud({ g }: { g: GameLive }) {
  const b = g.buyback;
  if (!b) return null;
  const cls = b.cooldown ? 'muted' : b.enough ? 'c-good' : 'c-bad';
  return (
    <Chip className={cls} title={b.cooldown ? `Выкуп на перезарядке ${mmss(b.cooldown)}` : b.enough ? 'На выкуп хватает' : `На выкуп не хватает ${b.missing.toLocaleString('ru')}`}>
      <RotateCcw size={13} /> выкуп {b.cooldown ? mmss(b.cooldown) : b.cost.toLocaleString('ru')}
    </Chip>
  );
}

export function PaceHud({ g }: { g: GameLive }) {
  const nw = g.pace?.networth;
  if (!nw) return null;
  const pct = Math.round((nw.ratio - 1) * 100);
  const Icon = pct >= 0 ? TrendingUp : TrendingDown;
  return (
    <Chip className={nw.verdict === 'bad' ? 'c-bad' : nw.verdict === 'good' ? 'c-good' : 'muted'} title={`Нетворс ${nw.now.toLocaleString('ru')} к ${nw.minute}-й минуте, у топов ${nw.top.toLocaleString('ru')}`}>
      <Icon size={13} /> нетворс {pct > 0 ? '+' : ''}
      {pct}% к топам
    </Chip>
  );
}

/** Night: a moon, the time, the portraits of the heroes stronger at night. */
export function NightHud({ g, me, enemies, elapsed = 0 }: { g: GameLive; me: number | null; enemies: number[]; elapsed?: number }) {
  const th = useThreats([...(me ? [me] : []), ...enemies]).data;
  const who = (th?.heroes ?? []).filter((h) => h.night);
  if (!who.length) return null;
  const t = g.timers.find((x) => x.key === 'night');
  const isNight = g.live?.daytime === false;
  const left = t ? Math.max(0, Math.round(t.in - elapsed)) : null;
  return (
    <span className={`hud-night ${isNight ? 'is-night' : ''}`} title={isNight ? 'Сейчас ночь — эти герои сильнее' : 'Ночью эти герои сильнее'}>
      <Moon size={14} />
      <small>{isNight ? 'ночь, сильнее:' : 'ночью сильнее:'}</small>
      {!isNight && left != null && t?.name === 'Ночь' && <b>{mmss(left)}</b>}
      {who.map((h) => (
        <span key={h.hero} className={h.hero === me ? 'is-me' : 'is-enemy'}>
          <HeroIcon id={h.hero} size="xs" />
        </span>
      ))}
    </span>
  );
}

/** The draft's chances as a thin two-colour bar. */
export function WinBar({ req }: { req: DraftRequest }) {
  const full = req.allies.length > 0 && req.enemies.length > 0;
  const ev = useEvaluate(req).data;
  if (!full || !ev) return null;
  const p = Math.round(ev.p_win * 100);
  return (
    <span className="hud-win" title={`Шанс победы по драфту ${p}%`}>
      <small>драфт</small>
      <span className="hud-win__bar">
        <i style={{ width: `${p}%` }} />
      </span>
      <b className={p >= 50 ? 'c-good' : 'c-bad'}>{p}%</b>
    </span>
  );
}
