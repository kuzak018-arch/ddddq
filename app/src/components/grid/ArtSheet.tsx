/**
 * «Арт из текста» and «Арт из картинки»: settings on the left, the art as the game will draw it on
 * the right; «Поставить на сетку» adds it (or replaces the art being edited).
 */
import { useEffect, useMemo, useState } from 'react';

import { glyphAdvance, FILL_GLYPHS, RAMPS } from '../../lib/grid/art';
import { ART_STEP, fitCols, imageArt, textArt, type ArtResult } from '../../lib/grid/artRender';
import { CANVAS_H, CANVAS_W, LABEL_COLOR, SLOW_CATEGORIES } from '../../lib/grid/dota';
import { clampItem, newId, type ArtItem, type ImageArtSource, type TextArtSource } from '../../lib/grid/doc';
import { activeGrid, useGrids } from '../../state/grids';
import { loadFile, saveFile } from '../../state/bgstore';
import { Sheet } from '../Sheet';
import { Segmented, Slider, Toggle } from '../ui';
import { GlyphLine } from './GridCanvas';

export type ArtKind = 'text' | 'image';

const TEXT_DEFAULT: TextArtSource = { kind: 'text', text: 'GG WP', size: 14, pitch: 11, step: ART_STEP, glyph: '@', bold: true };
const IMAGE_DEFAULT: Omit<ImageArtSource, 'key'> = {
  kind: 'image',
  cols: 70,
  pitch: 9,
  step: ART_STEP,
  contrast: 1.3,
  brightness: 0,
  invert: false,
  ramp: RAMPS[0].chars,
};

export function ArtSheet({ open, kind, editing, onClose }: { open: boolean; kind: ArtKind; editing: ArtItem | null; onClose: () => void }) {
  const [text, setText] = useState<TextArtSource>(TEXT_DEFAULT);
  const [image, setImage] = useState<Omit<ImageArtSource, 'key'> & { key: string | null }>({ ...IMAGE_DEFAULT, key: null });
  const [bmp, setBmp] = useState<ImageBitmap | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // editing an art: start from its settings
  useEffect(() => {
    if (!open) return;
    setErr(null);
    if (editing?.source.kind === 'text') setText(editing.source);
    if (editing?.source.kind === 'image') setImage(editing.source);
  }, [open, editing]);

  useEffect(() => {
    let alive = true;
    if (!image.key) return setBmp(null);
    loadFile(image.key).then(async (blob) => {
      if (!blob || !alive) return;
      try {
        const b = await createImageBitmap(blob);
        if (!alive) return;
        setBmp(b);
        // a new picture starts as big as fits the grid
        if (editing?.source.kind !== 'image' || editing.source.key !== image.key) setImage((im) => ({ ...im, cols: fitCols(b, im.pitch) }));
      } catch {
        setErr('Не получилось прочитать картинку.');
      }
    });
    return () => {
      alive = false;
    };
  }, [image.key]);

  const result: ArtResult | null = useMemo(() => {
    if (!open) return null;
    try {
      if (kind === 'text') return text.text.trim() ? textArt(text) : null;
      return bmp && image.key ? imageArt(bmp, { ...image, key: image.key }) : null;
    } catch {
      return null;
    }
  }, [open, kind, text, image, bmp]);

  // an edited art stays where it is, a new one goes to the middle
  const at = (r: ArtResult) => (editing ? { x: editing.x, y: editing.y } : { x: Math.max(0, (CANVAS_W - r.w) / 2), y: Math.max(0, (CANVAS_H - r.h) / 2) });

  const place = () => {
    if (!result) return;
    const source: ArtItem['source'] = kind === 'text' ? text : { ...image, key: image.key! };
    const s = useGrids.getState();
    const base = { id: editing?.id ?? newId(), ...at(result) };
    const item = clampItem<ArtItem>({ ...base, type: 'art', rows: result.rows, step: result.step, w: result.w, h: result.h, source });
    s.editItems((l) => (editing ? l.map((i) => (i.id === editing.id ? item : i)) : [...l, item]));
    s.select(item.id);
    onClose();
  };

  const total = activeGrid(useGrids.getState()).items.length + (result?.rows.length ?? 0);
  const tooBig = result && (result.w > CANVAS_W || result.h > CANVAS_H);
  const minPitch = Math.ceil(glyphAdvance(kind === 'text' ? text.glyph : '@'));

  return (
    <Sheet wide open={open} onClose={onClose} title={kind === 'text' ? 'Арт из текста' : 'Арт из картинки'}>
      <div className="art">
        <div className="art__controls">
          {kind === 'text' ? (
            <>
              <label className="field">
                <span className="label">Текст</span>
                <textarea className="input" rows={2} value={text.text} onChange={(e) => setText({ ...text, text: e.target.value })} placeholder="Например: GG WP" />
              </label>
              <Slider label="Высота букв, символов" value={text.size} min={4} max={30} step={1} onChange={(size) => setText({ ...text, size })} />
              <Slider
                label="Плотность: шаг символов"
                value={text.pitch}
                min={Math.min(minPitch, 6)}
                max={26}
                step={0.5}
                onChange={(pitch) => setText({ ...text, pitch })}
                format={(v) => `${v} ед.`}
              />
              <Slider label="Шаг строк" value={text.step} min={6} max={24} step={1} onChange={(step) => setText({ ...text, step })} format={(v) => `${v} ед.`} />
              <div className="field">
                <span className="label">Символ</span>
                <div className="art__glyphs">
                  {FILL_GLYPHS.map((g) => (
                    <button key={g} className={`gchip ${g === text.glyph ? 'is-on' : ''}`} onClick={() => setText({ ...text, glyph: g })}>
                      {g}
                    </button>
                  ))}
                </div>
              </div>
              <Toggle on={text.bold} onChange={(bold) => setText({ ...text, bold })} label="Жирные буквы" />
            </>
          ) : (
            <>
              <label className="btn">
                {image.key ? 'Другая картинка…' : 'Выбрать картинку…'}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    e.target.value = '';
                    if (!f) return;
                    if (f.size > 30 * 1024 * 1024) return setErr('Файл больше 30 МБ — возьми поменьше.');
                    try {
                      await createImageBitmap(f);
                    } catch {
                      return setErr('Не получилось прочитать картинку.');
                    }
                    const key = `gridart-${newId()}`;
                    await saveFile(key, f);
                    setErr(null);
                    setImage({ ...image, key });
                  }}
                />
              </label>
              <Slider label="Размер: символов в ширину" value={image.cols} min={10} max={200} step={1} onChange={(cols) => setImage({ ...image, cols })} />
              <Slider label="Плотность: шаг символов" value={image.pitch} min={5} max={20} step={0.5} onChange={(pitch) => setImage({ ...image, pitch })} format={(v) => `${v} ед.`} />
              <Slider label="Шаг строк" value={image.step} min={6} max={24} step={1} onChange={(step) => setImage({ ...image, step })} format={(v) => `${v} ед.`} />
              <Slider label="Контраст" value={image.contrast} min={0.5} max={3} step={0.05} onChange={(contrast) => setImage({ ...image, contrast })} format={(v) => v.toFixed(2)} />
              <Slider
                label="Яркость"
                value={image.brightness}
                min={-0.5}
                max={0.5}
                step={0.02}
                onChange={(brightness) => setImage({ ...image, brightness })}
                format={(v) => (v > 0 ? '+' : '') + v.toFixed(2)}
              />
              <div className="field">
                <span className="label">Символы</span>
                <Segmented small value={image.ramp} options={RAMPS.map((r) => ({ value: r.chars, label: r.label, title: r.chars.trim() }))} onChange={(ramp) => setImage({ ...image, ramp })} />
              </div>
              <Toggle on={image.invert} onChange={(invert) => setImage({ ...image, invert })} label="Наоборот: символы на другой части картинки" />
            </>
          )}
          {err && <p className="c-bad small">{err}</p>}
        </div>
        <div className="art__preview">
          <div className="art__stage">
            {result ? (
              // the whole grid, the art where it will stand: its real size against the canvas
              <svg viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} fill={LABEL_COLOR}>
                {result.rows.map((r, i) => (
                  <GlyphLine key={i} text={r.text} x={at(result).x + r.dx} y={at(result).y + i * result.step} />
                ))}
              </svg>
            ) : (
              <p className="muted small">{kind === 'text' ? 'Введи текст' : 'Выбери картинку'}</p>
            )}
          </div>
          {result && (
            <p className="hint">
              {result.rows.length} строк = {result.rows.filter((r) => r.text.trim()).length} категорий, {Math.round(result.w)}×{Math.round(result.h)} из {CANVAS_W}×{CANVAS_H}.
              Символы — только из шрифта Доты, поэтому в игре они встанут так же.
            </p>
          )}
          {tooBig && <p className="warn small">Арт больше сетки: уменьши размер или плотность, иначе край не будет виден.</p>}
          {total > SLOW_CATEGORIES && <p className="warn small">В сетке будет больше {SLOW_CATEGORIES} категорий — Дота может тормозить на экране героев.</p>}
          <div className="row">
            <button className="btn btn--accent" disabled={!result} onClick={place}>
              {editing ? 'Обновить на сетке' : 'Поставить на сетку'}
            </button>
            <button className="btn btn--ghost" onClick={onClose}>
              Отмена
            </button>
          </div>
        </div>
      </div>
    </Sheet>
  );
}
