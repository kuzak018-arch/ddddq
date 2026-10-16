import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { api, subscribe } from '../api/client';
import { useHealth, useHeroes, useSaveSettings, useSettings } from '../api/hooks';
import type { Job, Settings } from '../api/types';
import { heroArt, PRESETS } from '../components/Chrome';
import { Glass } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { refractionSupported } from '../glass/refraction';
import { ErrorBox, Segmented, Slider, Toggle } from '../components/ui';
import { saveBackgroundFile } from '../state/bgstore';
import { useUi } from '../state/ui';

export function SettingsPage() {
  return (
    <div className="settings">
      <AppearanceCard />
      <div className="settings__col">
        <AdviceCard />
        <DataCard />
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
    <Glass className="panel" refracting>
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
      <Toggle
        on={ui.refraction && refractionSupported}
        onChange={(refraction) => ui.set({ refraction })}
        label={refractionSupported ? 'Преломление по краям стекла' : 'Преломление (недоступно в этом движке)'}
      />
      <Toggle on={ui.performance} onChange={(performance) => ui.set({ performance })} label="Режим производительности (без размытия и анимаций)" />
    </Glass>
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
    <Glass className="panel">
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
    </Glass>
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
    <Glass className="panel">
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
    </Glass>
  );
}
