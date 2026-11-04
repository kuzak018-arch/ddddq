/** The demo site's strip under the title bar: what this is and where the full app is. */
import { DOWNLOAD_URL } from '../demo/api';

export function DemoBanner() {
  return (
    <div className="demo-banner" role="note">
      <span>
        <b>Демо в браузере.</b> Драфт, мета, герои и билды — по данным патча программы. Оверлей поверх игры, чтение драфта с экрана,
        подсказки в матче и твой профиль — в программе для Windows.
      </span>
      <a className="btn btn--sm btn--accent" href={DOWNLOAD_URL} target="_blank" rel="noreferrer">
        Скачать программу
      </a>
    </div>
  );
}
