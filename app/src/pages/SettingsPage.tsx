import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';

import { comboFromEvent, dotaKeyName, toggleOverlay, useHotkeyStatus } from '../lib/overlay';

import { api, subscribe } from '../api/client';
import { useHealth, useHeroes, useSaveSettings, useSettings } from '../api/hooks';
import type { Job, Settings } from '../api/types';
import { heroArt, PRESETS } from '../components/Chrome';
import { Panel } from '../components/Glass';
import { HeroGridCard } from '../components/HeroGridCard';
import { HeroSearch } from '../components/HeroSearch';
import { LaneBulkCard } from '../components/LaneBulkCard';
import { UpdatesCard } from '../components/UpdatesCard';
import { refractionSupported } from '../glass/refraction';
import { ErrorBox, Segmented, Slider, Toggle } from '../components/ui';
import { LOGO_KEY, useLogoUrl } from '../lib/appIcon';
import { saveBackgroundFile, saveFile } from '../state/bgstore';
import { useUi } from '../state/ui';

export function SettingsPage() {
  return (
    <div className="settings">
      <AppearanceCard />
      <div className="settings__col">
        <GsiCard />
        <VisionCard />
        <OverlayCard />
        <AdviceCard />
        <HeroGridCard />
        <DataCard />
        <LaneBulkCard />
        <UpdatesCard />
      </div>
    </div>
  );
}

function AppearanceCard() {
  const ui = useUi();
  const file = useRef<HTMLInputElement>(null);
  const heroes = useHeroes().data;
  const bg = ui.background;
  return (
    <Panel refracting>
      <h2>Оформление</h2>
      <div className="field">
        <span className="label">Тема</span>
        <Segmented
          value={ui.theme}
          onChange={(theme) => ui.set({ theme })}
          options={[
            { value: 'system', label: 'Как в системе' },
            { value: 'dark', label: 'Тёмная' },
            { value: 'light', label: 'Светлая' },
          ]}
        />
      </div>
      <LogoField />
      <span className="label">Фон</span>
      <div className="bg-grid">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={`bg-tile ${bg.kind === 'preset' && bg.id === p.id ? 'is-on' : ''}`}
            style={{ background: p.css }}
            onClick={() => ui.set({ background: { kind: 'preset', id: p.id } })}
          >
            <span>{p.name}</span>
          </button>
        ))}
        <button className={`bg-tile ${bg.kind === 'file' ? 'is-on' : ''}`} onClick={() => file.current?.click()}>
          <span>Свой файл…</span>
        </button>
        {bg.kind === 'hero' && (
          <button className="bg-tile is-on" style={{ background: `url("${heroArt(bg.key)}") center 20% / cover, #222` }}>
            <span>{heroes?.heroes.find((h) => h.key === bg.key)?.name}</span>
          </button>
        )}
      </div>
      <input
        ref={file}
        type="file"
        accept="image/*"
        hidden
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          await saveBackgroundFile(f);
          ui.set({ background: { kind: 'file', name: f.name } });
        }}
      />
      <HeroSearch placeholder="Арт героя как фон…" onPick={(h) => ui.set({ background: { kind: 'hero', key: h.key } })} compact />
      <Slider label="Размытие фона" value={ui.bgBlur} min={0} max={40} step={1} onChange={(bgBlur) => ui.set({ bgBlur })} format={(v) => `${v} px`} />
      <Slider label="Затемнение фона" value={ui.bgDim} min={0} max={0.8} step={0.05} onChange={(bgDim) => ui.set({ bgDim })} format={(v) => `${Math.round(v * 100)}%`} />
      <div className="field">
        <span className="label">Эффекты фона</span>
        <Segmented
          small
          value={ui.fx.kind}
          onChange={(kind) => ui.set({ fx: { ...ui.fx, kind } })}
          options={[
            { value: 'none', label: 'Нет' },
            { value: 'rain', label: 'Дождь' },
            { value: 'snow', label: 'Снег' },
            { value: 'stars', label: 'Звёзды' },
            { value: 'fog', label: 'Туман' },
            { value: 'particles', label: 'Частицы' },
          ]}
        />
      </div>
      {ui.fx.kind !== 'none' && (
        <Slider
          label="Интенсивность эффекта"
          value={ui.fx.intensity}
          min={0.1}
          max={1}
          step={0.05}
          onChange={(intensity) => ui.set({ fx: { ...ui.fx, intensity } })}
          format={(v) => `${Math.round(v * 100)}%`}
        />
      )}
      <p className="hint">Лёгкая отрисовка; сама выключается в оверлее, во время матча и в режиме производительности.</p>
      <Toggle
        on={ui.refraction && refractionSupported}
        onChange={(refraction) => ui.set({ refraction })}
        label={refractionSupported ? 'Преломление по краям стекла' : 'Преломление (недоступно в этом движке)'}
      />
      <Toggle on={ui.performance} onChange={(performance) => ui.set({ performance })} label="Режим производительности (без размытия и анимаций)" />
    </Panel>
  );
}

/** The icon next to "Dota Drafter" and in the taskbar: the built-in one or the user's picture. */
function LogoField() {
  const logo = useUi((s) => s.logo);
  const set = useUi((s) => s.set);
  const url = useLogoUrl();
  const input = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="field">
      <span className="label">Значок приложения</span>
      <div className="logo-field">
        {url ? <img className="logo-field__preview" src={url} alt="" /> : <span className="titlebar__logo logo-field__preview" />}
        <button className="btn btn--sm" onClick={() => input.current?.click()}>
          Своя картинка…
        </button>
        {logo.kind === 'file' && (
          <button className="btn btn--sm" onClick={() => set({ logo: { kind: 'default' } })}>
            Стандартный
          </button>
        )}
      </div>
      <p className="hint">Показывается рядом с названием и на панели задач (на панели — первый кадр GIF, обрезка по центру).</p>
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
          if (f.size > 20 * 1024 * 1024) return setErr('Файл больше 20 МБ — возьми поменьше.');
          try {
            await createImageBitmap(f); // not a picture -> fail here, not in the title bar
          } catch {
            return setErr('Не получилось прочитать картинку.');
          }
          setErr(null);
          await saveFile(LOGO_KEY, f);
          set({ logo: { kind: 'file', key: `${f.name}:${f.size}:${Date.now()}` } });
        }}
      />
    </div>
  );
}

interface GsiStatus {
  port: number;
  dota_found: boolean;
  installed: boolean;
  path?: string;
  other_cfgs?: string[];
  last_seen: number | null;
  match_id: string | null;
  has_draft_block: boolean;
  game_state: string | null;
  team: string | null;
  hero_id: number | null;
  phase: string | null;
}

const STATE_RU: Record<string, string> = {
  DOTA_GAMERULES_STATE_HERO_SELECTION: 'выбор героев',
  DOTA_GAMERULES_STATE_STRATEGY_TIME: 'стратегия',
  DOTA_GAMERULES_STATE_PRE_GAME: 'перед стартом',
  DOTA_GAMERULES_STATE_GAME_IN_PROGRESS: 'игра идёт',
  DOTA_GAMERULES_STATE_POST_GAME: 'матч окончен',
};

function GsiCard() {
  const qc = useQueryClient();
  const heroes = useHeroes().data;
  const status = useQuery({ queryKey: ['gsi'], queryFn: () => api<GsiStatus>('/gsi/status'), refetchInterval: 5000 });
  const install = useMutation({
    mutationFn: () => api<{ path: string; removed: string[] }>('/gsi/install', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gsi'] }),
  });
  useEffect(() => subscribe((e) => e.type === 'gsi' && qc.invalidateQueries({ queryKey: ['gsi'] })), [qc]);
  const s = status.data;
  const fresh = s?.last_seen && Date.now() / 1000 - s.last_seen < 30;
  return (
    <Panel>
      <div className="panel__head">
        <h2>Интеграция с игрой</h2>
        <span className={`pill ${fresh ? 'c-good' : ''}`}>{fresh ? 'Дота на связи' : 'нет данных'}</span>
      </div>
      {s && !s.dota_found && <ErrorBox error="Не нашёл установку Dota 2." />}
      {s?.dota_found && (
        <>
          <p className="hint">
            Game State Integration — официальный способ Valve: игра сама присылает стадию матча, твою сторону и героя.
            Память игры не читается, файлы игры не меняются — добавляется только конфиг в папку gamestate_integration. (Сетки героев — отдельная карточка ниже: это твой файл в Steam, он пишется только по кнопке.)
          </p>
          {s.installed ? (
            <p className="muted">Конфиг установлен (порт {s.port}). После установки Доту нужно один раз перезапустить.</p>
          ) : (
            <button className="btn btn--accent" onClick={() => install.mutate()} disabled={install.isPending}>
              Установить конфиг GSI
            </button>
          )}
          {install.data?.removed.length ? <p className="hint">Удалён старый конфиг: {install.data.removed.join(', ')}</p> : null}
          {install.error && <ErrorBox error={install.error} />}
          {s.last_seen && (
            <dl className="kv">
              <dt>Стадия</dt>
              <dd>{STATE_RU[s.game_state ?? ''] ?? s.game_state ?? '—'}</dd>
              <dt>Сторона</dt>
              <dd>{s.team ?? '—'}</dd>
              <dt>Мой герой</dt>
              <dd>{s.hero_id ? heroes?.byId.get(s.hero_id)?.name : '—'}</dd>
              <dt>Драфт от игры</dt>
              <dd>{s.has_draft_block ? 'приходит' : 'не приходит (вводи вручную или читай с экрана)'}</dd>
            </dl>
          )}
        </>
      )}
    </Panel>
  );
}

interface CollectStatus {
  enabled: boolean;
  limit_mb: number;
  used_mb: number;
  drafts: number;
  frames: number;
  labeled_drafts: number;
  error: string | null;
}

function VisionCard() {
  const go = useUi((s) => s.go);
  const settings = useSettings().data;
  const save = useSaveSettings();
  const status = useQuery({
    queryKey: ['vision'],
    queryFn: () =>
      api<{
        enabled: boolean;
        calibrated: boolean;
        calibration_auto: boolean;
        labeled_frames: number;
        error: string | null;
        collect: CollectStatus;
        auto: { auto_enabled: boolean; enabled_at: number | null; last: { evaluation?: { precision: number | null; frames: number; drafts: number } } | null };
      }>('/vision/status'),
  });
  const s = status.data;
  const c = s?.collect;
  const ev = s?.auto.last?.evaluation;
  return (
    <Panel>
      <div className="panel__head">
        <h2>Чтение драфта с экрана</h2>
        <span className="pill">{s?.enabled ? (s.auto.auto_enabled ? 'включено само' : 'включено') : 'выключено'}</span>
      </div>
      <p className="hint">
        Экспериментально и отключаемо: захват только окна Доты и сравнение портретов с шаблонами. Включается само, когда точность
        на кадрах из твоих матчей не ниже 98%.
      </p>
      <Toggle
        on={settings?.vision_collect ?? true}
        onChange={(vision_collect) => settings && save.mutate({ ...settings, vision_collect })}
        label="Собирать кадры драфта для калибровки (во время выбора героев)"
      />
      <Slider
        label="Место под кадры"
        value={settings?.vision_collect_mb ?? 500}
        min={100}
        max={3000}
        step={100}
        onChange={(vision_collect_mb) => settings && save.mutate({ ...settings, vision_collect_mb })}
        format={(v) => `${v} МБ`}
      />
      <p className="muted small">
        Собрано: {c?.drafts ?? 0} драфтов, {c?.frames ?? 0} кадров, {c?.used_mb ?? 0} МБ; с разметкой из доски драфта: {c?.labeled_drafts ?? 0}.
        {c?.error ? ` Последняя ошибка: ${c.error}` : ''}
      </p>
      <p className="muted small">
        Калибровка: {s?.calibrated ? (s.calibration_auto ? 'найдена автоматически' : 'сохранена вручную') : 'нет (пресет)'} · подтверждено в
        мастере: {s?.labeled_frames ?? 0}
        {ev && ev.precision !== null ? ` · точность ${Math.round(ev.precision * 1000) / 10}% на ${ev.frames} кадрах` : ''}
      </p>
      <button className="btn btn--accent" onClick={() => go('vision')}>
        Открыть мастер калибровки
      </button>
    </Panel>
  );
}

function HotkeyField({ label, value, onChange, dotaKeys }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  dotaKeys: Set<string>;
}) {
  const [recording, setRecording] = useState(false);
  const busy = dotaKeys.has(dotaKeyName(value));
  const noMods = !value.includes('+');
  return (
    <div className="field">
      <span className="label">{label}</span>
      <div className="hotkey">
        <button
          className={`btn hotkey__btn ${recording ? 'is-rec' : ''}`}
          onClick={() => setRecording(true)}
          onBlur={() => setRecording(false)}
          onKeyDown={(e) => {
            if (!recording) return;
            e.preventDefault();
            if (e.key === 'Escape') return setRecording(false);
            const combo = comboFromEvent(e.nativeEvent);
            if (combo) {
              onChange(combo);
              setRecording(false);
            }
          }}
        >
          {recording ? 'Нажми сочетание…' : value}
        </button>
        {(busy || noMods) && (
          <span className="hotkey__warn">
            {noMods ? 'без Ctrl/Alt/Shift клавиша пропадёт в игре' : `${dotaKeyName(value)} занята в Доте — сочетание может мешать`}
          </span>
        )}
      </div>
    </div>
  );
}

function OverlayCard() {
  const ui = useUi();
  const ov = ui.overlay;
  const setOv = (patch: Partial<typeof ov>) => ui.set({ overlay: { ...ov, ...patch } });
  const hotkeyError = useHotkeyStatus((s) => s.error);
  const keys = useQuery({ queryKey: ['dota-keys'], queryFn: () => api<{ keys: string[] }>('/dota/keybinds') });
  const display = useQuery({
    queryKey: ['dota-display'],
    queryFn: () => api<{ found: boolean; label?: string; width?: number; height?: number; fullscreen?: boolean }>('/dota/display'),
  });
  const dotaKeys = useMemo(() => new Set(keys.data?.keys ?? []), [keys.data]);
  return (
    <Panel>
      <div className="panel__head">
        <h2>Оверлей</h2>
        <button className="btn btn--accent" onClick={() => toggleOverlay()}>
          Показать / скрыть
        </button>
      </div>
      {display.data?.found && (
        <p className={display.data.fullscreen ? 'error-box' : 'hint'}>
          Дота: {display.data.width}×{display.data.height}, {display.data.label}.
          {display.data.fullscreen
            ? ' Поверх эксклюзивного полноэкранного режима оверлей не виден: включи «Окно без рамки» в настройках видео Доты.'
            : ' Оверлей будет поверх игры.'}
        </p>
      )}
      <HotkeyField label="Показать / скрыть" value={ov.toggle} onChange={(toggle) => setOv({ toggle })} dotaKeys={dotaKeys} />
      <HotkeyField label="Сквозные клики вкл/выкл" value={ov.interact} onChange={(interact) => setOv({ interact })} dotaKeys={dotaKeys} />
      {hotkeyError && <ErrorBox error={hotkeyError} />}
      <div className="field">
        <span className="label">Стекло поверх игры</span>
        <Segmented
          small
          value={ov.effect}
          onChange={(effect) => setOv({ effect })}
          options={[
            { value: 'acrylic', label: 'Acrylic (размытие игры)' },
            { value: 'tint', label: 'Тонировка (легче)' },
          ]}
        />
      </div>
      <div className="field">
        <span className="label">Режим</span>
        <Segmented
          small
          value={ov.mode}
          onChange={(mode) => setOv({ mode })}
          options={[
            { value: 'auto', label: 'Авто' },
            { value: 'draft', label: 'Драфт' },
            { value: 'build', label: 'Билд' },
          ]}
        />
      </div>
      <Slider label="Непрозрачность" value={ov.opacity} min={0.35} max={1} step={0.05} onChange={(opacity) => setOv({ opacity })} format={(v) => `${Math.round(v * 100)}%`} />
      <Toggle on={ov.autoShow} onChange={(autoShow) => setOv({ autoShow })} label="Показывать оверлей, когда начался выбор героев (GSI)" />
      <Toggle on={ov.autoPerf} onChange={(autoPerf) => setOv({ autoPerf })} label="Во время матча — режим производительности (без Acrylic и анимаций)" />
      <p className="hint">
        «Авто»: на стадии драфта — подсказки, с началом матча — билд против врагов (после подключения GSI на этапе 5).
        Позиция и размер оверлея запоминаются.
      </p>
    </Panel>
  );
}

function AdviceCard() {
  const s = useSettings().data;
  const save = useSaveSettings();
  const [draft, setDraft] = useState<Settings | null>(null);
  useEffect(() => setDraft(s ?? null), [s]);
  if (!draft) return null;
  const upd = (patch: Partial<Settings>) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    save.mutate(next);
  };
  return (
    <Panel>
      <h2>Подсказки</h2>
      <div className="field">
        <span className="label">Моя позиция по умолчанию</span>
        <Segmented value={draft.pos} onChange={(pos) => upd({ pos })} options={[1, 2, 3, 4, 5].map((p) => ({ value: p, label: String(p) }))} />
      </div>
      <Toggle on={draft.use_comfort} onChange={(use_comfort) => upd({ use_comfort })} label="Учитывать мой опыт на героях" />
      <Slider
        label="Вес личного опыта"
        value={draft.comfort_weight}
        min={0}
        max={1}
        step={0.05}
        onChange={(comfort_weight) => upd({ comfort_weight })}
        format={(v) => `${Math.round(v * 100)}%`}
      />
      <p className="hint">
        По твоей истории первая игра на новом герое выигрывается заметно реже. В оценку идёт эта доля эффекта: часть его
        объясняется тем, что новых героев чаще пробуют в неудачных драфтах.
      </p>
      <Slider label="Тир-лист за дней" value={draft.tier_days} min={3} max={30} step={1} onChange={(tier_days) => upd({ tier_days })} />
      {save.error && <ErrorBox error={save.error} />}
    </Panel>
  );
}

function DataCard() {
  const health = useHealth().data;
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api<Job[]>('/jobs') });
  const [lines, setLines] = useState<string[]>([]);
  const running = jobs.data?.find((j) => j.kind === 'refresh' && j.status === 'running');
  const last = jobs.data?.find((j) => j.kind === 'refresh');
  const start = useMutation({
    mutationFn: () => api<Job>('/data/refresh', { method: 'POST' }),
    onSuccess: (j) => {
      setLines(j.log);
      qc.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'job' || e.kind !== 'refresh') return;
        if (typeof e.line === 'string') setLines((xs) => [...xs.slice(-300), e.line as string]);
        if (e.status !== 'running') qc.invalidateQueries();
      }),
    [qc],
  );
  const shown = lines.length ? lines : last?.log ?? [];
  return (
    <Panel>
      <h2>Данные</h2>
      {health && (
        <dl className="kv">
          <dt>Патч</dt>
          <dd>{health.patch}</dd>
          <dt>Матчей в базе</dt>
          <dd>{health.matches.toLocaleString('ru')}</dd>
          <dt>Модель обучена</dt>
          <dd>{health.model_trained ?? 'нет'}</dd>
          <dt>Stratz</dt>
          <dd>{health.stratz ? 'токен есть' : 'нет токена в .env'}</dd>
          <dt>Аккаунт</dt>
          <dd>{health.account_id ?? 'не указан'}</dd>
        </dl>
      )}
      <button className="btn btn--accent" onClick={() => start.mutate()} disabled={!!running || start.isPending}>
        {running ? 'Обновляю…' : 'Обновить данные после патча'}
      </button>
      <p className="hint">Константы, новые матчи, пересчёт модели (около 15 минут), Stratz и твоя история.</p>
      {start.error && <ErrorBox error={start.error} />}
      {last?.status === 'failed' && <ErrorBox error={last.error} />}
      {shown.length > 0 && <pre className="joblog">{shown.slice(-14).join('\n')}</pre>}
    </Panel>
  );
}
