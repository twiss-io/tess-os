// Tess OS Mission Control — health polling (CLI-compat + connection-lost).
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { api } from './api.js';

export function startHealthPolling({ onUpdate, intervalMs = 20000, skipInitialPoll = false }) {
  let stopped = false;

  async function poll() {
    if (stopped) return;
    try {
      const health = await api.getHealth();
      if (!stopped) onUpdate({ ok: true, health });
    } catch (err) {
      if (!stopped) onUpdate({ ok: false, error: err });
    }
  }

  if (!skipInitialPoll) poll();
  const timer = setInterval(poll, intervalMs);
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}
