// journey.js — the gamified @clack/prompts flow (design doc §2, §3, §5.2).
//
// Step order (reconciled — see README "Ordering note"):
//   S0 cold open → S1 VIBE → S2 OPERATOR → S3 STARTER_PATH → S4 CONDUCTOR
//   → S5 PATHWAY → S6 TELEGRAM(opt) → S7 RECAP. Vibe is first so it reskins
//   every downstream step; path precedes conductor so the C3 name-collision
//   check has the real install set, and the squad reveal lands before naming.
import * as p from '@clack/prompts';
import { VIBES, VIBE_ORDER, VIBE_HONESTY } from './content/vibes.js';
import { SIGILS, NEUTRAL } from './content/sigils.js';
import { PATH_FRAMING, PATH_NOTES, PATHWAY_OPTIONS } from './content/squads.js';
import { PATHWAY_SET_LINE } from './content/pathways.js';
import { PATHS } from './args.js';
import { installSetForPath } from './roster.js';
import { validateName, checkConductorName } from './validate.js';
import { art, accent, dim, card } from './ui.js';

function bail(value) {
  if (p.isCancel(value)) {
    p.cancel('Cancelled — nothing was written. Your target is untouched.');
    process.exit(0);
  }
  return value;
}

function vibeOptions() {
  return VIBE_ORDER.map((k) => ({
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
    `${vibe.operatorTerm} ${c.operator}`,
    `World      ${vibe.label}`,
    `${vibe.squadNoun.padEnd(10)} ${PATH_FRAMING[vibe.key][c.path].label}`,
    `Conductor  ${c.conductor}  (${c.pathway})`,
    c.telegram ? `Telegram   ${c.telegram}` : 'Telegram   skipped',
  ].join('\n');
}

export async function runJourney(roster) {
  // S0 — cold open (neutral platform wordmark; vibe lore comes after select).
  process.stdout.write(art(NEUTRAL) + '\n');
  p.intro(accent('Tess OS — founding setup'));

  // S1 — VIBE (loops for the Command-vibe doctrine gate, the only branch).
  let vibe;
  for (;;) {
    const v = bail(
      await p.select({
        message: 'Every operator runs their world a different way. Choose how yours is framed.',
        options: vibeOptions(),
      }),
    );
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
  const operator = bail(
    await p.text({
      message: vibe.namePrompt,
      placeholder: 'Your name',
      validate: (val) => {
        const r = validateName(val, 'name');
        return r.ok ? undefined : r.error;
      },
    }),
  );
  const operatorName = validateName(operator).value;
  p.log.success(vibe.nameConfirm(operatorName));

  // S3 — STARTER PATH (squad reveal lands here, before conductor naming).
  const path = bail(
    await p.select({ message: vibe.pathPrompt, options: pathOptions(vibe.key) }),
  );
  const set = installSetForPath(roster, path);
  revealSquad(vibe, set);

  // S4 — CONDUCTOR name (default Tess); C3 collision against the install set.
  let conductor;
  for (;;) {
    const raw = bail(
      await p.text({
        message: vibe.conductorPrompt,
        placeholder: 'Tess',
        defaultValue: 'Tess',
        validate: (val) => {
          if (!val || !val.trim()) return undefined; // empty → default Tess
          const r = validateName(val, 'conductor name');
          return r.ok ? undefined : r.error;
        },
      }),
    );
    const name = raw && raw.trim() ? validateName(raw).value : 'Tess';
    const chk = checkConductorName(name, operatorName, set.installedNameSet);
    if (chk.block) {
      p.log.error(chk.reason);
      continue;
    }
    chk.warnings.forEach((w) => p.log.warn(w));
    conductor = name;
    break;
  }
  p.log.success(vibe.conductorConfirm(conductor));

  // S5 — PATHWAY (persona).
  const pathway = bail(
    await p.select({ message: vibe.pathwayPrompt(conductor), options: PATHWAY_OPTIONS }),
  );
  p.log.success(PATHWAY_SET_LINE[pathway](conductor));

  // S6 — TELEGRAM (optional; default skip).
  let telegram = null;
  const wantTg = bail(
    await p.confirm({ message: vibe.telegramPrompt, initialValue: false }),
  );
  if (wantTg) {
    const ch = bail(
      await p.text({ message: 'Telegram channel id', placeholder: '-100...' }),
    );
    telegram = ch && ch.trim() ? ch.trim() : null;
  } else {
    p.log.info(vibe.telegramSkip);
  }

  // S7 — RECAP + the single write gate. Nothing has touched the target yet.
  const choices = { vibe: vibe.key, operator: operatorName, path, conductor, pathway, telegram, set };
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
