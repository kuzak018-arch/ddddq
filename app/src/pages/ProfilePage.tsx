import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';

import { api } from '../api/client';
import { useAvatar, useHealth, useHeroes, useMeSummary, useProfile } from '../api/hooks';
import type { MeSummary } from '../api/types';
import { heroArt } from '../components/Chrome';
import { useHeroModel } from '../components/HeroModel';
import { Panel } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { MatchHistory } from '../components/MatchHistory';
import { PlayerSearch } from '../components/PlayerSearch';
import { Empty, ErrorBox, fmtPct, fmtSigned, HeroIcon, Segmented, Slider } from '../components/ui';
import { rankName } from '../lib/ranks';
import { loadFile, saveFile } from '../state/bgstore';
import { useUi } from '../state/ui';

const pp = (logit: number) => (1 / (1 + Math.exp(-logit)) - 0.5) * 100;

export function ProfilePage() {
  const prof = useProfile();
  const heroes = useHeroes().data;
  const openHero = useUi((s) => s.openHero);
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: () => api('/me/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const p = prof.data;
  const exp = p?.experience;
  const avatar = useAvatar(p?.avatar, p?.fetched);
  const summary = useMeSummary().data;
  const [tab, setTab] = useState<'matches' | 'pool' | 'search'>('matches');
  const health = useHealth().data;
  const go = useUi((s) => s.go);

  return (
    <div className="profile">
      <Panel className="profile__head" refracting>
        <Banner>
          <div className="panel__head">
            <h2>Профиль</h2>
            <button className="btn" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              {refresh.isPending ? 'Загружаю…' : 'Обновить историю'}
            </button>
          </div>
          {p && (
            <div className="me">
              {avatar && <img className="me__avatar" src={avatar} alt="" />}
              <div>
                <h1>{p.name ?? p.account_id}</h1>
                <p className="me__sub">
                  {rankName(p.rank_tier)} · рейтинговый All Pick: {p.overall?.games ?? 0} игр, {fmtPct(p.overall?.wr)} побед
                </p>
              </div>
            </div>
          )}
        </Banner>
        {prof.error && !health?.account_id ? (
          <div className="empty-cta">
            <p>Укажи свой Steam ID (Friend ID из профиля Доты) — здесь появятся твоя история, пул героев и разбор матчей.</p>
            <button className="btn btn--accent" onClick={() => go('settings')}>
              Указать в настройках
            </button>
          </div>
        ) : (
          prof.error && <ErrorBox error={prof.error} />
        )}
        {refresh.error && <ErrorBox error={refresh.error} />}
        {exp && (
          <div className="exp">
            <h3 className="section-title">Твоя кривая опыта на героях</h3>
            <p className="muted">
              Подогнана на {exp.games} твоих играх: насколько реже ты выигрываешь на герое, на котором мало играл.
            </p>
            <ExperienceChart A={exp.A} k={exp.k} />
          </div>
        )}
        {summary && <Summary s={summary} />}
      </Panel>
      <Panel className="profile__pool">
        <div className="panel__head">
          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: 'matches', label: 'Матчи' },
              { value: 'pool', label: 'Пул героев' },
              { value: 'search', label: 'Найти игрока' },
            ]}
          />
        </div>
        {tab === 'matches' && <MatchHistory />}
        {tab === 'search' && <PlayerSearch />}
        {tab === 'pool' && !p && !prof.error && <Empty>Загрузка…</Empty>}
        {tab === 'pool' && p && (
          <table className="table">
            <thead>
              <tr>
                <th>Герой</th>
                <th>Игр</th>
                <th>Побед</th>
                <th title="Насколько ты играешь лучше или хуже ожидаемого при таком опыте">Личный перевес</th>
                <th title="Поправка за опыт: чем больше игр, тем ближе к нулю">Опыт</th>
              </tr>
            </thead>
            <tbody>
              {p.heroes.map((h) => (
                <tr key={h.hero} onClick={() => openHero(h.hero)}>
                  <td className="table__hero">
                    <HeroIcon id={h.hero} size="sm" /> {heroes?.byId.get(h.hero)?.name}
                  </td>
                  <td>{h.games}</td>
                  <td className={h.wins / h.games >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(h.wins / h.games, 0)}</td>
                  <td className={h.edge >= 0 ? 'c-good' : 'c-bad'}>{fmtSigned(pp(h.edge))}%</td>
                  <td className="muted">{fmtSigned(pp(h.experience))}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

function ExperienceChart({ A, k }: { A: number; k: number }) {
  const W = 420;
  const H = 120;
  const xs = Array.from({ length: 51 }, (_, n) => n);
  const ys = xs.map((n) => pp(-A * (k / (k + n))));
  const lo = Math.min(...ys, -1);
  const x = (n: number) => 30 + (n / 50) * (W - 40);
  const y = (v: number) => 10 + ((0 - v) / (0 - lo)) * (H - 30);
  const d = xs.map((n, i) => `${i ? 'L' : 'M'}${x(n)},${y(ys[i]!)}`).join(' ');
  return (
    <svg className="exp-chart" viewBox={`0 0 ${W} ${H}`} width="100%">
      <line x1={30} x2={W - 10} y1={y(0)} y2={y(0)} className="exp-chart__axis" />
      {[0, 10, 20, 30, 40, 50].map((n) => (
        <text key={n} x={x(n)} y={H - 4} textAnchor="middle">
          {n}
        </text>
      ))}
      <text x={2} y={y(lo) + 4}>{lo.toFixed(0)}%</text>
      <text x={8} y={y(0) + 4}>0</text>
      <path d={d} className="exp-chart__line" />
      <text x={W - 10} y={H - 16} textAnchor="end" className="muted">
        игр на герое →
      </text>
    </svg>
  );
}

const POS_NAMES = ['', 'Керри', 'Мид', 'Оффлейн', 'Роумер (4)', 'Саппорт (5)'];

function Summary({ s }: { s: MeSummary }) {
  const heroes = useHeroes().data;
  const openHero = useUi((u) => u.openHero);
  const wins = s.form.filter((g) => g.win).length;
  const maxPos = Math.max(1, ...s.positions.map((x) => x.games));
  return (
    <>
      {s.form.length > 0 && (
        <section className="sum">
          <h3 className="section-title">
            Форма за {s.form.length} игр <span className="muted">· {wins}–{s.form.length - wins}</span>
          </h3>
          <div className="form-strip">
            {[...s.form].reverse().map((g) => (
              <button
                key={g.match_id}
                className={`form-strip__g ${g.win ? 'is-win' : 'is-loss'}`}
                title={`${heroes?.byId.get(g.hero)?.name ?? ''} — ${g.win ? 'победа' : 'поражение'}, ${g.kills}/${g.deaths}/${g.assists}, ${Math.round((g.duration ?? 0) / 60)} мин, ${new Date(g.start * 1000).toLocaleDateString('ru-RU')}`}
                onClick={() => openHero(g.hero)}
              >
                <HeroIcon id={g.hero} size="sm" />
              </button>
            ))}
          </div>
          <p className="muted small">Слева направо — от старых к новым.</p>
        </section>
      )}
      {s.positions.length > 0 && (
        <section className="sum">
          <h3 className="section-title">Винрейт по позициям</h3>
          <div className="pos-wr">
            {s.positions.map((x) => (
              <div key={x.pos} className="pos-wr__row">
                <span>{POS_NAMES[x.pos]}</span>
                <div className="pos-wr__bar">
                  <i style={{ width: `${(x.games / maxPos) * 100}%` }} />
                </div>
                <span className="muted">{x.games}</span>
                <b className={x.wr >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(x.wr, 0)}</b>
              </div>
            ))}
          </div>
          <p className="muted small">
            Последние {s.positions_games} игр.
            {!!s.positions_estimated && ` Для ${s.positions_estimated} из них Stratz не знает позицию — взята обычная позиция героя.`}
          </p>
        </section>
      )}
      {s.month_heroes.length > 0 && (
        <section className="sum">
          <h3 className="section-title">
            Главные герои за месяц <span className="muted">· {s.month_games} игр</span>
          </h3>
          <div className="month">
            {s.month_heroes.map((h) => (
              <button key={h.hero} className="month__h" onClick={() => openHero(h.hero)}>
                <HeroIcon id={h.hero} size="sm" />
                <span>{heroes?.byId.get(h.hero)?.name}</span>
                <span className="muted">{h.games}</span>
                <b className={h.wr >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(h.wr, 0)}</b>
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

const BANNER_KEY = 'banner';

/** The hero's model standing in the banner over its blurred scene, with a glow in its colour. */
function BannerModel({ heroKey, x }: { heroKey: string; x: number }) {
  const m = useHeroModel(heroKey);
  // dragging right lowers x (object-position semantics), so the model goes the other way
  const left = Math.min(90, Math.max(10, 100 - x));
  return (
    <>
      <div className="banner__glow" style={{ '--glow': m.color ?? 'var(--accent)', '--x': `${left}%` } as CSSProperties} />
      {m.still && <img className="banner__fig" src={m.still} alt="" draggable={false} style={{ left: `${left}%` }} />}
    </>
  );
}

/** Header banner: the user's own image/GIF (IndexedDB) or a hero render; drag to pick the visible part. */
function Banner({ children }: { children: ReactNode }) {
  const banner = useUi((s) => s.banner);
  const set = useUi((s) => s.set);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const drag = useRef<{ x: number; y: number; bx: number; by: number } | null>(null);
  const [pos, setPos] = useState({ x: banner.x, y: banner.y });
  useEffect(() => setPos({ x: banner.x, y: banner.y }), [banner.x, banner.y]);

  useEffect(() => {
    if (banner.kind !== 'file') return;
    let url: string | null = null;
    let alive = true;
    loadFile(BANNER_KEY).then((blob) => {
      if (blob && alive) setFileUrl((url = URL.createObjectURL(blob)));
    });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [banner.kind, banner.key]);

  const src = banner.kind === 'hero' && banner.key ? heroArt(banner.key) : banner.kind === 'file' ? fileUrl : null;
  const update = (patch: Partial<typeof banner>) => set({ banner: { ...banner, ...patch } });

  const onDown = (e: PointerEvent) => {
    if (!editing || !src) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, bx: pos.x, by: pos.y };
  };
  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    const r = box.current?.getBoundingClientRect();
    if (!d || !r) return;
    // dragging the picture right shows more of its left side: object-position goes down
    const clamp = (v: number) => Math.min(100, Math.max(0, v));
    setPos({ x: clamp(d.bx - ((e.clientX - d.x) / r.width) * 100), y: clamp(d.by - ((e.clientY - d.y) / r.height) * 100) });
  };
  const onUp = () => {
    if (drag.current) update({ x: Math.round(pos.x * 10) / 10, y: Math.round(pos.y * 10) / 10 });
    drag.current = null;
  };

  return (
    <>
      <div
        ref={box}
        className={`banner ${src ? 'has-img' : ''} ${editing && src ? 'is-editing' : ''}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        {src && (
          <img
            className="banner__img"
            src={src}
            alt=""
            draggable={false}
            style={{
              objectPosition: `${pos.x}% ${pos.y}%`,
              // a hero: its scene blurred behind the model, never sharp (that was the "own background")
              filter: banner.kind === 'hero' ? `blur(${Math.max(12, banner.blur)}px) saturate(1.3)` : banner.blur ? `blur(${banner.blur}px)` : undefined,
              transform: banner.kind === 'hero' || banner.blur ? 'scale(1.08)' : undefined,
            }}
          />
        )}
        {src && <div className="banner__dim" style={{ '--dim': banner.dim } as CSSProperties} />}
        {banner.kind === 'hero' && banner.key && <BannerModel heroKey={banner.key} x={pos.x} />}
        <div className="banner__content">{children}</div>
        <button className="btn btn--sm banner__edit" onClick={() => setEditing((v) => !v)} onPointerDown={(e) => e.stopPropagation()}>
          {editing ? 'Готово' : 'Баннер'}
        </button>
      </div>
      {editing && (
        <div className="banner-edit">
          <div className="banner-edit__row">
            <button className="btn btn--sm" onClick={() => input.current?.click()}>
              Свой файл (картинка или GIF)
            </button>
            {banner.kind !== 'none' && (
              <button className="btn btn--sm" onClick={() => update({ kind: 'none' })}>
                Убрать
              </button>
            )}
          </div>
          <HeroSearch placeholder="Арт героя на баннер…" onPick={(h) => update({ kind: 'hero', key: h.key, x: 22, y: 20 })} compact />
          <Slider label="Размытие" value={banner.blur} min={0} max={20} step={1} onChange={(blur) => update({ blur })} format={(v) => `${v} px`} />
          <Slider label="Затемнение" value={banner.dim} min={0} max={0.85} step={0.05} onChange={(dim) => update({ dim })} format={(v) => `${Math.round(v * 100)}%`} />
          {src && (
            <p className="muted small">
              {banner.kind === 'hero' ? 'Перетащи героя в шапке влево или вправо.' : 'Перетащи картинку в шапке, чтобы выбрать видимую часть.'}
            </p>
          )}
          {err && <p className="c-bad small">{err}</p>}
          <input
            ref={input}
            type="file"
            accept="image/*"
            hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              if (f.size > 40 * 1024 * 1024) return setErr('Файл больше 40 МБ — возьми поменьше.');
              setErr(null);
              await saveFile(BANNER_KEY, f);
              // a new key re-reads the file even when the banner already was a file
              update({ kind: 'file', key: `${f.name}:${f.size}:${Date.now()}`, x: 50, y: 50 });
            }}
          />
        </div>
      )}
    </>
  );
}
