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
