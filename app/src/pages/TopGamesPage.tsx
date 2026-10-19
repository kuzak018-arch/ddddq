/** «Игры топов»: matches of Immortal / Divine+ players and pros on a hero. Comes in stage 3. */
import { Panel } from '../components/Glass';

export function TopGamesPage() {
  return (
    <div className="soon">
      <Panel className="soon__card" refracting>
        <span className="kicker">Скоро</span>
        <h1>Игры топов</h1>
        <p className="muted">
          Выбираешь героя — и видишь его матчи у Immortal, Divine+ и про-игроков из Stratz: исход, KDA, нетворс, LH/DN, GPM,
          длительность, покупки с таймингами, прокачку и таланты. Плюс сводка по герою: винрейт и медианные тайминги ключевых
          предметов.
        </p>
        <p className="hint">Этот раздел появится на этапе 3.</p>
      </Panel>
    </div>
  );
}
