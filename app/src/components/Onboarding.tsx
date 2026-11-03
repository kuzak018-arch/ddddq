/**
 * First start: a step-by-step setup in the app's glass style. Steps: hello, the Dota folder (found
 * through Steam or picked by hand), the account (Steam accounts of this PC, a preview with the rank
 * medal), the Stratz token (checked before it is saved), the game (GSI, screen reading), the look,
 * and the history download. Skippable; «Позже» brings it back next start until a Friend ID is set,
 * and Настройки → Приложение opens it again.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FolderOpen,
  Gamepad2,
  KeyRound,
  Palette,
  ScanEye,
  Sparkles,
  Swords,
  TriangleAlert,
  User,
  type LucideIcon,
} from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';
import { create } from 'zustand';

import { api } from '../api/client';
import { PAGE_ANIMS } from '../lib/pageAnim';
import { play } from '../lib/sounds';
import { rankName } from '../lib/ranks';
import { useUi } from '../state/ui';
import { BrandMark, PRESETS } from './Chrome';
import { RankMedal } from './DotaIcons';
import { ExternalLink } from './ExternalLink';
import { Ti } from './Icons';
import { ErrorBox, Segmented, Toggle } from './ui';

interface Setup {
  account_id: number | null;
  has_stratz_token: boolean;
  installed: boolean;
  has_matches: boolean;
}
interface DotaDir {
  path: string | null;
  auto: string | null;
  manual: string | null;
  manual_ok: boolean;
}
interface Account {
  account_id: number;
  name: string | null;
  recent: boolean;
  dota: boolean;
}
interface PlayerPreview {
  account_id: number;
  name: string | null;
  avatar: string | null;
  rank_tier: number | null;
  leaderboard: number | null;
  found: boolean;
  closed_note?: string;
}

/** Opened again from the settings. */
export const useWizard = create<{ open: boolean }>(() => ({ open: false }));
export const openWizard = () => useWizard.setState({ open: true });

const STEPS: { key: string; title: string; icon: LucideIcon }[] = [
  { key: 'hello', title: 'Привет', icon: Sparkles },
  { key: 'dota', title: 'Папка Доты', icon: FolderOpen },
  { key: 'account', title: 'Аккаунт', icon: User },
  { key: 'stratz', title: 'Stratz', icon: KeyRound },
  { key: 'game', title: 'Игра', icon: Gamepad2 },
  { key: 'look', title: 'Вид', icon: Palette },
  { key: 'done', title: 'Готово', icon: Check },
];

export function Onboarding() {
  const setup = useQuery({ queryKey: ['setup'], queryFn: () => api<Setup>('/setup') });
  const [skipped, setSkipped] = useState(() => sessionStorage.getItem('onboarding-skip') === '1');
  const open = useWizard((s) => s.open);
  const needed = !!setup.data && !setup.data.account_id && !skipped;
  // once open it stays open: saving the Friend ID on the way must not close it
  useEffect(() => {
    if (needed) useWizard.setState({ open: true });
  }, [needed]);
  const close = () => {
    sessionStorage.setItem('onboarding-skip', '1');
    setSkipped(true);
    useWizard.setState({ open: false });
  };
  return <AnimatePresence>{open && setup.data && <Wizard setup={setup.data} onClose={close} />}</AnimatePresence>;
}

function Wizard({ setup, onClose }: { setup: Setup; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState(1);
  const [acc, setAcc] = useState(setup.account_id ? String(setup.account_id) : '');
  const go = (to: number) => {
    setDir(to > step ? 1 : -1);
    setStep(Math.max(0, Math.min(STEPS.length - 1, to)));
  };
  const next = () => go(step + 1);
  const s = STEPS[step]!;
  return (
    <motion.div className="onboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <motion.div
        className="onboard__card wiz glass glass--strong"
        initial={{ y: 24, scale: 0.97 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: 16, scale: 0.98 }}
        transition={{ type: 'spring', stiffness: 260, damping: 28 }}
      >
        <div className="wiz__steps" role="tablist" aria-label="Шаги настройки">
          {STEPS.map((x, i) => (
            <button
              key={x.key}
              role="tab"
              aria-selected={i === step}
              className={`wiz__dot ${i === step ? 'is-on' : ''} ${i < step ? 'is-done' : ''}`}
              onClick={() => go(i)}
              title={x.title}
            >
              {i < step ? <Check size={13} strokeWidth={2.6} /> : <x.icon size={13} strokeWidth={2.2} />}
            </button>
          ))}
        </div>
        <div className="wiz__body">
          <AnimatePresence mode="wait" custom={dir} initial={false}>
            <motion.div
              key={s.key}
              className="wiz__page"
              custom={dir}
              initial={{ opacity: 0, x: 40 * dir }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -40 * dir }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              {s.key === 'hello' && <Hello />}
              {s.key === 'dota' && <DotaStep />}
              {s.key === 'account' && <AccountStep acc={acc} setAcc={setAcc} />}
              {s.key === 'stratz' && <StratzStep hasToken={setup.has_stratz_token} />}
              {s.key === 'game' && <GameStep />}
              {s.key === 'look' && <LookStep />}
              {s.key === 'done' && <DoneStep acc={acc} onClose={onClose} />}
            </motion.div>
          </AnimatePresence>
        </div>
        {s.key !== 'done' && (
          <div className="wiz__nav">
            {step > 0 ? (
              <button className="btn btn--ghost" onClick={() => go(step - 1)}>
                <ArrowLeft size={16} /> Назад
              </button>
            ) : (
              <button className="btn btn--ghost" onClick={onClose}>
                Позже
              </button>
            )}
            <span className="muted small">
              {step + 1} из {STEPS.length}
            </span>
            <SaveAndNext step={s.key} acc={acc} onNext={next} />
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

/** «Дальше»: the account step saves the Friend ID on the way. */
function SaveAndNext({ step, acc, onNext }: { step: string; acc: string; onNext: () => void }) {
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api('/setup', { method: 'PUT', body: { account_id: Number(acc) } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['setup'] });
      onNext();
    },
  });
  const id = Number(acc.replace(/\D/g, ''));
  if (step === 'account' && id) {
    return (
      <button className="btn btn--accent" onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? 'Сохраняю…' : 'Дальше'} <ArrowRight size={16} />
      </button>
    );
  }
  return (
    <button className="btn btn--accent" onClick={onNext}>
      {step === 'hello' ? 'Начать' : step === 'account' || step === 'stratz' ? 'Пропустить' : 'Дальше'} <ArrowRight size={16} />
    </button>
  );
}

function Hello() {
  return (
    <div className="wiz__hello">
      <span className="wiz__logo">
        <BrandMark />
      </span>
      <h2>Добро пожаловать в Dota Drafter</h2>
      <p className="muted">Минута настройки — и подсказки будут про тебя: твой ранг, твои герои, твоя игра.</p>
      <ul className="wiz__feats">
        <li>
          <Ti icon={Swords} />
          Кого взять и кого банить прямо во время драфта, с причинами
        </li>
        <li>
          <Ti icon={ScanEye} />
          Драфт читается с экрана, оверлей поверх игры
        </li>
        <li>
          <Ti icon={Sparkles} />
          Мета, билды против врагов, линии, игры топов
        </li>
      </ul>
    </div>
  );
}

function DotaStep() {
  const qc = useQueryClient();
  const d = useQuery({ queryKey: ['setup-dota'], queryFn: () => api<DotaDir>('/setup/dota') });
  const [text, setText] = useState('');
  const save = useMutation({
    mutationFn: (path: string | null) => api<DotaDir>('/setup/dota', { method: 'PUT', body: { path } }),
    onSuccess: (r) => {
      qc.setQueryData(['setup-dota'], r);
      setText('');
    },
  });
  const browse = useMutation({
    mutationFn: () => api<{ path: string | null }>('/setup/dota/browse', { method: 'POST' }),
    onSuccess: (r) => r.path && save.mutate(r.path),
  });
  const v = d.data;
  return (
    <>
      <h2>
        <Ti icon={FolderOpen} />
        Папка Доты
      </h2>
      <p className="muted">Туда ставится конфиг Game State Integration — официальный способ Valve сообщать стадию матча и твоего героя.</p>
      {v?.path ? (
        <div className="wiz__found is-ok">
          <Check size={18} />
          <div>
            <b>{v.manual_ok ? 'Выбрана вручную' : 'Нашёл через Steam'}</b>
            <code>{v.path}</code>
          </div>
        </div>
      ) : (
        v && (
          <div className="wiz__found is-warn">
            <TriangleAlert size={18} />
            <div>
              <b>Не нашёл Доту через Steam</b>
              <span className="small">Укажи папку «dota 2 beta»: Steam → библиотека → Dota 2 → Управление → Просмотреть локальные файлы.</span>
            </div>
          </div>
        )
      )}
      <div className="row">
        <button className="btn" onClick={() => browse.mutate()} disabled={browse.isPending || save.isPending}>
          <Ti icon={FolderOpen} />
          {browse.isPending ? 'Жду выбора…' : 'Выбрать папку…'}
        </button>
        {v?.manual && (
          <button className="btn btn--ghost" onClick={() => save.mutate(null)}>
            Искать через Steam
          </button>
        )}
      </div>
      <div className="wiz__inline">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="или вставь путь: D:\SteamLibrary\steamapps\common\dota 2 beta" />
        <button className="btn" onClick={() => save.mutate(text)} disabled={!text.trim() || save.isPending}>
          Сохранить
        </button>
      </div>
      {(save.error || browse.error) && <ErrorBox error={save.error ?? browse.error} />}
      <p className="hint">Файлы Доты программа не меняет: в эту папку кладётся только наш конфиг GSI.</p>
    </>
  );
}

function AccountStep({ acc, setAcc }: { acc: string; setAcc: (v: string) => void }) {
  const accounts = useQuery({ queryKey: ['setup-accounts'], queryFn: () => api<{ accounts: Account[] }>('/setup/accounts') });
  const id = Number(acc.replace(/\D/g, ''));
  const [q, setQ] = useState<number | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setQ(id > 0 && id < 2 ** 32 ? id : null), 500);
    return () => clearTimeout(t);
  }, [id]);
  const preview = useQuery({
    queryKey: ['player', String(q)],
    queryFn: () => api<PlayerPreview>(`/players/lookup?q=${q}`),
    enabled: !!q,
    retry: false,
    staleTime: 10 * 60_000,
  });
  const list = accounts.data?.accounts.filter((a) => a.dota || a.name) ?? [];
  const p = preview.data;
  return (
    <>
      <h2>
        <Ti icon={User} />
        Твой аккаунт
      </h2>
      <p className="muted">По нему — история матчей, твой пул героев и ранг для подсказок.</p>
      {list.length > 0 && (
        <div className="wiz__accounts">
          <span className="label">Входили в Steam на этом ПК</span>
          {list.slice(0, 4).map((a) => (
            <button key={a.account_id} className={`wiz__acc ${id === a.account_id ? 'is-on' : ''}`} onClick={() => setAcc(String(a.account_id))}>
              <b>{a.name ?? `ID ${a.account_id}`}</b>
              <span className="muted small">
                {a.account_id}
                {a.recent ? ' · последний вход' : ''}
                {a.dota ? '' : ' · без Доты'}
              </span>
            </button>
          ))}
        </div>
      )}
      <label className="onboard__field">
        <span className="label">Friend ID (в Доте: «Друзья → Добавить друга» или под ником в профиле)</span>
        <input className="input" value={acc} onChange={(e) => setAcc(e.target.value.replace(/[^\d]/g, ''))} placeholder="например, 1477734386" inputMode="numeric" />
      </label>
      {q && (
        <div className="wiz__preview">
          {preview.isFetching && <span className="muted small">Ищу игрока…</span>}
          {p && (
            <>
              {p.avatar ? <img src={p.avatar} alt="" /> : <span className="wiz__avatar" />}
              <RankMedal tier={p.rank_tier} leaderboard={p.leaderboard} size={48} />
              <div>
                <b>{p.name ?? `Игрок ${p.account_id}`}</b>
                <span className="muted small">{p.found ? rankName(p.rank_tier) : 'OpenDota и Stratz такого не знают — проверь число'}</span>
              </div>
            </>
          )}
          {preview.error && <span className="muted small">Проверить не вышло (нет сети?) — сохраню как есть.</span>}
        </div>
      )}
      {p?.closed_note && <p className="warn small">{p.closed_note}</p>}
      <p className="hint">Чтобы история была видна, в Доте включи: Настройки → Социальное → «Общедоступные данные матчей».</p>
    </>
  );
}

function StratzStep({ hasToken }: { hasToken: boolean }) {
  const qc = useQueryClient();
  const [token, setToken] = useState('');
  const check = useMutation({
    mutationFn: async () => {
      const r = await api<{ ok: boolean; error: string | null; note?: string }>('/setup/stratz-check', { method: 'POST', body: { token } });
      if (r.ok) {
        await api('/setup', { method: 'PUT', body: { stratz_token: token.trim() } });
        void qc.invalidateQueries({ queryKey: ['setup'] });
      }
      return r;
    },
  });
  const r = check.data;
  return (
    <>
      <h2>
        <Ti icon={KeyRound} />
        Токен Stratz
      </h2>
      <p className="muted">
        Бесплатный. С ним — позиции и билды точнее, «Игры топов» Immortal / Divine, данные линий и разбор твоих матчей. Хранится только у
        тебя на ПК.
      </p>
      <ol className="wiz__how">
        <li>
          Открой <ExternalLink href="https://stratz.com/api">stratz.com/api</ExternalLink>
        </li>
        <li>Войди через Steam (кнопка справа сверху)</li>
        <li>Скопируй строку «API Token» и вставь сюда</li>
      </ol>
      {hasToken && !r && <p className="c-good small">Токен уже сохранён. Можно вставить новый или пропустить шаг.</p>}
      <div className="wiz__inline">
        <input className="input" value={token} onChange={(e) => setToken(e.target.value)} placeholder="eyJhbGciOi…" type="password" />
        <button className="btn btn--accent" onClick={() => check.mutate()} disabled={!token.trim() || check.isPending}>
          {check.isPending ? 'Проверяю…' : 'Проверить'}
        </button>
      </div>
      {r && (r.ok ? <p className="c-good small">✓ Токен работает и сохранён.{r.note ? ` ${r.note}.` : ''}</p> : <p className="c-bad small">{r.error}</p>)}
      {check.error && <ErrorBox error={check.error} />}
    </>
  );
}

function GameStep() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['gsi-status'], queryFn: () => api<{ dota_found: boolean; installed: boolean }>('/gsi/status') });
  const vision = useQuery({ queryKey: ['vision-status'], queryFn: () => api<{ enabled: boolean }>('/vision/status') });
  const install = useMutation({
    mutationFn: () => api('/gsi/install', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gsi-status'] }),
  });
  const reading = useMutation({
    mutationFn: (on: boolean) => api('/vision/enable', { method: 'POST', body: { on } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vision-status'] }),
  });
  const st = status.data;
  return (
    <>
      <h2>
        <Ti icon={Gamepad2} />
        Связь с игрой
      </h2>
      <div className={`wiz__found ${st?.installed ? 'is-ok' : st && !st.dota_found ? 'is-warn' : ''}`}>
        {st?.installed ? <Check size={18} /> : <Gamepad2 size={18} />}
        <div>
          <b>Game State Integration</b>
          <span className="small">
            {st?.installed
              ? 'Установлен. Если Дота запущена — перезапусти её один раз.'
              : st && !st.dota_found
                ? 'Сначала укажи папку Доты на втором шаге.'
                : 'Дота сама присылает стадию матча, твою сторону и героя. Память игры не читается.'}
          </span>
        </div>
        {st?.dota_found && !st.installed && (
          <button className="btn btn--sm btn--accent" onClick={() => install.mutate()} disabled={install.isPending}>
            {install.isPending ? 'Ставлю…' : 'Установить'}
          </button>
        )}
      </div>
      {install.error && <ErrorBox error={install.error} />}
      {vision.data && (
        <Toggle
          on={vision.data.enabled}
          onChange={(on) => reading.mutate(on)}
          label="Читать драфт с экрана (как скриншот окна Доты: герои сами попадают на доску)"
        />
      )}
      <p className="hint">Оверлей поверх игры открывается сам, когда начинается выбор героев. Клавиши — в настройках.</p>
    </>
  );
}

function LookStep() {
  const ui = useUi();
  return (
    <>
      <h2>
        <Ti icon={Palette} />
        Как будет выглядеть
      </h2>
      <div className="field">
        <span className="label">Тема</span>
        <Segmented
          small
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
      <div className="wiz__bgs">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className={`wiz__bg ${ui.background.kind === 'preset' && ui.background.id === p.id ? 'is-on' : ''}`}
            style={{ background: p.css }}
            onClick={() => ui.set({ background: { kind: 'preset', id: p.id } })}
            title={p.name}
          >
            <span>{p.name}</span>
          </button>
        ))}
      </div>
      <div className="field">
        <span className="label">Переход между вкладками</span>
        <Segmented small value={ui.pageAnim} onChange={(pageAnim) => ui.set({ pageAnim })} options={PAGE_ANIMS} />
      </div>
      <p className="hint">Свою картинку, GIF или видео на фон, иконку и эффекты — в Настройках → Оформление.</p>
    </>
  );
}

function DoneStep({ acc, onClose }: { acc: string; onClose: () => void }) {
  const qc = useQueryClient();
  const go = useUi((s) => s.go);
  const id = Number(acc);
  const load = useMutation({ mutationFn: () => api('/me/refresh', { method: 'POST' }) });
  useEffect(() => {
    const s = useUi.getState().sounds;
    if (s.on) play('done', s.volume);
    if (id) load.mutate();
    // once, when the last step opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="wiz__hello">
      <span className="wiz__logo is-done">
        <Check size={40} strokeWidth={2.4} />
      </span>
      <h2>Всё готово</h2>
      {id ? (
        <p className="muted">
          {load.isPending
            ? 'Загружаю твою историю матчей и пул героев…'
            : load.isError
              ? 'Историю загрузить не вышло — нажми «Обновить историю» в профиле позже.'
              : 'История загружена: подсказки учитывают твоих героев.'}
        </p>
      ) : (
        <p className="muted">Friend ID можно указать позже в настройках — тогда подсказки начнут учитывать твоих героев.</p>
      )}
      {load.isPending && <div className="spinner" />}
      <button
        className="btn btn--accent"
        onClick={() => {
          void qc.invalidateQueries();
          go('draft');
          onClose();
        }}
      >
        <Ti icon={Swords} />
        Открыть драфт
      </button>
    </div>
  );
}
