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
    // These files still render as tiles (see server/routes/commands.js
    // handleCommands) — the frontmatter parse just failed, so the tile's
    // description ends up empty. "skipped" would wrongly imply exclusion.
    badgeEl.textContent =
      skippedCount === 1 ? '1 file had an unreadable description' : `${skippedCount} files had unreadable descriptions`;
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

  function remove() {
    onRemove(mission.id);
  }
  function removeKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      remove();
    }
  }

  // The wrapper is a plain, non-interactive container (no role/tabindex) —
  // the launch tile and the remove control are both real <button>s as
  // siblings inside it, not one button-role element wrapping another real
  // button (invalid nested interactive controls). Native buttons get
  // Enter/Space activation for free, so neither needs a custom keydown
  // handler for its own activation; the remove button keeps one only to
  // stop its keyboard activation from also reaching the launch button.
  return el('div', { className: 'tile-wrapper' }, [
    el(
      'button',
      { type: 'button', className: 'tile tile--saved', onClick: () => onLaunch(mission) },
      [el('span', { className: 'tile__label' }, [mission.label]), el('span', { className: 'tile__desc' }, [preview])],
    ),
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
  ]);
}

export function renderSavedMissions(sectionEl, gridEl, savedMissions, handlers) {
  sectionEl.hidden = savedMissions.length === 0;
  clear(gridEl);
  for (const mission of savedMissions) {
    gridEl.appendChild(makeSavedTile(mission, handlers));
  }
}
