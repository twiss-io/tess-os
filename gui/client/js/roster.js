// Tess OS Mission Control — Roster drawer (Overlay tier).
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { el, clear } from './dom.js';

export function renderRosterGuilds(bodyEl, guilds) {
  clear(bodyEl);
  for (const guild of guilds) {
    bodyEl.appendChild(
      el('div', { className: 'roster-guild' }, [
        el('div', { className: 'roster-guild__title' }, [guild.name]),
        ...guild.agents.map((agent) =>
          el('div', { className: 'roster-agent' }, [
            el('span', { className: 'roster-agent__name' }, [agent.name]),
            el('span', { className: 'roster-agent__role' }, [agent.role]),
          ]),
        ),
      ]),
    );
  }
}

export function filterRosterGuilds(bodyEl, query) {
  const q = query.trim().toLowerCase();
  for (const guildEl of bodyEl.querySelectorAll('.roster-guild')) {
    let anyVisible = false;
    for (const agentEl of guildEl.querySelectorAll('.roster-agent')) {
      const match = !q || agentEl.textContent.toLowerCase().includes(q);
      agentEl.hidden = !match;
      if (match) anyVisible = true;
    }
    guildEl.hidden = !anyVisible;
  }
}

export function setupRosterDrawer({ trigger, backdrop, drawer, closeBtn, searchInput, body }) {
  function open() {
    backdrop.hidden = false;
    drawer.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    searchInput.value = '';
    filterRosterGuilds(body, '');
    searchInput.focus();
  }

  function close() {
    backdrop.hidden = true;
    drawer.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus();
  }

  trigger.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  backdrop.addEventListener('click', close);
  searchInput.addEventListener('input', () => filterRosterGuilds(body, searchInput.value));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !drawer.hidden) close();
  });

  return { open, close };
}
