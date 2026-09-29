// journey.js — the gamified @clack/prompts flow (design doc §2, §3, §5.2).
//
// Step order (reconciled — see README "Ordering note"):
//   S0 cold open → S1 VIBE → S2 OPERATOR → S3 STARTER_PATH → S4 CONDUCTOR
//   → S5 PATHWAY → S6 RECAP. Vibe is first so it reskins
//   every downstream step; path precedes conductor so the C3 name-collision
//   check has the real install set, and the squad reveal lands before naming.
import * as p from '@clack/prompts';
import { VIBES, VIBE_ORDER, VIBE_HONESTY, DEFAULT_VIBE } from './content/vibes.js';
import { SIGILS, NEUTRAL } from './content/sigils.js';
import { PATH_FRAMING, PATH_NOTES, PATHWAY_OPTIONS } from './content/squads.js';
import { PATHWAY_SET_LINE } from './content/pathways.js';
import { PATHS } from './args.js';
import { installSetForPath } from './roster.js';
import { validateName, checkConductorName } from './validate.js';
import { art, accent, dim, card } from './ui.js';
import { askWhoFor, MODE_OPTIONS } from './brain.js';

function bail(value) {
  if (p.isCancel(value)) {
    p.cancel('Cancelled — nothing was written. Your target is untouched.');
    process.exit(0);
  }
  return value;
}

function vibeOptions() {
  return VIBE_ORDER.filter((k) => k !== 'plain').map((k) => ({
    value: k,
    label: VIBES[k].label,
    hint: VIBES[k].selectHint,
  }));
}

function pathOptions(vibeKey) {
  return PATHS.map((path) => {
    const f = PATH_FRAMING[vibeKey][path];
    return { value: path, label: f.label, hint: f.hint };
  });
}

function revealSquad(vibe, set) {
  const title = `${PATH_FRAMING[vibe.key][set.path].label} — your ${vibe.squadNoun}`;
  const lines = [];
  for (const a of set.squadDisplay) lines.push(`${a.name} — ${a.role}`);
  for (const a of set.baseDisplay) lines.push(`${a.name} — ${a.role}  (always on)`);
  if (set.orchDisplay.length) {
    lines.push('');
    lines.push(`Orchestrator${set.orchDisplay.length > 1 ? 's' : ''}: ${set.orchDisplay.join(' · ')}`);
  }
  // Lysandra #1 — the framed reveal card() is the completed-game beat: the box is
  // the Guild path's structural signature, now shared by all three vibes (each
  // keeps card()'s built-in plain-mode fallback). No ANSI goes inside the frame,
  // so the box stays aligned.
  card(title, lines);
  // Eva's PATH_NOTES (honest expectation-setting) ride DIMMED beneath the frame —
  // kept out of the box so dim ANSI never breaks card()'s right-edge alignment.
  const notes = PATH_NOTES[set.path] || [];
  for (const n of notes) process.stdout.write(dim('  ' + n) + '\n');
}

function recap(vibe, c) {
  return [
    `You        ${c.operator}`,
    `World      ${vibe.label}`,
    `${vibe.squadNoun.padEnd(10)} ${PATH_FRAMING[vibe.key][c.path].label}`,
    `Assistant  ${c.conductor}  (${c.pathway})`,
    `For        ${MODE_OPTIONS.find((o) => o.value === c.mode).label}${c.preset ? ` (${c.preset})` : ''}`,
  ].join('\n');
}

// The operator's name: no default, so an empty answer asks again.
async function askOperator(message) {
  const raw = bail(
    await p.text({
      message,
      placeholder: 'Your name',
      validate: (val) => {
        const r = validateName(val, 'name');
        return r.ok ? undefined : r.error;
      },
    }),
  );
  return { name: validateName(raw).value, typed: String(raw).trim() };
}

// The assistant's name (Enter keeps Tess); refuses a team member's name.
async function askAssistant(message, operatorName, set) {
  for (;;) {
    const raw = bail(
      await p.text({
        message,
        placeholder: 'Tess',
        validate: (val) => {
          if (!val || !val.trim()) return undefined; // empty → default Tess
          const r = validateName(val, 'assistant name');
          return r.ok ? undefined : r.error;
        },
      }),
    );
    const typed = raw && raw.trim() ? String(raw).trim() : null;
    const name = typed ? validateName(raw).value : 'Tess';
    const chk = checkConductorName(name, operatorName, set.installedNameSet);
    if (chk.block) {
      p.log.error(chk.reason);
      continue;
    }
    chk.warnings.forEach((w) => p.log.warn(w));
    return { name, typed };
  }
}

// The default setup (v1.0 e2e review, S4): plain words, four questions, no
// theme, no "conductor", no lens lists. Same install as every other skin.
async function runPlainJourney(roster) {
  const vibe = VIBES.plain;
  p.intro(accent('Tess OS setup'));
  p.note(vibe.lore, 'Welcome');
  const op = await askOperator(vibe.namePrompt);
  p.log.success(vibe.nameConfirm(op.name));
  const path = 'founders'; // the same team on every path; --path changes it
  const set = installSetForPath(roster, path);
  const asst = await askAssistant(vibe.conductorPrompt, op.name, set);
  p.log.success(vibe.conductorConfirm(asst.name));
  const pathway = bail(
    await p.select({ message: vibe.pathwayPrompt(asst.name), options: PLAIN_PATHWAY_OPTIONS }),
  );
  const { mode, preset, said } = await askWhoFor(p, bail);
  const choices = {
    vibe: 'plain', operator: op.name, path, conductor: asst.name, pathway, set, mode, preset,
    said: { ...said, operator: op.typed, conductor: asst.typed },
  };
  p.note([
    `Your name       ${choices.operator}`,
    `Your assistant  ${choices.conductor}`,
    `Talks to you    ${PLAIN_PATHWAY_OPTIONS.find((o) => o.value === pathway).label}`,
    `For             ${MODE_OPTIONS.find((o) => o.value === mode).label}${preset ? ` (${preset})` : ''}`,
  ].join('\n'), 'Your choices');
  const go = bail(await p.confirm({ message: vibe.recapVerb, active: 'Yes', inactive: 'No, stop', initialValue: true }));
  if (!go) {
    p.cancel('Nothing was written. Run the same command again any time to start over.');
    process.exit(0);
  }
  return choices;
}

const PLAIN_PATHWAY_OPTIONS = [
  { value: 'chief-of-staff', label: 'Clear and to the point', hint: 'short updates, most important first' },
  { value: 'co-founder', label: 'Like a partner', hint: 'direct, says "we", pushes back' },
  { value: 'strategist', label: 'Challenge my thinking', hint: 'asks what outcome you want first' },
  { value: 'guide', label: 'Explain as we go', hint: 'patient, walks you through decisions' },
  { value: 'operator', label: 'Just the facts', hint: 'very short status lines' },
];

// `requested` is --vibe (validated by the caller). No --vibe: the plain setup.
// A themed skin is opt-in only: `--vibe rpg|command|studio`.
export async function runJourney(roster, { vibe: requested } = {}) {
  // S0 — cold open (neutral platform wordmark; vibe lore comes after select).
  process.stdout.write(art(NEUTRAL) + '\n');
  if ((requested || DEFAULT_VIBE) === 'plain') return runPlainJourney(roster);
  p.intro(accent('Tess OS — founding setup'));

  // S1 — VIBE (loops for the Command-vibe doctrine gate, the only branch).
  let vibe;
  let pick = requested;
  for (;;) {
    const v = pick || bail(
      await p.select({
        message: 'Every operator runs their world a different way. Choose how yours is framed.',
        options: vibeOptions(),
      }),
    );
    pick = null;
    vibe = VIBES[v];
    p.log.success(vibe.engaged);
    // Lysandra #5 — the honesty guarantee rides as a DIMMED follow-line on every
    // vibe, so it stays honest without crowding the cinematic engaged beat.
    p.log.message(dim(VIBE_HONESTY));
    process.stdout.write(art(SIGILS[vibe.key]) + '\n');
    p.note(vibe.lore, vibe.label);
    if (vibe.doctrineGate) {
      p.note(vibe.doctrineGate.body, vibe.doctrineGate.title);
      const ok = bail(
        await p.confirm({
          message: vibe.doctrineGate.confirm,
          active: 'Yes',
          inactive: vibe.doctrineGate.no,
          initialValue: true,
        }),
      );
      if (!ok) continue; // "No" → re-pick vibe (clean branch)
    }
    break;
  }

  // S2 — OPERATOR name.
  const op = await askOperator(vibe.namePrompt);
  const operatorName = op.name;
  p.log.success(vibe.nameConfirm(operatorName));

  // S3 — STARTER PATH (squad reveal lands here, before conductor naming).
  const path = bail(
    await p.select({ message: vibe.pathPrompt, options: pathOptions(vibe.key) }),
  );
  const set = installSetForPath(roster, path);
  revealSquad(vibe, set);

  // S4 — CONDUCTOR name (default Tess); C3 collision against the install set.
  const asst = await askAssistant(vibe.conductorPrompt, operatorName, set);
  const conductor = asst.name;
  p.log.success(vibe.conductorConfirm(conductor));

  // S5 — PATHWAY (persona).
  const pathway = bail(
    await p.select({ message: vibe.pathwayPrompt(conductor), options: PATHWAY_OPTIONS }),
  );
  p.log.success(PATHWAY_SET_LINE[pathway](conductor));

  // S5b — WHO IS THIS FOR (second-brain mode + optional preset, brain.js).
  const { mode, preset, said } = await askWhoFor(p, bail);

  // S6 — RECAP + the single write gate. Nothing has touched the target yet.
  const choices = {
    vibe: vibe.key, operator: operatorName, path, conductor, pathway, set, mode, preset,
    said: { ...said, operator: op.typed, conductor: asst.typed },
  };
  p.note(recap(vibe, choices), "Here's the world you've built");
  const go = bail(
    await p.confirm({ message: vibe.recapVerb, active: 'Yes', inactive: 'Change something', initialValue: true }),
  );
  if (!go) {
    p.cancel('No changes written. Re-run create-tess anytime to start over.');
    process.exit(0);
  }
  return choices;
}
