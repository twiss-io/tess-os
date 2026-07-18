// keystone.js — drive the Python keystone (tessctl) in the scaffolded instance.
// The wizard never edits doctrine directly: it writes operator state into
// operator/profile.json (operator space — never_touch in the manifest), then
// shells the keystone, which bakes (design doc §0, §5.5).
import { writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { VIBES } from './content/vibes.js';
import { pathwayLabel } from './content/pathways.js';

function tessctlPy(targetDir) {
  return join(targetDir, '.tess', 'bin', 'tessctl');
}

// Run one tessctl subcommand; returns trimmed stdout. Throws with context on
// non-zero exit so the caller can surface the failing step.
export function tessctl(targetDir, argsArr, { capture = true } = {}) {
  const py = tessctlPy(targetDir);
  if (!existsSync(py)) {
    throw new Error(`keystone not found at ${py} — template did not scaffold correctly`);
  }
  const env = { ...process.env, TESS_ROOT: targetDir };
  try {
    const out = execFileSync('python3', [py, ...argsArr], {
      cwd: targetDir,
      env,
      encoding: 'utf8',
      stdio: capture ? ['ignore', 'pipe', 'pipe'] : 'inherit',
    });
    return (out || '').trim();
  } catch (err) {
    const detail = [err.stdout, err.stderr].filter(Boolean).join('\n').trim();
    throw new Error(`tessctl ${argsArr.join(' ')} failed:\n${detail || err.message}`);
  }
}

// Write operator/profile.json — single source of operator truth (design doc §5.5).
// vibe + starter_path are recorded for provenance even though the engine only
// reads operator_name / assistant_name / pathway; _load_operator_profile merges
// {**defaults, **data} so the extra keys survive every keystone re-render.
export function writeProfile(targetDir, choices) {
  const opDir = join(targetDir, 'operator');
  if (!existsSync(opDir)) mkdirSync(opDir, { recursive: true });
  const profile = {
    operator_name: choices.operator,
    assistant_name: choices.conductor,
    pathway: choices.pathway,
    vibe: choices.vibe,
    starter_path: choices.path,
    telegram_channel: choices.telegram || null,
    created: new Date().toISOString(),
    wizard_version: choices.wizardVersion || '1.0.0',
  };
  writeFileSync(
    join(opDir, 'profile.json'),
    JSON.stringify(profile, null, 2) + '\n',
    'utf8',
  );
  return profile;
}

// tess.lock's core_key for the ship-gate policy — the EXACT string tess.lock
// stores (forward-slash, POSIX-style, regardless of host OS: tess.lock is
// YAML text, not a filesystem path join). `tessctl lock --regen --only`
// matches this literally against core_key OR live_path (see
// `_lock_resolve_only_paths` in .tess/bin/tessctl) — must NOT be built with
// `path.join`, which would emit a backslash-joined string on Windows that
// would never match.
export const POLICY_LOCK_CORE_KEY = '.tess/core/policy/policy.yaml';

// Scoped re-pin: `resetScaffoldedPolicyKeys` (scaffold.js) intentionally
// rewrites `.tess/core/policy/policy.yaml`'s bytes post-copy (collapsing the
// source repo's registered verifier_keys/signoff_keys back to the empty
// default) — that invalidates the base_sha tess.lock inherited from the
// source. Re-pinning ONLY this one entry (never an unscoped `--regen`, which
// would bless ANY other unrelated core drift) keeps a freshly scaffolded
// project `tessctl doctor`-clean without silently blessing anything else.
// This mirrors the exact mechanism `tessctl verdict keygen` already uses for
// the inverse operation (registering a real key) — see its own
// `_lock_regen_core(root, only={core_key})` call in .tess/bin/tessctl.
// A no-op (still exits 0) if base_sha already matches — safe to call even
// when resetScaffoldedPolicyKeys reports nothing changed.
export function regenPolicyLock(targetDir) {
  return tessctl(targetDir, ['lock', '--regen', '--yes', '--only', POLICY_LOCK_CORE_KEY]);
}

// The keystone bake sequence (task spec). Each step is a real tessctl verb.
// rename only runs when the conductor differs from the default 'Tess'.
//
// L1 — the per-step CLIMAX COPY is owned by the chosen vibe (content/vibes.js
// `bakeSteps`, keyed to these 5 operations); bake() resolves the label from the
// vibe so the climax reads as a crafted ritual per world, not a generic
// installer log. Falls back to neutral labels if a vibe omits a step.
//
// Free-text names (operator, conductor) are passed AFTER `--` so a name can
// never be read by tessctl's argparse as an option (HIGH-2b defence in depth;
// the wizard already rejects leading-hyphen names at validation).
//
// Returns an array of { op, label, args } for progress reporting.
export function bake(targetDir, choices, onStep = () => {}) {
  const vibe = VIBES[choices.vibe] || VIBES.rpg;
  const labels = vibe.bakeSteps || {};
  const ctx = {
    operator: choices.operator,
    conductor: choices.conductor,
    operatorTerm: vibe.operatorTerm,
    squadNoun: vibe.squadNoun,
    pathwayLabel: pathwayLabel(choices.pathway),
  };
  const labelFor = (op, fallback) => {
    const s = labels[op];
    if (typeof s === 'function') return s(ctx);
    if (typeof s === 'string') return s;
    return fallback;
  };

  const steps = [];
  const run = (op, fallback, argsArr) => {
    const label = labelFor(op, fallback);
    onStep(label, 'start');
    tessctl(targetDir, argsArr);
    steps.push({ op, label, args: argsArr });
    onStep(label, 'done');
  };

  run('roster', 'Installing starter squad', ['roster', 'apply', '--', choices.path]);
  run('setOperator', 'Writing operator profile', ['set-operator', '--', choices.operator]);
  if (choices.conductor && choices.conductor !== 'Tess') {
    run('rename', 'Naming the conductor', ['rename', '--', choices.conductor]);
  }
  run('pathway', 'Setting the communication pathway', ['pathway', '--', choices.pathway]);
  run('render', 'Rendering doctrine from operator stubs', ['render']);
  return steps;
}

// ---------------------------------------------------------------------------
// Gate activation — `git init` + `tessctl gate install-hooks`.
//
// Without this, a freshly scaffolded instance has a fully rendered doctrine
// tree and a working tessctl, but ZERO enforcement live: no `.git`, so no
// pre-commit/pre-push hooks, and the CI workflow tessctl writes
// (.github/workflows/tess-gate.yml) is dormant until it lives inside a repo
// that actually pushes commits through GitHub Actions. The gate is the
// headline feature the README sells — the wizard has to turn it on, not just
// hand over the parts.
//
// Deliberately NOT wrapped into the bake() rollback contract in index.js: an
// instance that finished bake() + writeProfile() and passes doctor/verify is
// already a good, working Tess OS install. If `git init` or
// `gate install-hooks` fails (git missing, an odd permissions issue, already
// nested inside a foreign repo in some unexpected way), the operator still
// has that working install — activateGate() reports the failure so the
// caller can surface manual next-steps, rather than discarding a good
// scaffold over an activation step that isn't part of the instance's
// correctness contract.
// ---------------------------------------------------------------------------

// True when `targetDir` is already inside a git work tree. Uses
// `git rev-parse --is-inside-work-tree` rather than checking for a `.git`
// entry in targetDir alone, so a target nested inside a parent repo (e.g. an
// operator scaffolding into an existing monorepo) is correctly detected as
// "already git" and left untouched.
export function isInsideGitWorkTree(targetDir) {
  try {
    const out = execFileSync('git', ['rev-parse', '--is-inside-work-tree'], {
      cwd: targetDir,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return out.trim() === 'true';
  } catch {
    return false;
  }
}

function gitErrorMessage(err) {
  if (err && err.code === 'ENOENT') {
    return 'git is not installed (or not on PATH) — install git and run `git init` manually.';
  }
  const detail = [err.stdout, err.stderr].filter(Boolean).join('\n').trim();
  return detail || err.message;
}

// Best-effort: `git init` (skipped if already inside a git work tree, or if
// skipGitInit is set) then `tessctl gate install-hooks` (skipped if skipHooks
// is set). Never throws — failures are reported on the returned result so the
// caller can decide how to surface them (see index.js).
//
// Returns:
//   gitInit         'done' | 'already' | 'skipped' | 'failed' | null
//   alreadyGitRepo  boolean
//   hooksInstalled  true | false | 'skipped' | null (null = not attempted)
//   gitHooksLive    boolean — the git pre-commit/pre-push hooks are actually
//                   on disk (false if install-hooks ran but found no
//                   `.git/hooks/` to write into — see tessctl's own NOTE)
//   hooksOut        stdout from `tessctl gate install-hooks` (on success)
//   error           combined error detail, or null
export function activateGate(
  targetDir,
  { onStep = () => {}, skipGitInit = false, skipHooks = false } = {},
) {
  const result = {
    gitInit: null,
    alreadyGitRepo: false,
    hooksInstalled: null,
    gitHooksLive: false,
    hooksOut: '',
    error: null,
  };

  if (skipGitInit) {
    result.gitInit = 'skipped';
    result.alreadyGitRepo = isInsideGitWorkTree(targetDir);
  } else if (isInsideGitWorkTree(targetDir)) {
    result.alreadyGitRepo = true;
    result.gitInit = 'already';
  } else {
    try {
      onStep('Initialising git repository', 'start');
      execFileSync('git', ['init', '--quiet', '-b', 'main'], {
        cwd: targetDir,
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      result.gitInit = 'done';
      onStep('Initialising git repository', 'done');
    } catch (err) {
      result.gitInit = 'failed';
      result.error = gitErrorMessage(err);
    }
  }

  if (skipHooks) {
    result.hooksInstalled = 'skipped';
    return result;
  }
  // No `.git` to hook into (git init failed and this wasn't already a repo) —
  // don't run install-hooks and call it a success; it would only write the
  // (inert) CI workflow file and print a NOTE. Surface the git failure via
  // next-steps instead (index.js) rather than muddying it with a partial
  // hooks result.
  if (result.gitInit === 'failed') {
    result.hooksInstalled = null;
    return result;
  }
  try {
    onStep('Installing gate hooks (tessctl gate install-hooks)', 'start');
    result.hooksOut = tessctl(targetDir, ['gate', 'install-hooks']);
    result.hooksInstalled = true;
    result.gitHooksLive = /installed git (pre-commit|pre-push) hook/.test(result.hooksOut);
    onStep('Installing gate hooks (tessctl gate install-hooks)', 'done');
  } catch (err) {
    result.hooksInstalled = false;
    result.error = result.error ? `${result.error}\n${err.message}` : err.message;
  }

  return result;
}

// Post-bake integrity checks. Returns { doctor, verify } booleans.
export function check(targetDir, { doctor = true, verify = true } = {}) {
  const result = { doctor: null, verify: null };
  if (doctor) {
    // tessctl throws on non-zero exit, so reaching the assignment = exit 0 = pass.
    try {
      result.doctorOut = tessctl(targetDir, ['doctor']);
      result.doctor = true;
    } catch (err) {
      result.doctor = false;
      result.doctorOut = err.message;
    }
  }
  if (verify) {
    try {
      result.verifyOut = tessctl(targetDir, ['verify']);
      result.verify = true;
    } catch (err) {
      result.verify = false;
      result.verifyOut = err.message;
    }
  }
  return result;
}
