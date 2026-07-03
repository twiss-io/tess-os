// Tess OS Mission Control — Live Mission View: SSE consumption + log render.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { createMissionEventSource, api } from './api.js';
import { el, clear } from './dom.js';
import { formatCurrency, formatDuration } from './format.js';

// Standardized EventSource readyState values — not read from the global
// EventSource binding, since that binding is MockEventSource in ?mock=1
// mode and must not be relied on for these constants.
const CONNECTING = 0;
const CLOSED = 2;

function appendLogLine(logEl, kind, child) {
  const line = el('div', { className: `log-line log-line--${kind} log-line--enter` }, [child]);
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  line.addEventListener('animationend', () => line.classList.remove('log-line--enter'), { once: true });
  return line;
}

export function renderAssistantMessage(logEl, message) {
  const blocks = message?.content;
  if (!Array.isArray(blocks)) return;
  for (const block of blocks) {
    if (block?.type === 'text' && typeof block.text === 'string' && block.text.trim()) {
      appendLogLine(logEl, 'assistant', document.createTextNode(block.text));
    } else if (block?.type === 'tool_use') {
      appendLogLine(logEl, 'assistant', el('span', { className: 'log-line__tool chip chip--tool' }, [`⚙ ${block.name || 'tool'}`]));
    }
  }
}

export function renderMsgEvent(logEl, data) {
  switch (data?.type) {
    case 'system':
      appendLogLine(logEl, 'system', document.createTextNode(`· session initialized${data.model ? ` (${data.model})` : ''}`));
      break;
    case 'assistant':
      renderAssistantMessage(logEl, data.message);
      break;
    case 'stderr':
      appendLogLine(logEl, 'stderr', document.createTextNode(data.text || ''));
      break;
    case 'raw':
      appendLogLine(logEl, 'raw', document.createTextNode(data.text || ''));
      break;
    default:
      break;
  }
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}

export function startLiveMission(refs, mission, { onDone, onBack }) {
  clear(refs.log);
  refs.banner.hidden = true;
  refs.section.hidden = false;
  refs.title.textContent = mission.label || mission.prompt;
  refs.summary.textContent = '';
  refs.stopBtn.disabled = false;

  function setState(status) {
    refs.section.dataset.state = status;
    refs.statusText.textContent = status;
    if (status !== 'running') refs.banner.hidden = true;
  }
  setState('running');

  const source = createMissionEventSource(mission.id);

  source.addEventListener('msg', (event) => {
    const data = parseEventData(event);
    if (data) renderMsgEvent(refs.log, data);
  });

  source.addEventListener('status', (event) => {
    const data = parseEventData(event);
    if (data?.status) setState(data.status);
  });

  source.addEventListener('done', (event) => {
    const data = parseEventData(event) || {};
    const status = data.status || 'done';
    setState(status);
    refs.stopBtn.disabled = true;
    const parts = [];
    if (typeof data.costUSD === 'number') parts.push(formatCurrency(data.costUSD));
    if (typeof data.durationMs === 'number') parts.push(formatDuration(data.durationMs));
    refs.summary.textContent = parts.join(' · ');
    onDone({ status, costUSD: data.costUSD ?? null, durationMs: data.durationMs ?? null });
  });

  source.addEventListener('error', () => {
    if (source.readyState === CONNECTING) {
      refs.banner.hidden = false;
      refs.banner.textContent = 'Connection to mission stream lost — reconnecting…';
    } else if (source.readyState === CLOSED) {
      refs.banner.hidden = false;
      refs.banner.textContent = 'Mission stream disconnected.';
    }
  });

  refs.stopBtn.onclick = () => {
    refs.stopBtn.disabled = true;
    api.stopMission(mission.id).catch(() => {
      refs.stopBtn.disabled = false;
    });
  };
  refs.backBtn.onclick = () => {
    source.close();
    onBack?.();
  };

  return { close: () => source.close() };
}
