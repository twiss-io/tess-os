// Tess OS Mission Control — dashboard client entry point.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// Boots the dashboard: reads the auth token from the URL (then strips it —
// see server/index.js's token model), wires ?mock=1 fixtures if present,
// fetches everything the at-rest view needs in parallel, and wires up every
// interaction. Each concern (launcher, live view, metrics, roster, timeline)
// owns its own render/update functions in js/*.js — this file is the
// composition root, not where rendering logic lives.
import { api, setToken, ApiError } from './js/api.js';
import { el } from './js/dom.js';
import { formatCurrency } from './js/format.js';
import { startHealthPolling } from './js/health.js';
import { openPrompt } from './js/modal.js';
import { renderCommandGroups, renderSavedMissions } from './js/launcher.js';
import { startLiveMission } from './js/live-mission.js';
import { renderMetricsBand, renderMetricsDetail, makeCaveatIcon } from './js/metrics.js';
import { renderRosterGuilds, setupRosterDrawer } from './js/roster.js';
import { renderTimeline } from './js/timeline.js';

const refs = {
  banners: document.getElementById('app-banners'),
  cliStatusDot: document.getElementById('cli-status-dot'),
  headerCostGroup: document.getElementById('header-cost-group'),
  headerCost: document.getElementById('header-session-cost'),
  headerActive: document.getElementById('header-active-missions'),
  metricsBand: document.getElementById('metrics-band'),
  metricsDetail: document.getElementById('metrics-detail'),
  launcherView: document.getElementById('launcher-view'),
  missionInput: document.getElementById('mission-input'),
  missionLaunchBtn: document.getElementById('mission-launch-btn'),
  saveToggle: document.getElementById('mission-save-toggle'),
  saveLabelInput: document.getElementById('mission-save-label'),
  savedSection: document.getElementById('saved-missions-section'),
  savedGrid: document.getElementById('saved-missions-grid'),
  commandsSkippedBadge: document.getElementById('commands-skipped-badge'),
  commandGroups: document.getElementById('command-groups'),
  liveView: document.getElementById('live-view'),
  liveBack: document.getElementById('live-view-back'),
  liveStatusText: document.getElementById('live-view-status'),
  liveTitle: document.getElementById('live-view-title'),
  liveSummary: document.getElementById('live-view-summary'),
  liveStop: document.getElementById('live-view-stop'),
  liveBanner: document.getElementById('live-view-banner'),
  liveLog: document.getElementById('live-view-log'),
  timelineList: document.getElementById('timeline-list'),
  rosterTrigger: document.getElementById('roster-trigger'),
  rosterBackdrop: document.getElementById('roster-backdrop'),
  rosterDrawer: document.getElementById('roster-drawer'),
  rosterClose: document.getElementById('roster-close'),
  rosterSearch: document.getElementById('roster-search'),
  rosterBody: document.getElementById('roster-body'),
};

const liveRefs = {
  section: refs.liveView,
  backBtn: refs.liveBack,
  statusText: refs.liveStatusText,
  title: refs.liveTitle,
  summary: refs.liveSummary,
  stopBtn: refs.liveStop,
  banner: refs.liveBanner,
  log: refs.liveLog,
};

const state = {
  summary: { days: [], totals: {}, missionCostUSD: 0, costNote: '', tokensCaveat: '' },
  metricsCommands: [],
  savedMissions: [],
  sessionCostUSD: 0,
  activeMissions: 0,
  durations: [],
  flashCostOnce: false,
  flashActiveOnce: false,
};

let currentLiveHandle = null;

function addBanner(id, text, { type = 'warning', dismissable = true } = {}) {
  removeBanner(id);
  const children = [text];
  if (dismissable) {
    children.push(el('button', { type: 'button', className: 'banner__dismiss', 'aria-label': 'Dismiss', onClick: () => removeBanner(id) }, ['×']));
  }
  refs.banners.appendChild(el('div', { className: `banner banner--${type}`, dataset: { bannerId: id } }, children));
}

function removeBanner(id) {
  refs.banners.querySelector(`[data-banner-id="${id}"]`)?.remove();
}

function showLauncher() {
  refs.liveView.hidden = true;
  refs.launcherView.hidden = false;
}

function showLive() {
  refs.launcherView.hidden = true;
  refs.liveView.hidden = false;
}

function avgDurationMs() {
  if (!state.durations.length) return null;
  return state.durations.reduce((a, b) => a + b, 0) / state.durations.length;
}

function refreshMetrics() {
  renderMetricsBand(refs.metricsBand, state.summary, {
    sessionCostUSD: state.sessionCostUSD,
    activeMissions: state.activeMissions,
    avgDurationMs: avgDurationMs(),
    flashCost: state.flashCostOnce,
    flashActive: state.flashActiveOnce,
  });
  state.flashCostOnce = false;
  state.flashActiveOnce = false;
  refs.headerCost.textContent = formatCurrency(state.sessionCostUSD);
  refs.headerActive.textContent = `${state.activeMissions} active`;
}

function attachLiveMission(mission) {
  showLive();
  currentLiveHandle?.close();
  currentLiveHandle = startLiveMission(liveRefs, mission, {
    onBack: showLauncher,
    onDone: ({ status, costUSD, durationMs }) => {
      state.activeMissions = Math.max(0, state.activeMissions - 1);
      if (typeof costUSD === 'number') {
        state.sessionCostUSD += costUSD;
        state.flashCostOnce = true;
      }
      if (typeof durationMs === 'number') state.durations.push(durationMs);
      refreshMetrics();
    },
  });
}

async function launchMission(prompt, label) {
  try {
    const { id } = await api.createMission(prompt, label);
    state.activeMissions += 1;
    state.flashActiveOnce = true;
    refreshMetrics();
    attachLiveMission({ id, label, prompt });
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      addBanner('mission-limit', 'Mission limit reached — 3 missions are already running. Stop one before starting another.');
    } else {
      addBanner('mission-launch-failed', 'Could not start the mission — try again.', { type: 'error' });
    }
  }
}

const savedHandlers = {
  onLaunch: (mission) => launchMission(mission.prompt, mission.label),
  onRemove: async (id) => {
    try {
      await api.deleteSavedMission(id);
      state.savedMissions = state.savedMissions.filter((m) => m.id !== id);
      renderSavedMissions(refs.savedSection, refs.savedGrid, state.savedMissions, savedHandlers);
    } catch {
      addBanner('remove-saved-failed', 'Could not remove this saved mission.');
    }
  },
};

const commandHandlers = {
  onLaunchImmediate: (name) => launchMission(`/${name}`),
  onLaunchWithArg: async (name, argSpec) => {
    const value = await openPrompt({ title: `/${name}`, label: argSpec.label, placeholder: argSpec.placeholder });
    if (value == null) return;
    await launchMission(`/${name} ${value}`);
  },
};

refs.missionLaunchBtn.addEventListener('click', async () => {
  const prompt = refs.missionInput.value.trim();
  if (!prompt) return;
  const shouldSave = refs.saveToggle.checked;
  const label = refs.saveLabelInput.value.trim() || prompt.slice(0, 80);

  if (shouldSave) {
    try {
      const saved = await api.createSavedMission(label, prompt);
      state.savedMissions.push(saved);
      renderSavedMissions(refs.savedSection, refs.savedGrid, state.savedMissions, savedHandlers);
    } catch {
      addBanner('save-mission-failed', 'Could not save this mission as a tile.');
    }
  }

  refs.missionInput.value = '';
  refs.saveToggle.checked = false;
  refs.saveLabelInput.hidden = true;
  refs.saveLabelInput.value = '';
  await launchMission(prompt, shouldSave ? label : undefined);
});

refs.saveToggle.addEventListener('change', () => {
  refs.saveLabelInput.hidden = !refs.saveToggle.checked;
});

const rosterDrawer = setupRosterDrawer({
  trigger: refs.rosterTrigger,
  backdrop: refs.rosterBackdrop,
  drawer: refs.rosterDrawer,
  closeBtn: refs.rosterClose,
  searchInput: refs.rosterSearch,
  body: refs.rosterBody,
});
void rosterDrawer;

function applyHealth(result) {
  if (result.ok) {
    refs.cliStatusDot.dataset.state = 'ok';
    refs.cliStatusDot.setAttribute('aria-label', 'CLI status: connected');
    removeBanner('disconnected');
    const claude = result.health.claude || {};
    if (claude.compatible === false) {
      const found = claude.version ? `found ${claude.version}` : 'Claude Code CLI not detected';
      addBanner(
        'cli-incompatible',
        `Claude Code CLI version ${claude.minVersion} required, ${found} — some features may not work.`,
        { dismissable: false },
      );
    } else {
      removeBanner('cli-incompatible');
    }
  } else {
    refs.cliStatusDot.dataset.state = 'disconnected';
    refs.cliStatusDot.setAttribute('aria-label', 'CLI status: disconnected');
    addBanner('disconnected', 'Connection to the tess-gui server lost — retrying…', { type: 'error', dismissable: false });
  }
}

async function boot() {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  const mockMode = url.searchParams.get('mock') === '1';
  url.searchParams.delete('token');
  history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);

  if (mockMode) {
    const { installMock } = await import('./js/mock.js');
    installMock();
  }
  setToken(token);

  let health, commands, roster, summary, metricsCommands, timeline, missions, savedMissions;
  try {
    [health, commands, roster, summary, metricsCommands, timeline, missions, savedMissions] = await Promise.all([
      api.getHealth(),
      api.getCommands(),
      api.getRoster(),
      api.getMetricsSummary(7),
      api.getMetricsCommands(30),
      api.getTimeline(),
      api.getMissions(),
      api.getSavedMissions(),
    ]);
  } catch {
    addBanner('boot-failed', 'Could not reach the tess-gui server. Refresh to retry.', { type: 'error', dismissable: false });
    return;
  }

  applyHealth({ ok: true, health });
  state.summary = summary;
  state.metricsCommands = metricsCommands.commands || [];
  state.savedMissions = savedMissions.missions || [];

  // Built once here (not on every refreshMetrics() re-render, unlike the
  // metrics-band cells) since the header cost figure is a one-off element
  // that lives for the whole page lifetime.
  const headerCaveat = makeCaveatIcon(state.summary.costNote, {
    ariaLabel: 'About this cost figure',
    tooltipId: 'cost-caveat-tooltip-header',
  });
  refs.headerCostGroup.appendChild(headerCaveat.element);

  renderCommandGroups(refs.commandGroups, refs.commandsSkippedBadge, commands, commandHandlers);
  renderSavedMissions(refs.savedSection, refs.savedGrid, state.savedMissions, savedHandlers);
  renderRosterGuilds(refs.rosterBody, roster.guilds || []);
  renderTimeline(refs.timelineList, timeline.entries || []);
  renderMetricsDetail(refs.metricsDetail, state.summary, state.metricsCommands);

  state.sessionCostUSD = typeof summary.missionCostUSD === 'number' ? summary.missionCostUSD : 0;
  const runningMissions = (missions.missions || []).filter((m) => m.status === 'running');
  state.activeMissions = runningMissions.length;
  refreshMetrics();

  if (runningMissions.length) attachLiveMission(runningMissions[0]);

  startHealthPolling({ onUpdate: applyHealth, skipInitialPoll: true });
}

boot();
