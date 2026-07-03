// tess-gui test helper — polls until a condition is true.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// app.js's boot() is an un-awaitable side effect (it runs automatically at
// module load, exactly as it would when the browser loads the real page) —
// tests synchronize with it by polling the DOM for a post-boot marker
// instead of reaching into app.js's internals.
export async function waitFor(conditionFn, { timeout = 3000, interval = 20 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const result = conditionFn();
    if (result) return result;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
  throw new Error(`waitFor: condition not met within ${timeout}ms`);
}
