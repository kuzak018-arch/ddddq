import { Crosshair, Route, Shield, Users } from 'lucide-react';

import { useHeroes, useBuild } from '../api/hooks';
import { BuildView } from '../components/BuildView';
import { AttrIcon, RoleIcon } from '../components/DotaIcons';
import { Ti } from '../components/Icons';
import { Panel } from '../components/Glass';
import { HeroModeSwitch } from '../components/HeroModeSwitch';
import { HeroSearch } from '../components/HeroSearch';
import { LaneView } from '../components/LaneView';
import { Empty, ErrorBox, HeroIcon, Loading, Segmented } from '../components/ui';
import { picked, useDraft } from '../state/draft';
import { useUi } from '../state/ui';
import { useState } from 'react';

export function BuildsPage() {
  const { buildHero, buildPos, set } = useUi();
  const draftEnemies = picked(useDraft((s) => s.enemies));
  const [enemies, setEnemies] = useState<number[] | null>(null); // null = follow the draft
  const vsList = enemies ?? draftEnemies;
  const [mode, setMode] = useState<'all' | 'specialists'>('all');
  const build = useBuild(buildHero, buildPos, vsList, true, mode);
  const heroes = useHeroes().data;

  return (
    <div className="builds">
      <Panel className="builds__controls" refracting>
        <div className="panel__head">
          <HeroModeSwitch />
        </div>
        <span className="label">
          <Ti icon={Shield} />
          Мой герой
        </span>
        <div className="builds__hero">
          {buildHero && <HeroIcon id={buildHero} size="md" />}
          <HeroSearch placeholder="Мой герой…" onPick={(h) => set({ buildHero: h.id })} compact />
        </div>
        <span className="label">
          <RoleIcon pos={buildPos} size={14} className="seg-role" />
          Позиция
        </span>
        <Segmented
          value={buildPos}
          onChange={(p) => set({ buildPos: p })}
          options={[1, 2, 3, 4, 5].map((p) => ({ value: p, title: `Позиция ${p}`, label: <><RoleIcon pos={p} size={14} className="seg-role" />{p}</> }))}
        />
        <span className="label">
          <Ti icon={Users} />
          Чьи билды
        </span>
        <Segmented
          value={mode}
          onChange={setMode}
          options={[
            { value: 'all', label: 'Legend+ на позиции' },
            { value: 'specialists', label: 'Специалисты', title: 'Игроки с 30+ играми на герое за сезон (лидерборд Stratz)' },
          ]}
        />
        <span className="label">
          <Ti icon={Crosshair} />
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
        {buildHero && vsList.length > 0 && (
          <section className="builds__lane">
            <h3 className="section-title">
              <Ti icon={Route} />
              Линия
            </h3>
            <LaneView hero={buildHero} pos={buildPos} enemies={vsList} />
          </section>
        )}
      </Panel>
      <Panel className="builds__result">
        {!buildHero && <Empty>Выбери героя и позицию. Враги подтянутся из драфта, а билд подстроится под них.</Empty>}
        {buildHero && (
          <div className="panel__head">
            <h2 className="hero-card__name">
              <AttrIcon attr={heroes?.byId.get(buildHero)?.attr ?? ''} size={22} />
              {heroes?.byId.get(buildHero)?.name} · позиция {buildPos}
            </h2>
          </div>
        )}
        {build.error && <ErrorBox error={build.error} />}
        {buildHero && build.isPending && <Loading>Собираю билд…</Loading>}
        {build.data && <BuildView r={build.data.build} vs={build.data.vs} />}
      </Panel>
    </div>
  );
}
