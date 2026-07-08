// Tess OS Mission Control — Timeline section.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { el, clear } from './dom.js';
import { formatShortDate } from './format.js';

export function renderTimeline(listEl, entries) {
  clear(listEl);
  if (!entries.length) {
    listEl.appendChild(el('li', { className: 'empty-state' }, ['No recent activity.']));
    return;
  }
  for (const entry of entries) {
    listEl.appendChild(
      el('li', { className: 'timeline__entry' }, [
        el('span', { className: 'timeline__date' }, [formatShortDate(entry.date)]),
        el('span', { className: 'timeline__text' }, [entry.text]),
      ]),
    );
  }
}
