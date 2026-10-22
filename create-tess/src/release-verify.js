// release-verify.js — v1.0 audit
// (create-tess/git-template-source/unauthenticated-template-executed-and-anchored).
//
// An explicit git --template-source used to be cloned and then RUN (tessctl
// bake / install-hooks / verify / anchor init) with no check that it was a
// signed Tess OS release. Now a git template is fetched only over https, only
// as a release tag (v1.2.3), and its signed tag is verified exactly the way
// `tessctl update` verifies one (_verify_release_tag / _release_ssh_reason in
// .tess/bin/tessctl), with the keys shipped INSIDE this package's bundled
// template — never keys from the fetched tree:
//   * gpg on PATH       -> the OpenPGP tag signature must verify, made by the
//                          pinned fingerprint (.tess/tess.lock
//                          framework.trusted_key_fingerprint), in a throwaway
//                          isolated GNUPGHOME;
//   * SSH key pinned and ssh-keygen on PATH -> the SSH release signature in the
//                          tag message must verify too (namespace
//                          "tess-release", principal "twiss-release"), over the
//                          manifest rebuilt from THIS tag name, commit and tree;
//   * neither           -> refused.
// Nothing from the fetched tree is checked out, and no template code runs,
// until both checks pass.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const RELEASE_TAG_RE = /^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const PGP_BEGIN = '\n-----BEGIN PGP SIGNATURE-----';
const SSH_MARKER = 'Tess-Release-SSH-Signature: tess-release-manifest/1';
const SSH_INDENT = '    ';
const SSH_SIGNER_RE =
  /^twiss-release[ \t]+namespaces="tess-release"[ \t]+ssh-ed25519[ \t]+([A-Za-z0-9+/]{68})(?:[ \t]+[^\n]*)?$/;
const ED25519_PREFIX = Buffer.from('0000000b7373682d6564323535313900000020', 'hex');

function which(cmd) {
  const r = spawnSync(cmd, ['--version'], { encoding: 'utf8', timeout: 30000 });
  if (!r.error) return true;
  // ssh-keygen has no --version; it exits non-zero but it RAN.
  return r.error.code !== 'ENOENT';
}

// The release keys shipped with this package: the bundled template's
// .tess/tess.lock pins, and its .tess/keys files. Throws a plain Error when
// any is missing (a damaged package).
export function loadReleaseTrust(templateDir) {
  const lockPath = join(templateDir, '.tess', 'tess.lock');
  const keyPath = join(templateDir, '.tess', 'keys', 'twiss-release-key.asc');
  const signersPath = join(templateDir, '.tess', 'keys', 'twiss-release-allowed-signers');
  if (!existsSync(lockPath) || !existsSync(keyPath)) {
    throw new Error(
      'this create-tess install is missing the Tess OS release keys, so it cannot check ' +
        'a template fetched from git. Reinstall create-tess, or run it without ' +
        '--template-source to use the template it ships with.',
    );
  }
  const lock = readFileSync(lockPath, 'utf8');
  const pgp = /^ {2}trusted_key_fingerprint:\s*'?([0-9A-F]{40})'?\s*$/m.exec(lock);
  const ssh = /^ {2}trusted_ssh_key_fingerprint:\s*'?(SHA256:[A-Za-z0-9+/]{43})'?\s*$/m.exec(lock);
  if (!pgp) throw new Error('the shipped tess.lock pins no release key; cannot check a git template.');
  return {
    pgpFpr: pgp[1],
    sshFpr: ssh ? ssh[1] : null,
    pgpKey: readFileSync(keyPath),
    sshSigners: existsSync(signersPath) ? readFileSync(signersPath, 'utf8') : null,
  };
}

function git(repoDir, args, input) {
  const r = spawnSync('git', ['-C', repoDir, ...args], { input, maxBuffer: 64 * 1024 * 1024 });
  return { ok: r.status === 0, out: r.stdout || Buffer.alloc(0), err: String(r.stderr || '') };
}

function headers(buf) {
  const text = buf.toString('utf8');
  const head = text.split('\n\n', 1)[0];
  const out = {};
  for (const line of head.split('\n')) {
    const sp = line.indexOf(' ');
    if (sp > 0 && !(line.slice(0, sp) in out)) out[line.slice(0, sp)] = line.slice(sp + 1);
  }
  return out;
}

function refuse(ref, why) {
  return new Error(
    `the git template ${ref} is not a signed Tess OS release (${why}). Nothing was ` +
      'installed and none of its code was run.',
  );
}

function verifyPgp(tagBuf, trust, ref) {
  const text = tagBuf.toString('latin1');
  const at = text.indexOf(PGP_BEGIN);
  if (at < 0 || text.indexOf(PGP_BEGIN, at + 1) >= 0) throw refuse(ref, 'no single OpenPGP signature');
  const home = mkdtempSync(join(tmpdir(), 'create-tess-gpg-'));
  try {
    chmodSync(home, 0o700);
    writeFileSync(join(home, 'payload'), tagBuf.subarray(0, at + 1));
    writeFileSync(join(home, 'sig.asc'), tagBuf.subarray(at + 1));
    const env = { ...process.env, GNUPGHOME: home };
    const imp = spawnSync('gpg', ['--homedir', home, '--batch', '--import'], {
      input: trust.pgpKey, env, timeout: 60000,
    });
    if (imp.status !== 0) throw refuse(ref, 'the shipped release key could not be read');
    const v = spawnSync(
      'gpg',
      ['--homedir', home, '--batch', '--status-fd', '1', '--verify',
        join(home, 'sig.asc'), join(home, 'payload')],
      { env, encoding: 'utf8', timeout: 60000 },
    );
    const status = String(v.stdout || '');
    if (/^\[GNUPG:\] (BADSIG|ERRSIG|EXPKEYSIG|REVKEYSIG|KEYEXPIRED|KEYREVOKED|EXPSIG)\b/m.test(status)) {
      throw refuse(ref, 'the OpenPGP signature is bad, expired or revoked');
    }
    const valid = /^\[GNUPG:\] VALIDSIG ([0-9A-F]{40}) .* ([0-9A-F]{40})$/m.exec(status);
    if (v.status !== 0 || !valid) throw refuse(ref, 'the OpenPGP signature does not verify');
    if (valid[1] !== trust.pgpFpr && valid[2] !== trust.pgpFpr) {
      throw refuse(ref, 'it is signed by a key that is not the Tess OS release key');
    }
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
}

function sshSignatureBlock(tagBuf) {
  const text = tagBuf.toString('utf8');
  const cut = text.indexOf(PGP_BEGIN);
  const payload = cut >= 0 ? text.slice(0, cut + 1) : text;
  const sep = payload.indexOf('\n\n');
  if (sep < 0) return null;
  const lines = payload.slice(sep + 2).split('\n');
  const mentions = lines.filter((l) => l.includes('Tess-Release-SSH-Signature')).length;
  if (mentions === 0) return null;
  const at = lines.indexOf(SSH_MARKER);
  if (mentions !== 1 || at < 0) throw new Error('malformed');
  const block = [];
  for (const l of lines.slice(at + 1)) {
    if (!l.startsWith(SSH_INDENT)) break;
    block.push(l.slice(SSH_INDENT.length));
  }
  if (block.length < 3 || block[0] !== '-----BEGIN SSH SIGNATURE-----' ||
      block[block.length - 1] !== '-----END SSH SIGNATURE-----') {
    throw new Error('malformed');
  }
  return block.join('\n') + '\n';
}

function verifySsh(tagBuf, commitId, treeId, tagName, trust, ref) {
  const entries = String(trust.sshSigners || '')
    .split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));
  const m = entries.length === 1 ? SSH_SIGNER_RE.exec(entries[0]) : null;
  const blob = m ? Buffer.from(m[1], 'base64') : null;
  if (!blob || blob.length !== 51 || !blob.subarray(0, 19).equals(ED25519_PREFIX)) {
    throw refuse(ref, 'the shipped SSH release key is missing or malformed');
  }
  const fp = 'SHA256:' + createHash('sha256').update(blob).digest('base64').replace(/=+$/, '');
  if (fp !== trust.sshFpr) throw refuse(ref, 'the shipped SSH release key is not the pinned one');
  let sig;
  try {
    sig = sshSignatureBlock(tagBuf);
  } catch {
    throw refuse(ref, 'its SSH release signature is malformed');
  }
  if (!sig) throw refuse(ref, 'it has no SSH release signature');
  const dir = mkdtempSync(join(tmpdir(), 'create-tess-sshsig-'));
  try {
    writeFileSync(join(dir, 'allowed_signers'),
      `twiss-release namespaces="tess-release" ssh-ed25519 ${m[1]}\n`);
    writeFileSync(join(dir, 'release.sig'), sig);
    const manifest =
      `tess-release-manifest/1\ntag ${tagName}\nobject ${commitId}\ntree ${treeId}\n`;
    const r = spawnSync('ssh-keygen', ['-Y', 'verify', '-f', join(dir, 'allowed_signers'),
      '-I', 'twiss-release', '-n', 'tess-release', '-s', join(dir, 'release.sig')],
    { input: manifest, encoding: 'utf8', timeout: 60000 });
    if (r.status !== 0 || !String(r.stdout || '').includes(fp)) {
      throw refuse(ref, 'its SSH release signature does not verify');
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// Verify refs/tags/<ref> in repoDir (already fetched, nothing checked out).
// Returns the commit id the tag signs. Throws a plain Error otherwise.
export function verifyReleaseTag(repoDir, ref, trust, { has = which } = {}) {
  const tag = git(repoDir, ['cat-file', 'tag', `refs/tags/${ref}`]);
  if (!tag.ok) throw refuse(ref, 'it is not an annotated tag');
  const h = headers(tag.out);
  if (h.tag !== ref) throw refuse(ref, `the tag object is named ${JSON.stringify(h.tag)}`);
  if (h.type !== 'commit' || !/^[0-9a-f]{40}([0-9a-f]{24})?$/.test(h.object || '')) {
    throw refuse(ref, 'the tag does not name a commit');
  }
  const commit = git(repoDir, ['cat-file', 'commit', h.object]);
  const tree = commit.ok ? headers(commit.out).tree : null;
  if (!tree || !/^[0-9a-f]{40}([0-9a-f]{24})?$/.test(tree)) throw refuse(ref, 'its commit is unreadable');
  const hasGpg = has('gpg');
  const hasSsh = Boolean(trust.sshFpr) && has('ssh-keygen');
  if (!hasGpg && !hasSsh) {
    throw new Error(
      'checking a Tess OS release needs gpg or ssh-keygen, and this computer has neither. ' +
        'Run create-tess without --template-source to use the template it ships with.',
    );
  }
  if (hasGpg) verifyPgp(tag.out, trust, ref);
  if (hasSsh) verifySsh(tag.out, h.object, tree, ref, trust, ref);
  return h.object;
}

// Fetch EXACTLY refs/tags/<ref> from `source` into stagingDir, verify it,
// then check out the signed commit. The caller has already checked `source`
// (https only). Throws a plain Error, leaving stagingDir empty, on failure.
export function fetchVerifiedRelease(source, stagingDir, ref, trust, opts = {}) {
  if (!ref || !RELEASE_TAG_RE.test(ref)) {
    throw new Error(
      `a git --template-source must name a signed Tess OS release tag with ` +
        `--template-ref (for example v1.0.0)${ref ? `; ${JSON.stringify(ref)} is not one` : ''}. ` +
        'Branches and commits cannot be checked, so they are not installed.',
    );
  }
  const clean = () => {
    rmSync(join(stagingDir, '.git'), { recursive: true, force: true });
  };
  let r = git(stagingDir, ['init', '-q']);
  if (!r.ok) throw new Error(`git init failed: ${r.err.trim()}`);
  r = git(stagingDir, ['fetch', '--depth=1', '--no-tags', '--', source,
    `+refs/tags/${ref}:refs/tags/${ref}`]);
  if (!r.ok) {
    clean();
    throw new Error(`could not fetch the release tag ${ref} from ${source}: ${r.err.trim()}`);
  }
  let commit;
  try {
    commit = verifyReleaseTag(stagingDir, ref, trust, opts);
  } catch (err) {
    clean();
    throw err;
  }
  r = git(stagingDir, ['-c', 'advice.detachedHead=false', '-c', 'core.hooksPath=/dev/null',
    'checkout', '-q', '--detach', commit]);
  const head = git(stagingDir, ['rev-parse', 'HEAD']);
  if (!r.ok || head.out.toString().trim() !== commit) {
    clean();
    throw new Error(`could not check out the verified release ${ref}: ${r.err.trim()}`);
  }
  return commit;
}
