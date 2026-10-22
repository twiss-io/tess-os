// v1.0 security audit — create-tess/git-template-source/unauthenticated-template-executed-and-anchored
//
// On 3eba77d an explicit --template-source (or the ambient TESS_TEMPLATE_SOURCE)
// was cloned over any of https/git/ssh/scp, with no release-signature check,
// and its tessctl was then run as the operator and anchored. Now:
//   * only https:// remote sources (or a local folder named with the flag);
//   * only a release tag (v1.2.3), fetched alone;
//   * its OpenPGP and SSH release signatures are verified with the keys the
//     package ships (release-verify.js), before anything is checked out or run.
import { after, test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  chmodSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { isSafeTemplateSource, fetchTemplate, BUNDLED_TEMPLATE_DIR } from '../src/scaffold.js';
import { fetchVerifiedRelease, loadReleaseTrust, verifyReleaseTag } from '../src/release-verify.js';

const PKG_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ENTRY = join(PKG_DIR, 'bin', 'create-tess.mjs');
const HAS_GPG = spawnSync('gpg', ['--version']).status === 0;
const HAS_SSH = !spawnSync('ssh-keygen', ['-?']).error;

function tmp(prefix) {
  return mkdtempSync(join(tmpdir(), prefix));
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { encoding: 'utf8', ...opts });
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} failed: ${r.stderr}`);
  return r.stdout;
}

// A signing identity like the real release one: an OpenPGP key in an
// isolated GNUPGHOME and an ed25519 SSH key.
let IDENT = null;
function identity() {
  if (IDENT) return IDENT;
  const home = tmp('ct-gpg-');
  chmodSync(home, 0o700);
  const env = { ...process.env, GNUPGHOME: home };
  run('gpg', ['--batch', '--passphrase', '', '--quick-gen-key', 'Release Test <rel@test>',
    'ed25519', 'sign', 'never'], { env });
  const fpr = /^fpr:+([0-9A-F]{40}):/m.exec(run('gpg', ['--with-colons', '--list-keys'], { env }))[1];
  const armored = run('gpg', ['--armor', '--export', fpr], { env });
  const sshDir = tmp('ct-ssh-');
  run('ssh-keygen', ['-q', '-t', 'ed25519', '-N', '', '-C', 'rel', '-f', join(sshDir, 'k')]);
  const b64 = readFileSync(join(sshDir, 'k.pub'), 'utf8').split(' ')[1];
  const sshFpr = 'SHA256:' +
    createHash('sha256').update(Buffer.from(b64, 'base64')).digest('base64').replace(/=+$/, '');
  IDENT = {
    env, fpr, sshKey: join(sshDir, 'k'),
    trust: {
      pgpFpr: fpr, sshFpr, pgpKey: Buffer.from(armored),
      sshSigners: `twiss-release namespaces="tess-release" ssh-ed25519 ${b64}\n`,
    },
  };
  return IDENT;
}

after(() => {
  if (IDENT) spawnSync('gpgconf', ['--kill', 'gpg-agent'], { env: IDENT.env });
});

// An upstream repo whose tree carries a tessctl that would leave a marker if
// it were ever run, tagged `tag`, signed per `how`.
function upstream(tag, how = { pgp: true, ssh: true }) {
  const id = identity();
  const repo = tmp('ct-up-');
  const marker = join(repo, '..', `${repo.split('/').pop()}-RAN`);
  const git = (...a) => run('git', ['-C', repo, ...a], { env: id.env });
  git('init', '-q', '-b', 'main');
  git('config', 'user.email', 'rel@test');
  git('config', 'user.name', 'Rel');
  mkdirSync(join(repo, '.tess', 'bin'), { recursive: true });
  writeFileSync(join(repo, '.tess', 'bin', 'tessctl'),
    `#!/usr/bin/env python3\nopen(${JSON.stringify(marker)}, "w").write("ran")\n`);
  writeFileSync(join(repo, 'README.md'), 'template\n');
  git('add', '-A');
  git('commit', '-q', '-m', 'release');
  const commit = git('rev-parse', 'HEAD').trim();
  const tree = git('rev-parse', 'HEAD^{tree}').trim();
  let msg = `Release ${tag}\n`;
  if (how.ssh) {
    const manifest = `tess-release-manifest/1\ntag ${how.sshTag || tag}\nobject ${commit}\ntree ${tree}\n`;
    const sig = run('ssh-keygen', ['-Y', 'sign', '-f', id.sshKey, '-n', 'tess-release'],
      { input: manifest });
    msg += '\nTess-Release-SSH-Signature: tess-release-manifest/1\n' +
      sig.trim().split('\n').map((l) => '    ' + l).join('\n') + '\n';
  }
  const msgFile = join(repo, '..', `${repo.split('/').pop()}-msg`);
  writeFileSync(msgFile, msg);
  git('tag', ...(how.pgp ? ['-s', '-u', id.fpr] : ['-a']), '--cleanup=verbatim', '-F', msgFile, tag, commit);
  return { repo, marker, commit };
}

test('only https:// or a local folder is an allowed template source', () => {
  assert.equal(isSafeTemplateSource('https://github.com/twiss-io/tess-os.git'), true);
  assert.equal(isSafeTemplateSource(PKG_DIR), true);
  for (const bad of ['git://github.com/twiss-io/tess-os.git', 'ssh://git@github.com/x/y.git',
    'git@github.com:twiss-io/tess-os.git', 'file:///etc', 'ext::sh -c id', '-x', 'http://x/y.git']) {
    assert.equal(isSafeTemplateSource(bad), false, bad);
  }
});

test('a git template must name a release tag; branches and missing refs are refused before git runs', () => {
  const staging = tmp('ct-stage-');
  for (const ref of [null, 'main', 'deadbeef', 'create-tess-v1.0.0']) {
    assert.throws(
      () => fetchTemplate('https://example.invalid/tess-os.git', staging, ref),
      /must name a signed Tess OS release tag/,
    );
  }
  assert.deepEqual(readdirSync(staging), [], 'nothing was fetched');
});

test('the shipped release keys are what a git template is checked against', () => {
  const trust = loadReleaseTrust(BUNDLED_TEMPLATE_DIR);
  assert.match(trust.pgpFpr, /^[0-9A-F]{40}$/);
  assert.match(trust.sshFpr, /^SHA256:/);
  assert.ok(trust.pgpKey.length > 0 && /twiss-release/.test(trust.sshSigners));
});

test('a correctly signed release is fetched, and nothing in it is run', { skip: !(HAS_GPG && HAS_SSH) }, () => {
  const up = upstream('v9.9.9');
  const staging = tmp('ct-stage-');
  const commit = fetchVerifiedRelease(up.repo, staging, 'v9.9.9', identity().trust);
  assert.equal(commit, up.commit);
  assert.ok(existsSync(join(staging, '.tess', 'bin', 'tessctl')));
  assert.ok(!existsSync(up.marker), 'template code must not run during the fetch');
});

test('a release signed by another OpenPGP key is refused and never checked out', { skip: !(HAS_GPG && HAS_SSH) }, () => {
  const up = upstream('v9.9.8');
  const staging = tmp('ct-stage-');
  const trust = { ...identity().trust, pgpFpr: 'EBEABC618C11B6A7340A7D1601DD637667B8CC89' };
  assert.throws(() => fetchVerifiedRelease(up.repo, staging, 'v9.9.8', trust),
    /not a signed Tess OS release .*not the Tess OS release key/);
  assert.deepEqual(readdirSync(staging), [], 'nothing checked out, .git removed');
  assert.ok(!existsSync(up.marker));
});

test('an unsigned annotated tag is refused', { skip: !(HAS_GPG && HAS_SSH) }, () => {
  const up = upstream('v9.9.7', { pgp: false, ssh: false });
  const staging = tmp('ct-stage-');
  assert.throws(() => fetchVerifiedRelease(up.repo, staging, 'v9.9.7', identity().trust),
    /not a signed Tess OS release/);
  assert.deepEqual(readdirSync(staging), []);
});

test('the SSH release signature is required and bound to this tag', { skip: !(HAS_GPG && HAS_SSH) }, () => {
  const noSsh = upstream('v9.9.6', { pgp: true, ssh: false });
  assert.throws(() => fetchVerifiedRelease(noSsh.repo, tmp('ct-stage-'), 'v9.9.6', identity().trust),
    /no SSH release signature/);
  // An SSH signature made for another tag name does not verify for this one.
  const renamed = upstream('v9.9.5', { pgp: true, ssh: true, sshTag: 'v1.0.0' });
  assert.throws(() => fetchVerifiedRelease(renamed.repo, tmp('ct-stage-'), 'v9.9.5', identity().trust),
    /SSH release signature does not verify/);
});

test('without gpg, the SSH signature alone must verify (the tessctl update policy)', { skip: !(HAS_GPG && HAS_SSH) }, () => {
  const up = upstream('v9.9.4');
  const staging = tmp('ct-stage-');
  const repoDir = staging;
  run('git', ['-C', repoDir, 'init', '-q']);
  run('git', ['-C', repoDir, 'fetch', '-q', '--no-tags', up.repo, '+refs/tags/v9.9.4:refs/tags/v9.9.4']);
  const has = (cmd) => cmd !== 'gpg';
  assert.equal(verifyReleaseTag(repoDir, 'v9.9.4', identity().trust, { has }), up.commit);
  assert.throws(() => verifyReleaseTag(repoDir, 'v9.9.4', identity().trust, { has: () => false }),
    /needs gpg or ssh-keygen/);
});

function cli(args, env = {}) {
  const target = tmp('ct-target-');
  rmSync(target, { recursive: true, force: true });
  const e = { ...process.env, ...env };
  if (!('TESS_TEMPLATE_SOURCE' in env)) delete e.TESS_TEMPLATE_SOURCE;
  return spawnSync(process.execPath, [ENTRY, '--yes', '--operator=Alex', `--target=${target}`,
    '--no-git-init', '--no-gate-hooks', '--no-onboarding', ...args], { encoding: 'utf8', env: e });
}

test('CLI: git://, ssh:// and scp-form template sources are refused before any fetch', () => {
  for (const src of ['git://example.invalid/tess-os.git', 'ssh://git@example.invalid/x.git',
    'git@example.invalid:x/tess-os.git']) {
    const r = cli([`--template-source=${src}`]);
    assert.notEqual(r.status, 0, src);
    assert.match(r.stderr, /not an allowed source.*https:\/\//s, src);
  }
});

test('CLI: a local folder only from TESS_TEMPLATE_SOURCE (no flag) is refused', () => {
  const r = cli([], { TESS_TEMPLATE_SOURCE: BUNDLED_TEMPLATE_DIR });
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /name it on the command line instead: --template-source/);
});
