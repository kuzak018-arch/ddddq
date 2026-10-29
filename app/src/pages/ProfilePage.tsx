import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  CalendarDays,
  ChartLine,
  CircleUser,
  Droplet,
  Gamepad2,
  Image,
  LayoutGrid,
  MessageSquareText,
  Paintbrush,
  Percent,
  RefreshCw,
  Star,
  Upload,
  User,
  UserSearch,
  Skull,
} from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react';

import { api } from '../api/client';
import { useAvatar, useHealth, useHeroes, useMeSummary, useProfile } from '../api/hooks';
import type { MeSummary, Profile, RankProgress } from '../api/types';
import { heroArt, PRESETS } from '../components/Chrome';
import { useHeroModel } from '../components/HeroModel';
import { Panel } from '../components/Glass';
import { AttrIcon, PlusBadge, RankMedal, RoleIcon } from '../components/DotaIcons';
import { HeroSearch } from '../components/HeroSearch';
import { Ti } from '../components/Icons';
import { MatchHistory } from '../components/MatchHistory';
import { MatchRuin } from '../components/MatchRuin';
import { MyStats } from '../components/MyStats';
import { type ProfileTab, useNav } from '../state/nav';
import { PlayerSearch } from '../components/PlayerSearch';
import { Sheet } from '../components/Sheet';
import { Empty, ErrorBox, fmtPct, fmtSigned, HeroIcon, plural, Segmented, Slider, Toggle } from '../components/ui';
import { rankName } from '../lib/ranks';
import { loadFile, saveFile } from '../state/bgstore';
import { useUi } from '../state/ui';

const pp = (logit: number) => (1 / (1 + Math.exp(-logit)) - 0.5) * 100;

const ACCENTS: { value: string; name: string }[] = [
  { value: 'auto', name: 'Под героя на баннере' },
  { value: '#5ee6a0', name: 'Radiant' },
  { value: '#ff6b5e', name: 'Dire' },
  { value: '#6aa8ff', name: 'Синий' },
  { value: '#ffc95c', name: 'Золото' },
  { value: '#c48bff', name: 'Фиолетовый' },
  { value: '#ff7ab8', name: 'Розовый' },
  { value: '#ffffff', name: 'Белый' },
];

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
  const summary = useMeSummary().data;
  const { profileTab: tab, ruinId, set: setNav } = useNav();
  const setTab = (profileTab: ProfileTab) => setNav({ profileTab });
  const setRuinId = (id: number | null) => setNav({ ruinId: id });
  const [look, setLook] = useState(false);
  const health = useHealth().data;
  const go = useUi((s) => s.go);

  return (
    <div className="profile">
      <Panel className="profile__head" refracting>
        <Banner>
          <div className="panel__head">
            <h2>
              <Ti icon={User} />
              Профиль
            </h2>
            <button className="btn btn--sm" onClick={() => setLook(true)}>
              <Ti icon={Paintbrush} />
              Оформить
            </button>
            <button className="btn btn--sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <Ti icon={RefreshCw} />
              {refresh.isPending ? 'Загружаю…' : 'Обновить историю'}
            </button>
          </div>
          {p && <ProfileCard p={p} summary={summary} />}
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
      </Panel>
      <Panel className="profile__side">
        {exp && (
          <div className="exp">
            <h3 className="section-title">
              <Ti icon={ChartLine} />
              Твоя кривая опыта на героях
            </h3>
            <p className="muted">
              Подогнана на {exp.games} твоих играх: насколько реже ты выигрываешь на герое, на котором мало играл.
            </p>
            <ExperienceChart A={exp.A} k={exp.k} />
          </div>
        )}
        {summary && <Summary s={summary} />}
        {!exp && !(summary && (summary.form.length || summary.positions.length || summary.month_heroes.length)) && <Empty>Здесь будут форма, винрейт по позициям и главные герои месяца.</Empty>}
      </Panel>
      <Panel className="profile__pool">
        <div className="panel__head">
          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: 'stats', label: <><Ti icon={ChartLine} />Статистика</> },
              { value: 'matches', label: <><Ti icon={Gamepad2} />Матчи</> },
              { value: 'ruin', label: <><Ti icon={Skull} />Кто заруинил</> },
              { value: 'pool', label: <><Ti icon={LayoutGrid} />Пул героев</> },
              { value: 'search', label: <><Ti icon={UserSearch} />Найти игрока</> },
            ]}
          />
        </div>
        {tab === 'matches' && (
          <MatchHistory
            onAnalyze={(id) => {
              setRuinId(id);
              setTab('ruin');
            }}
          />
        )}
        {tab === 'ruin' && <MatchRuin initial={ruinId} />}
        {tab === 'stats' && (
          <MyStats
            onAnalyze={(id) => {
              setRuinId(id);
              setTab('ruin');
            }}
          />
        )}
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
                    <HeroIcon id={h.hero} size="sm" /> <AttrIcon attr={heroes?.byId.get(h.hero)?.attr ?? ''} size={14} /> {heroes?.byId.get(h.hero)?.name}
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
      <ProfileLook open={look} onClose={() => setLook(false)} />
    </div>
  );
}

/** Points to the next star and the next medal. Valve hides the exact rating, so these are estimates
 * from the rank's step (and OpenDota's estimate when it fits it): said so in the tooltip. */
function RankProgressLine({ r }: { r: RankProgress }) {
  const how = r.from_estimate ? `внутри ступени взята оценка OpenDota (${r.mmr})` : `внутри ступени взята середина (${r.mmr})`;
  const title = `Valve не показывает точный рейтинг, поэтому цифры примерные. Ступень «${r.name}» — это ${r.low}–${r.high} ПТС, ${how}. Победа или поражение — около ±${r.per_game}.`;
  return (
    <p className="rankp" title={title}>
      {r.next_star && (
        <span>
          до <b>{r.next_star.name}</b> ≈ {r.next_star.points} ПТС
        </span>
      )}
      <span>
        до <b>{r.next_rank.name}</b> ≈ {r.next_rank.points} ПТС (~{r.next_rank.games} {plural(r.next_rank.games, 'победа', 'победы', 'побед')})
      </span>
    </p>
  );
}

/** The header card: avatar in its frame, rank medal, name, Dota Plus, status, tiles and the showcase. */
function ProfileCard({ p, summary }: { p: Profile; summary?: MeSummary }) {
  const b = useUi((s) => s.banner);
  const openHero = useUi((s) => s.openHero);
  const avatar = useAvatar(p.avatar, p.fetched);
  const main = summary?.positions.length ? [...summary.positions].sort((x, y) => y.games - x.games)[0]! : null;
  const month = summary?.month_heroes[0];
  return (
    <div className="pro">
      <div className={`pro__avatar pro__avatar--${b.avatar}`}>{avatar ? <img src={avatar} alt="" /> : <span />}</div>
      <RankMedal tier={p.rank_tier} leaderboard={p.leaderboard} size={92} className="pro__medal" />
      <div className="pro__who">
        <h1>
          {p.name ?? p.account_id}
          {p.plus && <PlusBadge size={26} />}
        </h1>
        {b.status && <p className="pro__status">{b.status}</p>}
        <p className="me__sub">
          {rankName(p.rank_tier)}
          {p.leaderboard ? ` · #${p.leaderboard} в таблице лидеров` : ''} · ID {p.account_id}
        </p>
        {p.rank_progress && <RankProgressLine r={p.rank_progress} />}
        <div className="pro__tiles">
          {b.tiles.games && (
            <div className="pro__tile">
              <b>{(p.overall?.games ?? 0).toLocaleString('ru')}</b>
              <span>игр в рейтинге</span>
            </div>
          )}
          {b.tiles.winrate && (
            <div className="pro__tile">
              <b className={(p.overall?.wr ?? 0) >= 0.5 ? 'c-good' : 'c-bad'}>{fmtPct(p.overall?.wr)}</b>
              <span>побед</span>
            </div>
          )}
          {b.tiles.pos && main && (
            <div className="pro__tile">
              <b>
                <RoleIcon pos={main.pos} size={20} /> {POS_NAMES[main.pos]}
              </b>
              <span>
                главная роль · {fmtPct(main.wr, 0)}
              </span>
            </div>
          )}
          {b.tiles.month && month && (
            <button className="pro__tile pro__tile--hero" onClick={() => openHero(month.hero)}>
              <HeroIcon id={month.hero} size="sm" />
              <span>
                <b>{month.games}</b> игр за месяц
              </span>
            </button>
          )}
        </div>
      </div>
      {b.showcase.length > 0 && (
        <div className="pro__showcase">
          <span className="label">Витрина</span>
          <div>
            {b.showcase.map((h) => (
              <button key={h} className="pro__show tilt" data-tilt="12" onClick={() => openHero(h)}>
                <img src={`/portraits/${h}.webp`} alt="" draggable={false} />
                <HeroName id={h} />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function HeroName({ id }: { id: number }) {
  const name = useHeroes().data?.byId.get(id)?.name;
  return <span>{name}</span>;
}

/** «Оформить»: the header's background, accent, avatar frame, status, tiles and showcase. */
function ProfileLook({ open, onClose }: { open: boolean; onClose: () => void }) {
  const b = useUi((s) => s.banner);
  const set = useUi((s) => s.set);
  const update = (patch: Partial<typeof b>) => set({ banner: { ...b, ...patch } });
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  return (
    <Sheet open={open} onClose={onClose} title={<><Ti icon={Paintbrush} />Оформление профиля</>}>
      <div className="plook">
        <section>
          <h3 className="section-title">
            <Ti icon={Image} />
            Фон шапки
          </h3>
          <div className="plook__bgs">
            <button className={`plook__bg ${b.kind === 'none' ? 'is-on' : ''}`} onClick={() => update({ kind: 'none' })}>
              <span>Без фона</span>
            </button>
            {PRESETS.map((x) => (
              <button
                key={x.id}
                className={`plook__bg ${b.kind === 'preset' && b.key === x.id ? 'is-on' : ''}`}
                style={{ background: x.css }}
                onClick={() => update({ kind: 'preset', key: x.id })}
              >
                <span>{x.name}</span>
              </button>
            ))}
          </div>
          <div className="row">
            <button className="btn btn--sm" onClick={() => input.current?.click()}>
              <Ti icon={Upload} />
              Свой файл (картинка или GIF)
            </button>
          </div>
          <HeroSearch placeholder="Арт героя на фон…" onPick={(h) => update({ kind: 'hero', key: h.key, x: 22, y: 20 })} compact />
          {b.kind !== 'none' && b.kind !== 'preset' && (
            <>
              <Slider label="Размытие" value={b.blur} min={0} max={20} step={1} onChange={(blur) => update({ blur })} format={(v) => `${v} px`} />
              <Slider label="Затемнение" value={b.dim} min={0} max={0.85} step={0.05} onChange={(dim) => update({ dim })} format={(v) => `${Math.round(v * 100)}%`} />
              <p className="muted small">Видимую часть картинки (или место героя) выбирают перетаскиванием в шапке: кнопка «Баннер» на ней.</p>
            </>
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
              update({ kind: 'file', key: `${f.name}:${f.size}:${Date.now()}`, x: 50, y: 50 });
            }}
          />
        </section>
        <section>
          <h3 className="section-title">
            <Ti icon={Droplet} />
            Акцент
          </h3>
          <div className="plook__accents">
            {ACCENTS.map((a) => (
              <button
                key={a.value}
                className={`plook__accent ${b.accent === a.value ? 'is-on' : ''} ${a.value === 'auto' ? 'is-auto' : ''}`}
                style={a.value === 'auto' ? undefined : { background: a.value }}
                title={a.name}
                aria-label={a.name}
                onClick={() => update({ accent: a.value })}
              />
            ))}
          </div>
          <p className="muted small">Рамка аватара, свечение шапки и подсветка витрины.</p>
        </section>
        <section>
          <h3 className="section-title">
            <Ti icon={CircleUser} />
            Аватар
          </h3>
          <Segmented
            small
            value={b.avatar}
            onChange={(avatar) => update({ avatar })}
            options={[
              { value: 'round', label: 'Круг' },
              { value: 'squircle', label: 'Скруглённый' },
              { value: 'hex', label: 'Шестиугольник' },
            ]}
          />
        </section>
        <section>
          <h3 className="section-title">
            <Ti icon={MessageSquareText} />
            Статус
          </h3>
          <input className="input" maxLength={60} value={b.status} onChange={(e) => update({ status: e.target.value })} placeholder="например: мид или фид · иду в Divine" />
        </section>
        <section>
          <h3 className="section-title">
            <Ti icon={LayoutGrid} />
            Плитки в шапке
          </h3>
          <Toggle on={b.tiles.games} onChange={(games) => update({ tiles: { ...b.tiles, games } })} label="Игры в рейтинге" />
          <Toggle on={b.tiles.winrate} onChange={(winrate) => update({ tiles: { ...b.tiles, winrate } })} label="Винрейт" />
          <Toggle on={b.tiles.pos} onChange={(pos) => update({ tiles: { ...b.tiles, pos } })} label="Главная роль" />
          <Toggle on={b.tiles.month} onChange={(month) => update({ tiles: { ...b.tiles, month } })} label="Главный герой месяца" />
        </section>
        <section>
          <h3 className="section-title">
            <Ti icon={Star} />
            Витрина героев <span className="muted">· до 5</span>
          </h3>
          <div className="plook__show">
            {b.showcase.map((h) => (
              <button key={h} className="plook__showhero" onClick={() => update({ showcase: b.showcase.filter((x) => x !== h) })} title="Убрать">
                <HeroIcon id={h} size="md" />
                <span className="plook__x">✕</span>
              </button>
            ))}
          </div>
          {b.showcase.length < 5 && (
            <HeroSearch
              placeholder="Добавить героя в витрину…"
              unavailable={new Set(b.showcase)}
              onPick={(h) => update({ showcase: [...b.showcase, h.id].slice(0, 5) })}
              compact
            />
          )}
        </section>
      </div>
    </Sheet>
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
            <Ti icon={Activity} />
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
          <h3 className="section-title">
            <Ti icon={Percent} />
            Винрейт по позициям
          </h3>
          <div className="pos-wr">
            {s.positions.map((x) => (
              <div key={x.pos} className="pos-wr__row">
                <span className="pos-wr__name">
                  <RoleIcon pos={x.pos} size={16} />
                  {POS_NAMES[x.pos]}
                </span>
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
            <Ti icon={CalendarDays} />
            Главные герои за месяц <span className="muted">· {s.month_games} игр</span>
          </h3>
          <div className="month">
            {s.month_heroes.map((h) => (
              <button key={h.hero} className="month__h tilt" data-tilt="6" onClick={() => openHero(h.hero)}>
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

/** Header banner: the user's own image/GIF (IndexedDB), a hero render or a built-in gradient, in
 * the profile's accent; «Баннер» lets the picture (or the hero) be dragged to the part to show. */
function Banner({ children }: { children: ReactNode }) {
  const banner = useUi((s) => s.banner);
  const set = useUi((s) => s.set);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; bx: number; by: number } | null>(null);
  const [pos, setPos] = useState({ x: banner.x, y: banner.y });
  useEffect(() => setPos({ x: banner.x, y: banner.y }), [banner.x, banner.y]);
  const heroColor = useHeroModel(banner.kind === 'hero' ? banner.key : null).color;

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
  const preset = banner.kind === 'preset' ? PRESETS.find((x) => x.id === banner.key) : null;
  const accent = banner.accent === 'auto' ? (heroColor ?? '#9db4ff') : banner.accent;
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
    <div
      ref={box}
      className={`banner ${src || preset ? 'has-img' : ''} ${editing && src ? 'is-editing' : ''}`}
      style={{ '--accent-p': accent, ...(preset ? { background: preset.css } : {}) } as CSSProperties}
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
      <div className="banner__accent" aria-hidden />
      {banner.kind === 'hero' && banner.key && <BannerModel heroKey={banner.key} x={pos.x} />}
      <div className="banner__content">{children}</div>
      {src && (
        <button className="btn btn--sm banner__edit" onClick={() => setEditing((v) => !v)} onPointerDown={(e) => e.stopPropagation()}>
          {editing ? 'Готово' : banner.kind === 'hero' ? 'Сдвинуть героя' : 'Выбрать часть картинки'}
        </button>
      )}
    </div>
  );
}
