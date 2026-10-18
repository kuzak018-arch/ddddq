/** Settings card: the app's version and where new versions come from (no auto-update: releases are private). */
import { getVersion } from '@tauri-apps/api/app';
import { isTauri } from '@tauri-apps/api/core';
import { useEffect, useState } from 'react';

import { Panel } from './Glass';

export function VersionCard() {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    if (isTauri()) getVersion().then(setVersion).catch(() => undefined);
  }, []);
  return (
    <Panel>
      <div className="panel__head">
        <h2>Версия</h2>
        {version && <span className="pill">версия {version}</span>}
      </div>
      <p className="hint">
        Автообновления нет: релизы лежат в приватном репозитории. Новая версия — на GitHub, в репозитории ddddq, раздел
        Releases: скачай установщик <b>Dota.Drafter_x.y.z_x64-setup.exe</b>, закрой приложение и запусти его поверх
        старой версии. Твои настройки и данные сохраняются.
      </p>
    </Panel>
  );
}
