/**
 * After a match the backend breaks it down by itself (backend after_match.py) and sends a "ruin"
 * event: the main window opens Profile → «Кто заруинил» on that match, the first time a match is
 * announced (the second announcement, when the replay is parsed, only refreshes it).
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { subscribe } from '../api/client';
import { useNav } from '../state/nav';
import { useUi } from '../state/ui';

const opened = new Set<number>();

export function useAfterMatch() {
  const qc = useQueryClient();
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'ruin') return;
        const id = Number(e.match_id);
        if (!id) return;
        qc.invalidateQueries({ queryKey: ['ruin', id] });
        qc.invalidateQueries({ queryKey: ['me', 'ratings'] });
        if (opened.has(id)) return;
        opened.add(id);
        useNav.getState().set({ profileTab: 'ruin', ruinId: id });
        useUi.getState().go('profile');
      }),
    [qc],
  );
}
