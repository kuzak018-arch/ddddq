/** First start: the user's Steam32 id (and optionally a Stratz token), GSI, data. Skippable. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { useState } from 'react';

import { api } from '../api/client';
import { ErrorBox } from './ui';

interface Setup {
  account_id: number | null;
  has_stratz_token: boolean;
  installed: boolean;
  has_matches: boolean;
}

export function Onboarding() {
  const qc = useQueryClient();
  const setup = useQuery({ queryKey: ['setup'], queryFn: () => api<Setup>('/setup') });
  const [skipped, setSkipped] = useState(() => sessionStorage.getItem('onboarding-skip') === '1');
  const [acc, setAcc] = useState('');
  const [token, setToken] = useState('');
  const save = useMutation({
    mutationFn: async () => {
      const id = Number(acc.replace(/\D/g, ''));
      await api('/setup', { method: 'PUT', body: { account_id: id || null, stratz_token: token.trim() || null } });
      if (id) await api('/me/refresh', { method: 'POST' });
      await api('/gsi/install', { method: 'POST' }).catch(() => null); // no Dota found: can be done later
    },
    onSuccess: () => qc.invalidateQueries(),
  });
  const show = setup.data && !setup.data.account_id && !skipped;
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="onboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div
            className="onboard__card glass glass--strong"
            initial={{ y: 24, scale: 0.97 }}
            animate={{ y: 0, scale: 1 }}
            transition={{ type: 'spring', stiffness: 260, damping: 28 }}
          >
            <h2>Добро пожаловать в Dota Drafter</h2>
            <p className="muted">Пара шагов, чтобы подсказки учитывали тебя.</p>
            <label className="onboard__field">
              <span className="label">Steam ID (Friend ID в профиле Доты)</span>
              <input className="input" value={acc} onChange={(e) => setAcc(e.target.value)} placeholder="например, 1477734386" inputMode="numeric" />
              <span className="hint">Нужен для истории матчей и твоего пула героев. В Доте включи «Общедоступные данные матчей».</span>
            </label>
            <label className="onboard__field">
              <span className="label">Токен Stratz (необязательно)</span>
              <input className="input" value={token} onChange={(e) => setToken(e.target.value)} placeholder="stratz.com/api → вход через Steam → токен" type="password" />
              <span className="hint">
                Без него не будет истории матчей с оценкой игры, «Игр топов» Immortal/Divine и данных линий, а позиции и билды
                будут грубее. Бесплатный, хранится только у тебя в .env.
              </span>
            </label>
            <p className="hint">
              Ещё установлю конфиг Game State Integration в папку Доты — это официальный способ Valve узнать стадию матча и
              твоего героя. После этого Доту нужно один раз перезапустить.
            </p>
            {save.error && <ErrorBox error={save.error} />}
            <div className="row">
              <button className="btn btn--accent" onClick={() => save.mutate()} disabled={save.isPending || !acc.trim()}>
                {save.isPending ? 'Сохраняю…' : 'Готово'}
              </button>
              <button
                className="btn"
                onClick={() => {
                  sessionStorage.setItem('onboarding-skip', '1');
                  setSkipped(true);
                }}
              >
                Позже
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
