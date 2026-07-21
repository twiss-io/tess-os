// Tess OS Mission Control — number/date/token formatting.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss

// Server-side sentinel for internal/test messages that are not a real
// billable model — never surfaced as a model usage row.
export const SYNTHETIC_MODEL_KEY = '<synthetic>';

export function formatTokenCount(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs < 1000) return `${sign}${Math.round(abs)}`;
  const units = [
    [1_000_000_000, 'B'],
    [1_000_000, 'M'],
    [1_000, 'k'],
  ];
  for (const [threshold, suffix] of units) {
    if (abs >= threshold) {
      const scaled = (abs / threshold).toFixed(1).replace(/\.0$/, '');
      return `${sign}${scaled}${suffix}`;
    }
  }
  return `${sign}${Math.round(abs)}`;
}

// THE byModel FIX: byModel[model] is always {input, output} token sums —
// never a bare count. Always destructure; never treat the value as a number.
export function formatModelLine(model, usage) {
  const input = Number(usage?.input) || 0;
  const output = Number(usage?.output) || 0;
  return `${model} · ${formatTokenCount(input)} in / ${formatTokenCount(output)} out`;
}

export function formatCurrency(usd) {
  // Number(null) === 0, so null/undefined must be checked explicitly before
  // coercion — otherwise "cost unavailable" would render as "$0.00".
  if (usd == null) return '—';
  const n = Number(usd);
  if (!Number.isFinite(n)) return '—';
  return `$${n.toFixed(2)}`;
}

export function formatDuration(ms) {
  // Same null/undefined-coerces-to-0 trap as formatCurrency — guard first.
  if (ms == null) return '—';
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '—';
  if (n < 1000) return `${Math.round(n)}ms`;
  const totalSeconds = Math.round(n / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

// Dates from the API are plain YYYY-MM-DD strings — parse as UTC midnight so
// short-date rendering never drifts a day in either direction from the
// browser's local timezone.
export function formatShortDate(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

// Filters out the synthetic sentinel and sorts by total token volume desc —
// shared by the metrics-detail table renderer and its unit tests.
export function realModelEntries(byModel) {
  return Object.entries(byModel || {})
    .filter(([model]) => model !== SYNTHETIC_MODEL_KEY)
    .sort((a, b) => {
      const totalA = (Number(a[1]?.input) || 0) + (Number(a[1]?.output) || 0);
      const totalB = (Number(b[1]?.input) || 0) + (Number(b[1]?.output) || 0);
      return totalB - totalA;
    });
}
