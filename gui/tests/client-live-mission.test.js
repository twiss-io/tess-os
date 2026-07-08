// tess-gui client tests — live-mission.js unit coverage: the 'done'
// idempotency guard, isolated from any timing/mock-reconnect model so the
// regression assertion can't be accidentally satisfied by a race instead of
// the actual guard.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { installDomEnv } from './helpers/dom-env.js';

installDomEnv();

// A minimal stand-in for the real (or Mock) EventSource: startLiveMission
// only ever calls addEventListener/close/readyState on it, all provided by
// EventTarget + this subclass — no fixture script, no reconnect simulation,
// just direct control over exactly which/how-many 'done' events fire.
let lastInstance = null;
class FakeEventSource extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  constructor(url) {
    super();
    this.url = url;
    this.readyState = 1;
    this.closeCalls = 0;
    lastInstance = this;
  }

  close() {
    this.closeCalls += 1;
    this.readyState = 2;
  }
}
globalThis.EventSource = FakeEventSource;

const { startLiveMission } = await import('../client/js/live-mission.js');

function makeRefs() {
  return {
    log: document.createElement('div'),
    banner: document.createElement('div'),
    section: document.createElement('section'),
    title: document.createElement('h2'),
    summary: document.createElement('p'),
    stopBtn: document.createElement('button'),
    statusText: document.createElement('span'),
    backBtn: document.createElement('button'),
  };
}

test("startLiveMission: a replayed 'done' (simulating a real-browser reconnect) does not fire onDone twice", () => {
  const refs = makeRefs();
  const doneCalls = [];

  startLiveMission(refs, { id: 'm1', label: 'test mission' }, {
    onDone: (payload) => doneCalls.push(payload),
    onBack: () => {},
  });

  const source = lastInstance;
  assert.ok(source, 'startLiveMission must construct an EventSource for the mission');

  const emitDone = (data) => source.dispatchEvent(new MessageEvent('done', { data: JSON.stringify(data) }));

  // First 'done' — the mission genuinely finishes.
  emitDone({ status: 'done', costUSD: 0.05, durationMs: 4000 });
  assert.equal(doneCalls.length, 1, 'onDone must fire once for the genuine completion');
  assert.deepEqual(doneCalls[0], { status: 'done', costUSD: 0.05, durationMs: 4000 });
  assert.equal(source.closeCalls, 1, "the handler must call close() so a real browser will not auto-reconnect and replay 'done' again");

  // A real EventSource does not close itself when the server ends the HTTP
  // response after 'done' — it auto-reconnects and the server replays the
  // identical status+done for the (now non-running) mission. Simulating
  // that exact replay directly here, independent of any timer/mock
  // reconnect model, proves the guard itself (not a timing coincidence)
  // is what stops the double count.
  emitDone({ status: 'done', costUSD: 0.05, durationMs: 4000 });
  assert.equal(doneCalls.length, 1, "a replayed 'done' must not fire onDone a second time");
  assert.equal(source.closeCalls, 1, 'close() must not be called again on the replay');
});

test('startLiveMission: a genuine status change to done, followed by the terminal done event, still only fires onDone once', () => {
  const refs = makeRefs();
  const doneCalls = [];

  startLiveMission(refs, { id: 'm2', label: 'test mission 2' }, {
    onDone: (payload) => doneCalls.push(payload),
    onBack: () => {},
  });

  const source = lastInstance;
  source.dispatchEvent(new MessageEvent('status', { data: JSON.stringify({ status: 'done' }) }));
  assert.equal(refs.section.dataset.state, 'done');
  assert.equal(doneCalls.length, 0, "a 'status' event alone must never fire onDone");

  source.dispatchEvent(new MessageEvent('done', { data: JSON.stringify({ status: 'done', costUSD: 0.1, durationMs: 5000 }) }));
  assert.equal(doneCalls.length, 1);
  assert.equal(refs.stopBtn.disabled, true, 'the stop button must be disabled once the mission is done');
});
