/**
 * Screen reading check: take (or upload) a screenshot of the draft, see the rects the reader uses on
 * a frame of that size (built-in layout, fitted to the frame, or the user's own), check what it
 * reads, correct mistakes (each correction teaches it how that portrait looks in this game) and
 * confirm frames, which also measures accuracy. Dragging the rects by hand is the fallback.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { api, backend } from '../api/client';
import { moveRects, resizeRects, type Rect } from '../lib/calibrate';
import { useHeroes } from '../api/hooks';
import { Panel } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { useUi } from '../state/ui';
import { Empty, ErrorBox, fmtPct, HeroIcon, Segmented, Slider, Toggle } from '../components/ui';

type Group = 'radiant' | 'dire' | 'bans';
interface Calibration {
  aspect: number;
  radiant: Rect[];
  dire: Rect[];
  bans: Rect[];
  threshold: number;
  margin: number;
  preset: boolean;
  auto?: boolean;
  source?: string;
}

const SOURCE_LABEL: Record<string, string> = {
  manual: 'твои ручные рамки',
  auto: 'найдены по кадру с известными героями',
  detected: 'встроенный профиль, подогнанный по кадру',
  profile: 'встроенный профиль для этого разрешения',
  'from-manual': 'твои ручные рамки, пересчитанные под это разрешение',
  'from-auto': 'найденные рамки, пересчитанные под это разрешение',
  edited: 'изменены, ещё не сохранены',
};
interface DetectInfo {
  portraits: number;
  score: number;
  scale: number;
  reason?: string;
}
interface SlotResult {
  hero: number | null;
  score: number;
  margin: number;
  candidates: [number, number][];
  empty: boolean;
}
type ReadResult = Record<Group, SlotResult[]> & { warnings: string[] };
interface VisionStatus {
  enabled: boolean;
  running: boolean;
  error: string | null;
  calibrated: boolean;
  labeled_frames: number;
  required_precision: number;
  dota_window: boolean;
}
interface Snapshot {
  id: string;
  width: number;
  height: number;
}
interface CollectedDraft {
  id: string;
  started: number;
  frozen: boolean;
  frames: { id: string; state: string | null; complete: boolean; width: number; height: number }[];
  labels: { radiant: number[]; dire: number[]; bans: number[]; side: string } | null;
}
interface EvalTotal {
  drafts: number;
  frames: number;
  filled: number;
  correct: number;
  precision: number | null;
  required: number;
  auto_rule: { drafts: number; frames: number; filled: number };
}

const GROUP_LABEL: Record<Group, string> = { radiant: 'Radiant', dire: 'Dire', bans: 'Баны' };
/** A new ban slot right after the last one (same size), or a default under the top bar. */
function nextBan(rects: Rect[]): Rect {
  const last = rects[rects.length - 1];
  return last ? [Math.min(0.97, last[0] + last[2] * 1.1), last[1], last[2], last[3]] : [0.3, 0.06, 0.03, 0.03];
}

const GROUP_COLOR: Record<Group, string> = { radiant: 'var(--radiant)', dire: 'var(--dire)', bans: '#c9c9d1' };

async function snapshotUrl(id: string): Promise<string> {
  const { url, token } = await backend();
  const res = await fetch(`${url}/vision/snapshots/${id}.png`, { headers: token ? { 'X-Drafter-Token': token } : {} });
  if (!res.ok) throw new Error('снимок не загрузился');
  return URL.createObjectURL(await res.blob());
}

export function VisionPage() {
  const qc = useQueryClient();
  const heroes = useHeroes().data;
  const status = useQuery({ queryKey: ['vision'], queryFn: () => api<VisionStatus>('/vision/status'), refetchInterval: 4000 });
  const saved = useQuery({ queryKey: ['vision-cal'], queryFn: () => api<Calibration>('/vision/calibration') });
  const [cal, setCalState] = useState<Calibration | null>(null);
  // the user changed the rects in the wizard: a new frame must not replace them
  const [dirty, setDirty] = useState(false);
  const setCal = (c: Calibration, edited = true) => {
    setCalState(edited ? { ...c, source: 'edited' } : c);
    setDirty(edited);
  };
  useEffect(() => {
    if (saved.data && !cal) setCal(saved.data, false);
  }, [saved.data, cal]);

  const recent = useQuery({ queryKey: ['vision-snaps'], queryFn: () => api<string[]>('/vision/snapshots') });
  const collected = useQuery({ queryKey: ['vision-collected'], queryFn: () => api<CollectedDraft[]>('/vision/collected') });
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [img, setImg] = useState<string | null>(null);
  const [group, setGroup] = useState<Group>('radiant');
  const [together, setTogether] = useState(true);
  const [result, setResult] = useState<ReadResult | null>(null);
  const [fixes, setFixes] = useState<Record<string, number | null>>({});
  const [editing, setEditing] = useState<{ group: Group; i: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  // the rects the reader itself would use on a frame of this size
  useEffect(() => {
    if (!snap || dirty) return;
    api<Calibration>(`/vision/calibration?width=${snap.width}&height=${snap.height}`).then((c) => setCal(c, false), (e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap?.id]);
  useEffect(() => {
    if (!snap) return;
    let url: string | null = null;
    snapshotUrl(snap.id).then((u) => setImg((url = u))).catch((e) => setError(String(e)));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [snap]);

  const take = useMutation({
    mutationFn: () => api<Snapshot>('/vision/snapshot', { method: 'POST' }),
    onSuccess: (s) => {
      setSnap(s);
      setResult(null);
      setFixes({});
      qc.invalidateQueries({ queryKey: ['vision-snaps'] });
    },
    onError: (e) => setError(String(e)),
  });
  const upload = async (f: File) => {
    const { url, token } = await backend();
    const res = await fetch(`${url}/vision/upload`, {
      method: 'POST',
      headers: { ...(token ? { 'X-Drafter-Token': token } : {}), 'Content-Type': 'application/octet-stream' },
      body: f,
    });
    const body = await res.json();
    if (!res.ok) return setError(body.detail ?? 'не удалось загрузить');
    setSnap(body);
    setResult(null);
    setFixes({});
    qc.invalidateQueries({ queryKey: ['vision-snaps'] });
  };
  const read = useMutation({
    mutationFn: () => api<ReadResult>('/vision/read', { body: { snapshot: snap!.id, calibration: cal } }),
    onSuccess: (r) => {
      setResult(r);
      setFixes({});
    },
    onError: (e) => setError(String(e)),
  });
  const saveCal = useMutation({
    mutationFn: () => api<Calibration>('/vision/calibration', { method: 'PUT', body: cal }),
    onSuccess: (c) => {
      setCal(c, false);
      qc.invalidateQueries({ queryKey: ['vision'] });
    },
    onError: (e) => setError(String(e)),
  });
  const label = useMutation({
    mutationFn: () => {
      const pick = (g: Group) => (cal?.[g] ?? []).map((_, i) => (`${g}${i}` in fixes ? fixes[`${g}${i}`] : result?.[g][i]?.hero ?? null));
      return api<{ learned: number }>('/vision/label', {
        body: { snapshot: snap!.id, calibration: cal, radiant: pick('radiant'), dire: pick('dire'), bans: pick('bans') },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vision'] });
      evalRun.mutate();
    },
    onError: (e) => setError(String(e)),
  });
  const evalRun = useMutation({
    mutationFn: () =>
      api<{
        results: { folder: string; frames: number; precision: number | null; recall: number | null }[];
        collected: { drafts: number; frames: number; precision: number | null; recall: number | null };
        total: EvalTotal;
      }>('/vision/evaluate', { method: 'POST' }),
  });
  const [autoInfo, setAutoInfo] = useState<string | null>(null);
  const autocal = useMutation({
    mutationFn: () =>
      api<{ calibration: Calibration | null; info: { hits: number; searched: number; fitted?: number; reason?: string } }>('/vision/autocal', {
        body: { snapshot: snap!.id },
      }),
    onSuccess: (r) => {
      if (r.calibration) {
        setCal(r.calibration);
        setResult(null);
        setAutoInfo(`Нашёл ${r.info.hits} портретов из ${r.info.searched}, в ровный ряд легли ${r.info.fitted}. Проверь рамки и сохрани.`);
      } else setAutoInfo(`Не получилось: ${r.info.reason ?? 'портреты не найдены'}.`);
    },
    onError: (e) => setError(String(e)),
  });
  const [detectInfo, setDetectInfo] = useState<string | null>(null);
  const detect = useMutation({
    mutationFn: () => api<{ calibration: Calibration | null; info: DetectInfo; saved: boolean }>('/vision/detect', { body: { snapshot: snap!.id, save: true } }),
    onSuccess: (r) => {
      if (r.calibration) {
        setCal(r.calibration, false);
        setResult(null);
        setDetectInfo(
          `Нашёл ${r.info.portraits} портретов, совпадение ${Math.round(r.info.score * 100)}%, масштаб ${r.info.scale.toFixed(3)}. Рамки для ${snap!.width}×${snap!.height} сохранены — проверь распознавание.`,
        );
        qc.invalidateQueries({ queryKey: ['vision'] });
      } else setDetectInfo(`Не получилось: ${r.info.reason ?? 'портреты не найдены'}.`);
    },
    onError: (e) => setError(String(e)),
  });
  const reset = useMutation({
    mutationFn: () => api<{ removed: boolean }>('/vision/calibration', { method: 'DELETE' }),
    onSuccess: async () => {
      setDetectInfo(null);
      setAutoInfo(null);
      setResult(null);
      const size = snap ? `?width=${snap.width}&height=${snap.height}` : '';
      setCal(await api<Calibration>(`/vision/calibration${size}`), false);
      qc.invalidateQueries({ queryKey: ['vision'] });
      qc.invalidateQueries({ queryKey: ['vision-cal'] });
    },
    onError: (e) => setError(String(e)),
  });
  const openSnapshot = (id: string) => {
    const im = new Image();
    snapshotUrl(id).then((u) => {
      im.onload = () => {
        setSnap({ id, width: im.naturalWidth, height: im.naturalHeight });
        setResult(null);
        setFixes({});
        setAutoInfo(null);
        setDetectInfo(null);
        URL.revokeObjectURL(u);
      };
      im.src = u;
    });
  };
  const draftOf = (id: string | undefined) =>
    id?.startsWith('auto-') ? collected.data?.find((d) => id.startsWith(`auto-${d.id}-`)) : undefined;
  const curDraft = draftOf(snap?.id);
  const heroName = (h: number) => heroes?.byId.get(h)?.name ?? h;
  const enable = useMutation({
    mutationFn: (on: boolean) => api('/vision/enable', { body: { on } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vision'] }),
    onError: (e) => setError(String(e)),
  });

  const rects = cal?.[group] ?? [];
  const setRects = (g: Group, rs: Rect[]) => cal && setCal({ ...cal, [g]: rs, preset: false });
  const distribute = () => {
    if (rects.length < 3) return;
    const first = rects[0]!;
    const last = rects[rects.length - 1]!;
    const n = rects.length - 1;
    setRects(group, rects.map((_, i) => [first[0] + ((last[0] - first[0]) * i) / n, first[1] + ((last[1] - first[1]) * i) / n, first[2], first[3]]));
  };
  const real = evalRun.data?.results.find((r) => r.folder.includes('labeled'));
  const total = evalRun.data?.total;
  const s = status.data;

  return (
    <div className="vision">
      <Panel className="vision__side" refracting>
        <div className="panel__head panel__head--wrap">
          <button className="btn btn--sm btn--ghost" onClick={() => useUi.getState().go('settings')} title="Вернуться в настройки">
            ← Настройки
          </button>
          <h2>Чтение экрана</h2>
          <span className="pill">эксперимент</span>
        </div>
        <p className="hint">
          Читает только картинку окна Доты (как скриншот) — без памяти игры и без изменения файлов. Работает лишь на стадии
          выбора героев. Ручная правка слота всегда важнее.
        </p>
        {error && (
          <div onClick={() => setError(null)}>
            <ErrorBox error={error} />
          </div>
        )}
        <div className="row">
          <button className="btn btn--accent" onClick={() => take.mutate()} disabled={take.isPending || !s?.dota_window} title={s?.dota_window ? '' : 'Дота не запущена'}>
            Снимок Доты
          </button>
          <button className="btn" onClick={() => file.current?.click()}>
            Загрузить скриншот
          </button>
          <input ref={file} type="file" accept="image/png,image/jpeg" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
        {!!collected.data?.length && (
          <select className="select" value={curDraft ? snap!.id : ''} onChange={(e) => e.target.value && openSnapshot(e.target.value)}>
            <option value="">Кадры из твоих матчей…</option>
            {collected.data.map((d) => (
              <optgroup
                key={d.id}
                label={`${new Date(d.started * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })} · ${d.frames.length} кадров${d.labels ? ' · размечен' : ''}`}
              >
                {d.frames.map((f, i) => (
                  <option key={f.id} value={f.id}>
                    Кадр {i + 1}
                    {f.complete ? ' — все герои (стратегия)' : ''}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        )}
        {curDraft && (
          <div className="vision__labels small">
            {curDraft.labels ? (
              <>
                <span className="muted">Разметка из доски драфта:</span>
                <span>Radiant: {curDraft.labels.radiant.map(heroName).join(', ') || '—'}</span>
                <span>Dire: {curDraft.labels.dire.map(heroName).join(', ') || '—'}</span>
                <button className="btn btn--sm" onClick={() => autocal.mutate()} disabled={autocal.isPending}>
                  {autocal.isPending ? 'Ищу портреты…' : 'Автокалибровка по этому кадру'}
                </button>
              </>
            ) : (
              <span className="muted">У этого драфта нет разметки: доска драфта не заполнялась или сторона неизвестна.</span>
            )}
            {autoInfo && <span>{autoInfo}</span>}
          </div>
        )}
        {!!recent.data?.length && (
          <select
            className="select"
            value={snap?.id ?? ''}
            onChange={(e) => {
              const id = e.target.value;
              if (!id) return;
              const im = new Image();
              snapshotUrl(id).then((u) => {
                im.onload = () => {
                  setSnap({ id, width: im.naturalWidth, height: im.naturalHeight });
                  setResult(null);
                  setFixes({});
                  URL.revokeObjectURL(u);
                };
                im.src = u;
              });
            }}
          >
            <option value="">Сохранённые снимки…</option>
            {recent.data.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        )}

        <span className="label">Рамки</span>
        {cal && (
          <p className="small">
            Сейчас: <b>{SOURCE_LABEL[cal.source ?? 'manual'] ?? cal.source}</b>
            {snap ? <span className="muted"> · кадр {snap.width}×{snap.height}</span> : null}
          </p>
        )}
        <div className="row">
          <button className="btn btn--accent" onClick={() => detect.mutate()} disabled={!snap || detect.isPending} title="Подогнать встроенный профиль по портретам на этом кадре — герои не нужны">
            {detect.isPending ? 'Ищу…' : 'Найти рамки по кадру'}
          </button>
          <button className="btn" onClick={() => reset.mutate()} disabled={reset.isPending} title="Забыть ручные и найденные рамки и читать по встроенному профилю">
            Сбросить на автоматические
          </button>
        </div>
        {detectInfo && <p className="small">{detectInfo}</p>}
        <Segmented value={group} onChange={setGroup} options={(['radiant', 'dire', 'bans'] as Group[]).map((g) => ({ value: g, label: `${GROUP_LABEL[g]} · ${cal?.[g].length ?? 0}` }))} />
        <Toggle on={together} onChange={setTogether} label="Двигать и менять размер группой" />
        <div className="row">
          <button className="btn" onClick={distribute} title="Расставить слоты ровно между первым и последним">
            Распределить
          </button>
          {group === 'bans' && (
            <>
              <button className="btn" onClick={() => setRects('bans', [...rects, nextBan(rects)])}>
                + бан
              </button>
              <button className="btn" onClick={() => setRects('bans', rects.slice(0, -1))} disabled={!rects.length}>
                − бан
              </button>
            </>
          )}
          <button
            className="btn"
            title="Рамки встроенного профиля для размера этого кадра (без подгонки)"
            onClick={async () => setCal(await api<Calibration>(`/vision/calibration/preset${snap ? `?width=${snap.width}&height=${snap.height}` : ''}`))}
          >
            Встроенный профиль
          </button>
        </div>
        {cal && (
          <>
            <Slider label="Порог уверенности" value={cal.threshold} min={0.3} max={0.9} step={0.01} onChange={(threshold) => setCal({ ...cal, threshold })} format={(v) => v.toFixed(2)} />
            <Slider label="Отрыв от второго кандидата" value={cal.margin} min={0} max={0.3} step={0.01} onChange={(margin) => setCal({ ...cal, margin })} format={(v) => v.toFixed(2)} />
          </>
        )}
        <div className="row">
          <button className="btn" onClick={() => read.mutate()} disabled={!snap || read.isPending}>
            Проверить распознавание
          </button>
          <button className="btn" onClick={() => saveCal.mutate()} disabled={!cal || saveCal.isPending}>
            Сохранить рамки
          </button>
        </div>
        {result && (
          <button className="btn btn--accent" onClick={() => label.mutate()} disabled={label.isPending}>
            Всё верно — подтвердить кадр
          </button>
        )}
        {result?.warnings.map((w) => <p key={w} className="warn">{w}</p>)}
        <p className="hint">
          Кликни по рамке, чтобы исправить героя (или правой кнопкой — «пусто»). Подтверждённый кадр учит распознавание и
          проверяет точность. «Сохранить рамки» делает их ручными: они главнее автоматики и переносятся на другие разрешения.
        </p>
        <details className="vision__how small">
          <summary>Как проверить, что всё читается без калибровки</summary>
          <ol>
            <li>В Доте дойди до выбора героев (подойдёт и лобби с ботами), дождись, пока выберут 4–5 героев.</li>
            <li>Здесь нажми «Снимок Доты», затем «Найти рамки по кадру» — рамки должны лечь на портреты в верхней полосе.</li>
            <li>«Проверить распознавание»: под рамками появятся герои. Исправь ошибки кликом и нажми «Всё верно — подтвердить кадр».</li>
            <li>Если рамки легли криво — потяни их мышью и «Сохранить рамки» (ручные). «Сбросить на автоматические» вернёт профиль.</li>
          </ol>
          <p className="muted">
            Дальше ничего делать не нужно: во время драфта программа сама подгоняет профиль по первым кадрам с героями и сама
            включает чтение, когда точность на твоих матчах дойдёт до 98%.
          </p>
        </details>

        <h3 className="section-title">Точность</h3>
        <dl className="kv">
          <dt>Подтверждено в мастере</dt>
          <dd>
            {s?.labeled_frames ?? 0} кадров{real ? `, точность ${fmtPct(real.precision)}` : ''}
          </dd>
          <dt>Из твоих матчей</dt>
          <dd>
            {evalRun.data?.collected
              ? `${evalRun.data.collected.frames} кадров в ${evalRun.data.collected.drafts} драфтах, точность ${fmtPct(evalRun.data.collected.precision)}, полнота ${fmtPct(evalRun.data.collected.recall)}`
              : '—'}
          </dd>
          <dt>Всего</dt>
          <dd>{total ? `${fmtPct(total.precision)} (${total.correct} из ${total.filled} распознанных)` : '—'}</dd>
        </dl>
        <button className="btn btn--sm" onClick={() => evalRun.mutate()} disabled={evalRun.isPending}>
          {evalRun.isPending ? 'Считаю…' : 'Пересчитать точность'}
        </button>
        {total && (
          <p className="hint">
            Включится само при ≥ {total.auto_rule.drafts} драфтах, ≥ {total.auto_rule.frames} кадрах, ≥ {total.auto_rule.filled} распознанных
            героях и точности ≥ {fmtPct(total.required, 0)}.
          </p>
        )}
        <Toggle
          on={!!s?.enabled}
          onChange={(on) => enable.mutate(on)}
          label={`Читать драфт во время выбора героев (нужно ≥ ${fmtPct(s?.required_precision ?? 0.98, 0)} на 3+ кадрах)`}
        />
        {s?.error && <p className="warn">{s.error}</p>}
      </Panel>

      <Panel className="vision__canvas">
        {!img || !snap || !cal ? (
          <Empty>
            Зайди в выбор героев (лобби с ботами подойдёт), нажми «Снимок Доты» или загрузи скриншот (F12 в Steam). Затем
            перетащи рамки на портреты героев.
          </Empty>
        ) : (
          <SnapshotEditor
            img={img}
            snap={snap}
            cal={cal}
            active={group}
            together={together}
            onChange={setRects}
            result={result}
            fixes={fixes}
            onEdit={(g, i) => setEditing({ group: g, i })}
            onClear={(g, i) => setFixes({ ...fixes, [`${g}${i}`]: null })}
          />
        )}
        {editing && (
          <div className="vision__fix glass glass--strong">
            <span className="label">
              {GROUP_LABEL[editing.group]}, слот {editing.i + 1}: кто здесь на самом деле?
            </span>
            <HeroSearch
              compact
              onPick={(h) => {
                setFixes({ ...fixes, [`${editing.group}${editing.i}`]: h.id });
                setEditing(null);
              }}
            />
            <div className="row">
              <button className="btn" onClick={() => (setFixes({ ...fixes, [`${editing.group}${editing.i}`]: null }), setEditing(null))}>
                Пусто
              </button>
              <button className="btn" onClick={() => setEditing(null)}>
                Отмена
              </button>
            </div>
            {result?.[editing.group][editing.i]?.candidates.length ? (
              <p className="hint">
                Кандидаты:{' '}
                {result[editing.group][editing.i]!.candidates.map(([h, sc]) => `${heroes?.byId.get(h)?.name} ${sc.toFixed(2)}`).join(', ')}
              </p>
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  );
}

function SnapshotEditor({ img, snap, cal, active, together, onChange, result, fixes, onEdit, onClear }: {
  img: string;
  snap: Snapshot;
  cal: Calibration;
  active: Group;
  together: boolean;
  onChange: (g: Group, rs: Rect[]) => void;
  result: ReadResult | null;
  fixes: Record<string, number | null>;
  onEdit: (g: Group, i: number) => void;
  onClear: (g: Group, i: number) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const W = snap.width;
  const H = snap.height;
  const drag = useRef<{ g: Group; i: number; mode: 'move' | 'size'; x: number; y: number; start: Rect[]; moved: boolean } | null>(null);
  const [zoomMode, setZoom] = useState<'slots' | 'top' | 'all'>('slots');
  // «Рамки»: the area around all slot rectangles, so portraits are big enough to place precisely
  // even on a 2560×1440 frame; «Верх экрана»: the top 30%; «Весь кадр»: everything.
  const all = [...cal.radiant, ...cal.dire, ...cal.bans];
  const box = all.length
    ? (() => {
        const x0 = Math.min(...all.map((r) => r[0])), x1 = Math.max(...all.map((r) => r[0] + r[2]));
        const y0 = Math.min(...all.map((r) => r[1])), y1 = Math.max(...all.map((r) => r[1] + r[3]));
        const mx = (x1 - x0) * 0.08 + 0.01, my = Math.max((y1 - y0) * 0.6, 0.03);
        const bx = Math.max(0, x0 - mx), by = Math.max(0, y0 - my);
        return { x: bx * W, y: by * H, w: (Math.min(1, x1 + mx) - bx) * W, h: (Math.min(1, y1 + my * 2.2) - by) * H };
      })()
    : { x: 0, y: 0, w: W, h: H };
  // the box follows the rectangles only between drags, so it does not run away under the cursor
  const [slotsView, setSlotsView] = useState(box);
  useEffect(() => {
    if (!drag.current) setSlotsView(box);
  }, [snap.id, zoomMode]);
  const view = zoomMode === 'slots' ? slotsView : zoomMode === 'top' ? { x: 0, y: 0, w: W, h: Math.round(H * 0.3) } : { x: 0, y: 0, w: W, h: H };

  const toFrac = (e: React.PointerEvent) => {
    const pt = svg.current!.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.current!.getScreenCTM()!.inverse());
    return { x: p.x / W, y: p.y / H };
  };
  const onDown = (e: React.PointerEvent, g: Group, i: number, mode: 'move' | 'size') => {
    if (e.button !== 0) return;
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    const p = toFrac(e);
    drag.current = { g, i, mode, x: p.x, y: p.y, start: cal[g].map((r) => [...r] as Rect), moved: false };
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = toFrac(e);
    const dx = p.x - d.x;
    const dy = p.y - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 0.001) d.moved = true;
    // a group resize scales the whole group, so the rectangles keep their spacing (see calibrate.ts)
    onChange(d.g, d.mode === 'move' ? moveRects(d.start, d.i, dx, dy, together) : resizeRects(d.start, d.i, dx, dy, together));
  };
  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved && d.mode === 'move') onEdit(d.g, d.i);
  };

  return (
    <div className="snap">
      <div className="row">
        <Segmented
          small
          value={zoomMode}
          onChange={setZoom}
          options={[
            { value: 'slots', label: 'Рамки крупно' },
            { value: 'top', label: 'Верх экрана' },
            { value: 'all', label: 'Весь кадр' },
          ]}
        />
        <span className="hint">
          {W}×{H}
        </span>
      </div>
      <svg ref={svg} className="snap__svg" viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} onPointerMove={onMove} onPointerUp={onUp}>
        <image href={img} x={0} y={0} width={W} height={H} />
        {(['radiant', 'dire', 'bans'] as Group[]).map((g) =>
          cal[g].map((r, i) => {
            const [x, y, w, h] = [r[0] * W, r[1] * H, r[2] * W, r[3] * H];
            const res = result?.[g][i];
            const key = `${g}${i}`;
            const hero = key in fixes ? fixes[key] : res?.hero ?? null;
            const isActive = g === active;
            return (
              <g key={key} className={`snap__slot ${isActive ? 'is-active' : ''}`} style={{ color: GROUP_COLOR[g] }}>
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  onPointerDown={(e) => isActive && onDown(e, g, i, 'move')}
                  onClick={() => !isActive && onEdit(g, i)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    onClear(g, i);
                  }}
                />
                {isActive && <rect className="snap__handle" x={x + w - w * 0.18} y={y + h - h * 0.3} width={w * 0.18} height={h * 0.3} onPointerDown={(e) => onDown(e, g, i, 'size')} />}
                {result && (
                  <foreignObject x={x} y={y + h + 2} width={Math.max(w, 60)} height={Math.max(h, 30)}>
                    <div className={`snap__tag ${key in fixes ? 'is-fixed' : hero ? '' : 'is-none'}`}>
                      {hero ? <HeroIcon id={hero} size="sm" /> : <span>—</span>}
                      {res && !(key in fixes) && <small>{res.score.toFixed(2)}</small>}
                    </div>
                  </foreignObject>
                )}
              </g>
            );
          }),
        )}
      </svg>
      <CropStrip snap={snap} cal={cal} />
    </div>
  );
}

/**
 * What the reader really cuts out with these rectangles: the backend crops the same frame with the
 * same code, a moment after a rectangle stops moving. A portrait that looks cut or shifted here
 * is read wrong in the game too.
 */
function CropStrip({ snap, cal }: { snap: Snapshot; cal: Calibration }) {
  const [debounced, setDebounced] = useState(cal);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(cal), 250);
    return () => clearTimeout(t);
  }, [cal]);
  const crops = useQuery({
    queryKey: ['vision-crops', snap.id, debounced],
    queryFn: () =>
      api<Record<Group, (string | null)[]> & { width: number; height: number; warnings: string[] }>('/vision/crops', {
        body: { snapshot: snap.id, calibration: debounced },
      }),
    placeholderData: (prev) => prev,
  });
  const d = crops.data;
  return (
    <div className="crops">
      <span className="label">Что вырезается из кадра {d ? `${d.width}×${d.height}` : ''}</span>
      {d?.warnings.map((w) => (
        <p key={w} className="small warn">
          {w}
        </p>
      ))}
      {crops.error && <ErrorBox error={crops.error} />}
      {(['radiant', 'dire', 'bans'] as Group[]).map((g) =>
        d?.[g]?.length ? (
          <div key={g} className="crops__row">
            <span className="crops__group" style={{ color: GROUP_COLOR[g] }}>
              {GROUP_LABEL[g]}
            </span>
            {d[g].map((src, i) => (src ? <img key={i} src={src} alt={`${GROUP_LABEL[g]} ${i + 1}`} /> : <span key={i} className="crops__none">—</span>))}
          </div>
        ) : null,
      )}
    </div>
  );
}
