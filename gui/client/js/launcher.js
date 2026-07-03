// Tess OS Mission Control — Mission Launcher: command tiles + saved tiles.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { el, clear } from './dom.js';

const GROUPS = [
  {
    title: 'Mission Lifecycle',
    names: [
      'add-mission', 'review-mission', 'route-mission', 'show-owner', 'show-active-guilds',
      'show-risks', 'show-next-moves', 'wake', 'close', 'finalize', 'summary', 'reset',
      'code-red', 'initiate',
    ],
  },
  {
    title: 'Orchestrator Modes',
    names: ['founder-mode', 'revenue-mode', 'product-mode', 'cx-mode', 'ops-mode', 'strategic-mode'],
  },
  {
    title: 'Crew & System',
    names: ['list-agents', 'add-agent', 'remove-agent', 'brainstorm', 'feedback', 'help'],
  },
];

// Commands that take a free-text argument open a one-field prompt first.
export const ARG_COMMANDS = new Map([
  ['add-mission', { label: 'Mission brief', placeholder: 'Describe the mission…' }],
  ['code-red', { label: 'Situation brief', placeholder: 'Describe the emergency…' }],
  ['add-agent', { label: 'Agent name', placeholder: 'e.g. Freya' }],
  ['remove-agent', { label: 'Agent name', placeholder: 'e.g. Freya' }],
  ['feedback', { label: 'Feedback', placeholder: 'What should change…' }],
]);

function groupCommands(commands) {
  const remaining = new Map(commands.map((c) => [c.name, c]));
  const groups = [];
  for (const { title, names } of GROUPS) {
    const items = [];
    for (const name of names) {
      const cmd = remaining.get(name);
      if (cmd) {
        items.push(cmd);
        remaining.delete(name);
      }
    }
    if (items.length) groups.push({ title, items });
  }
  if (remaining.size) groups.push({ title: 'Other', items: Array.from(remaining.values()) });
  return groups;
}

function makeTile(command, { onLaunchImmediate, onLaunchWithArg }) {
  const argSpec = ARG_COMMANDS.get(command.name);
  return el(
    'button',
    {
      type: 'button',
      className: 'tile',
      onClick: () => (argSpec ? onLaunchWithArg(command.name, argSpec) : onLaunchImmediate(command.name)),
    },
    [
      el('span', { className: 'tile__command' }, [`/${command.name}`]),
      el('span', { className: 'tile__label' }, [command.name.replace(/-/g, ' ')]),
      command.description ? el('span', { className: 'tile__desc' }, [command.description]) : null,
    ],
  );
}

export function renderCommandGroups(container, badgeEl, { commands, skippedCount }, handlers) {
  clear(container);

  if (skippedCount > 0) {
    badgeEl.textContent = `${skippedCount} file${skippedCount === 1 ? '' : 's'} skipped (malformed)`;
    badgeEl.hidden = false;
  } else {
    badgeEl.hidden = true;
  }

  for (const { title, items } of groupCommands(commands)) {
    const grid = el(
      'div',
      { className: 'tile-grid' },
      items.map((cmd) => makeTile(cmd, handlers)),
    );
    container.appendChild(
      el('div', { className: 'tile-subsection' }, [
        el('h3', { className: 'tile-subsection__title' }, [title]),
        grid,
      ]),
    );
  }
}

function makeSavedTile(mission, { onLaunch, onRemove }) {
  const preview = mission.prompt.length > 90 ? `${mission.prompt.slice(0, 90)}…` : mission.prompt;

  function remove(event) {
    event.stopPropagation();
    onRemove(mission.id);
  }
  function removeKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      remove(event);
    }
  }

  function launch() {
    onLaunch(mission);
  }
  function launchKeydown(event) {
    // Native buttons get Enter/Space activation for free; this wrapper is a
    // div (not a button) because it contains the nested remove button, so
    // keyboard activation has to be wired explicitly.
    if (event.target !== event.currentTarget) return; // let the remove button handle its own keys
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      launch();
    }
  }

  return el(
    'div',
    { className: 'tile tile--saved', role: 'button', tabindex: '0', onClick: launch, onKeydown: launchKeydown },
    [
      el('span', { className: 'tile__label' }, [mission.label]),
      el('span', { className: 'tile__desc' }, [preview]),
      el(
        'button',
        {
          type: 'button',
          className: 'tile__remove',
          'aria-label': `Remove "${mission.label}" from saved missions`,
          onClick: remove,
          onKeydown: removeKeydown,
        },
        ['×'],
      ),
    ],
  );
}

export function renderSavedMissions(sectionEl, gridEl, savedMissions, handlers) {
  sectionEl.hidden = savedMissions.length === 0;
  clear(gridEl);
  for (const mission of savedMissions) {
    gridEl.appendChild(makeSavedTile(mission, handlers));
  }
}
