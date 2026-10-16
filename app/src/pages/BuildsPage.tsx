import { useHeroes, useBuild } from '../api/hooks';
import { BuildView } from '../components/BuildView';
import { Panel } from '../components/Glass';
import { HeroSearch } from '../components/HeroSearch';
import { Empty, ErrorBox, HeroIcon, Segmented } from '../components/ui';
import { picked, useDraft } from '../state/draft';
import { useUi } from '../state/ui';
import { useState } from 'react';

export function BuildsPage() {
  const { buildHero, buildPos, set } = useUi();
  const draftEnemies = picked(useDraft((s) => s.enemies));
  const [enemies, setEnemies] = useState<number[] | null>(null); // null = follow the draft
  const vsList = enemies ?? draftEnemies;
  const build = useBuild(buildHero, buildPos, vsList, true);
  const heroes = useHeroes().data;

  return (
    <div className="builds">
      <Panel className="builds__controls" refracting>
        <div className="panel__head">
          <h2>Билды</h2>
        </div>
        <span className="label">Мой герой</span>
        <div className="builds__hero">
          {buildHero && <HeroIcon id={buildHero} size="md" />}
          <HeroSearch placeholder="Мой герой…" onPick={(h) => set({ buildHero: h.id })} compact />
        </div>
        <span className="label">Позиция</span>
        <Segmented value={buildPos} onChange={(p) => set({ buildPos: p })} options={[1, 2, 3, 4, 5].map((p) => ({ value: p, label: String(p) }))} />
        <span className="label">
          Враги {enemies === null && draftEnemies.length > 0 && <span className="muted">— из драфта</span>}
        </span>
        <div className="builds__enemies">
          {vsList.map((e) => (
            <span key={e} title="Убрать" onClick={() => setEnemies(vsList.filter((x) => x !== e))}>
              <HeroIcon id={e} size="md" onClick={() => undefined} />
            </span>
          ))}
        </div>
        {vsList.length < 5 && (
          <HeroSearch
            placeholder="Добавить врага…"
            unavailable={new Set([...vsList, ...(buildHero ? [buildHero] : [])])}
            onPick={(h) => setEnemies([...vsList, h.id])}
            compact
          />
        )}
        <div className="row">
          <button className="btn" onClick={() => setEnemies(null)} disabled={enemies === null}>
            Взять из драфта
          </button>
          <button className="btn" onClick={() => setEnemies([])} disabled={!vsList.length}>
            Очистить
          </button>
        </div>
      </Panel>
      <Panel className="builds__result">
        {!buildHero && <Empty>Выбери героя и позицию. Враги подтянутся из драфта, а билд подстроится под них.</Empty>}
        {buildHero && (
          <div className="panel__head">
            <h2>
              {heroes?.byId.get(buildHero)?.name} · позиция {buildPos}
            </h2>
          </div>
        )}
        {build.error && <ErrorBox error={build.error} />}
        {build.data && <BuildView b={build.data.build} vs={build.data.vs} />}
      </Panel>
    </div>
  );
}
