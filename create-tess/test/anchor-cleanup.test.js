// anchor-cleanup.test.js — the npm test sweep is safe when two runs overlap:
// each run's snapshot has its own name, a run never removes what it did not
// see at its start while another live run's snapshot exists, and it does the
// precise sweep once no other run is alive. Runs against a temp tess root,
// never the real ~/.config/tess.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { SNAPSHOT_PREFIX, snapshotPath, sweep } from './anchor-cleanup.js';

function fakeTess() {
  const root = mkdtempSync(join(tmpdir(), 'anchor-cleanup-test-'));
  const tess = join(root, 'tess');
  const snaps = join(root, 'snaps');
  mkdirSync(join(tess, 'brain', 'projects', 'keep'), { recursive: true });
  writeFileSync(join(tess, 'brain', 'projects', 'keep', 'id'), 'k');
  mkdirSync(snaps);
  return { root, tess, snaps };
}

function addRunLeftovers(tess) {
  mkdirSync(join(tess, 'brain', 'projects', 'added'), { recursive: true });
  writeFileSync(join(tess, 'brain', 'projects', 'added', 'id'), 'a');
  mkdirSync(join(tess, 'anchor-blobs'), { recursive: true });
  writeFileSync(join(tess, 'anchor-blobs', 'blob1'), 'x');
}

function deadPid() {
  return spawnSync(process.execPath, ['-e', '']).pid;
}

test('each run gets its own snapshot file name', () => {
  const a = snapshotPath('/x');
  const b = snapshotPath('/x');
  assert.notEqual(a, b);
  assert.ok(basename(a).startsWith(SNAPSHOT_PREFIX) && a.endsWith('.json'));
  assert.ok(basename(a).startsWith(`${SNAPSHOT_PREFIX}${process.pid}-`), 'names the runner PID');
});

test('a live overlapping run keeps what this run did not see at its start', (t) => {
  const { root, tess, snaps } = fakeTess();
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const mine = snapshotPath(snaps);
  assert.equal(sweep('snapshot', mine, { tessDir: tess }), 0);
  // Another run (this very test process: alive) took its snapshot too.
  const other = join(snaps, `${SNAPSHOT_PREFIX}other.json`);
  writeFileSync(other, JSON.stringify({ pid: process.pid, blobs: [], brain: [], dirs: [] }));
  addRunLeftovers(tess);
  assert.equal(sweep('final', mine, { tessDir: tess, owner: deadPid() }), 0);
  assert.ok(existsSync(join(tess, 'brain', 'projects', 'added', 'id')), 'other run may own it');
  assert.ok(existsSync(join(tess, 'anchor-blobs', 'blob1')), 'fresh unnamed copy kept');
  assert.ok(existsSync(other), 'the live run keeps its snapshot');
  assert.ok(!existsSync(mine), 'this run removes only its own snapshot');
});

test('with no other live run the precise sweep runs and stale snapshots go', (t) => {
  const { root, tess, snaps } = fakeTess();
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const mine = snapshotPath(snaps);
  assert.equal(sweep('snapshot', mine, { tessDir: tess }), 0);
  const stale = join(snaps, `${SNAPSHOT_PREFIX}stale.json`);
  writeFileSync(stale, JSON.stringify({ pid: deadPid(), blobs: [], brain: [], dirs: [] }));
  addRunLeftovers(tess);
  assert.equal(sweep('final', mine, { tessDir: tess }), 0);
  assert.deepEqual(readdirSync(join(tess, 'brain', 'projects')), ['keep'], 'pre-existing folder kept, added one removed');
  assert.ok(!existsSync(join(tess, 'anchor-blobs')), 'new unnamed copy and the dir it created removed');
  assert.deepEqual(readdirSync(snaps), [], 'own and dead-runner snapshots removed');
});
