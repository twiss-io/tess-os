// Tess OS Mission Control — metrics band + 7-day detail panel.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { el, clear } from './dom.js';
import { formatCurrency, formatTokenCount, formatDuration, formatShortDate, formatModelLine, realModelEntries } from './format.js';

function makeCell(label, valueNode, { mono = false, live = false } = {}) {
  const value = el('span', { className: `metric-cell__value${mono ? ' metric-cell__value--mono' : ''}` }, [valueNode]);
  return el('div', { className: `metric-cell${live ? ' metric-cell--live' : ''}` }, [
    el('span', { className: 'metric-cell__label' }, [label]),
    value,
  ]);
}

let caveatIdCounter = 0;

// Caveat icons rebuilt on every renderMetricsBand() call (tokens + cost
// cells) need their document-level outside-click listeners torn down before
// the next rebuild, or every re-render leaks one more listener forever.
// Collected here and flushed at the top of renderMetricsBand(). A caveat
// icon built once outside that render cycle (e.g. app.js's header instance)
// is fine to leave undisposed — it's only ever constructed once per boot.
let pendingCaveatTeardowns = [];

function disposeRenderedCaveatIcons() {
  for (const dispose of pendingCaveatTeardowns) dispose();
  pendingCaveatTeardowns = [];
}

export function makeCaveatIcon(text, { ariaLabel = 'More information', tooltipId } = {}) {
  const id = tooltipId || `caveat-tooltip-${++caveatIdCounter}`;
  const tooltip = el('div', { className: 'caveat__tooltip', role: 'tooltip', id, hidden: true }, [text]);
  const icon = el('button', { type: 'button', className: 'caveat__icon', 'aria-label': ariaLabel, 'aria-describedby': id }, ['i']);
  const wrap = el('span', { className: 'caveat' }, [icon, tooltip]);

  icon.addEventListener('click', (event) => {
    event.stopPropagation();
    tooltip.hidden = !tooltip.hidden;
  });
  icon.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') tooltip.hidden = true;
  });

  const onOutsideClick = (event) => {
    if (!wrap.contains(event.target)) tooltip.hidden = true;
  };
  document.addEventListener('click', onOutsideClick);

  return { element: wrap, dispose: () => document.removeEventListener('click', onOutsideClick) };
}

function makeTokensCell(totalTokens, caveatText) {
  const caveat = makeCaveatIcon(caveatText, { ariaLabel: 'About this token count', tooltipId: 'tokens-caveat-tooltip' });
  pendingCaveatTeardowns.push(caveat.dispose);
  return makeCell('Tokens (7d)', el('span', {}, [formatTokenCount(totalTokens), caveat.element]));
}

function makeCostCell(sessionCostUSD, costNote, { mono = false, live = false } = {}) {
  const caveat = makeCaveatIcon(costNote, { ariaLabel: 'About this cost figure', tooltipId: 'cost-caveat-tooltip-band' });
  pendingCaveatTeardowns.push(caveat.dispose);
  return makeCell('Session cost', el('span', {}, [formatCurrency(sessionCostUSD), caveat.element]), { mono, live });
}

function flash(cellEl) {
  cellEl.classList.remove('metric-cell--flash');
  // Force reflow so the animation restarts if it's already mid-flash.
  void cellEl.offsetWidth;
  cellEl.classList.add('metric-cell--flash');
}

export function renderMetricsBand(container, summary, liveState) {
  disposeRenderedCaveatIcons();
  clear(container);
  const t = summary.totals?.tokens || {};
  const totalTokens = (t.input || 0) + (t.output || 0) + (t.cacheRead || 0) + (t.cacheCreation || 0);

  const costCell = makeCostCell(liveState.sessionCostUSD, summary.costNote, { mono: true, live: true });
  const activeCell = makeCell('Active missions', String(liveState.activeMissions), { mono: true, live: true });
  const sessionsCell = makeCell('Sessions (7d)', String(summary.totals?.sessions ?? 0));
  const durationCell = makeCell(
    'Avg duration',
    liveState.avgDurationMs != null ? formatDuration(liveState.avgDurationMs) : '—',
    { mono: true },
  );

  const detailEl = document.getElementById('metrics-detail');
  const toggleBtn = el(
    'button',
    {
      type: 'button',
      className: 'metrics-band__toggle',
      'aria-expanded': String(!detailEl.hidden),
      'aria-controls': 'metrics-detail',
      onClick: () => {
        detailEl.hidden = !detailEl.hidden;
        toggleBtn.setAttribute('aria-expanded', String(!detailEl.hidden));
        toggleBtn.textContent = detailEl.hidden ? '7-day detail ▾' : '7-day detail ▴';
      },
    },
    [detailEl.hidden ? '7-day detail ▾' : '7-day detail ▴'],
  );

  container.append(costCell, makeTokensCell(totalTokens, summary.tokensCaveat), activeCell, sessionsCell, durationCell, toggleBtn);
  if (liveState.flashCost) flash(costCell);
  if (liveState.flashActive) flash(activeCell);
}

function renderDayRow(day) {
  const models = realModelEntries(day.byModel);
  const breakdown = el(
    'div',
    { className: 'model-breakdown' },
    models.length
      ? models.map(([model, usage]) => el('div', { className: 'model-line' }, [formatModelLine(model, usage)]))
      : [el('div', { className: 'model-line' }, ['—'])],
  );

  return el('tr', {}, [
    el('td', { className: 'metrics-table__date' }, [formatShortDate(day.date)]),
    el('td', {}, [String(day.sessions)]),
    el('td', {}, [`${formatTokenCount(day.tokens?.input)} in / ${formatTokenCount(day.tokens?.output)} out`]),
    el('td', {}, [breakdown]),
  ]);
}

export function renderMetricsDetail(container, summary, topCommands) {
  clear(container);

  const notes = el('div', { className: 'metrics-detail__notes' }, [
    el('div', {}, [summary.costNote || '']),
    el('div', {}, [summary.tokensCaveat || '']),
  ]);

  const table = el('table', { className: 'metrics-table' }, [
    el('thead', {}, [
      el('tr', {}, [
        el('th', {}, ['Date']),
        el('th', {}, ['Sessions']),
        el('th', {}, ['Tokens']),
        el('th', {}, ['By model']),
      ]),
    ]),
    el('tbody', {}, (summary.days || []).map(renderDayRow)),
  ]);

  container.append(notes, table);

  if (topCommands?.length) {
    container.appendChild(
      el('div', { className: 'metrics-commands' }, [
        el('div', { className: 'metrics-commands__title' }, ['Most-used commands (30d)']),
        el(
          'ul',
          { className: 'metrics-commands__list' },
          topCommands.slice(0, 5).map((c) => el('li', {}, [el('span', {}, [c.command]), el('span', {}, [`×${c.count}`])])),
        ),
      ]),
    );
  }
}
