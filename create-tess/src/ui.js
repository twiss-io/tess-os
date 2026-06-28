// ui.js — terminal capability detection + styled output helpers.
// Design doc §5.1: non-TTY or <80 cols → plain-line mode (no ASCII art, no
// box-drawing, spinners degrade to plain log lines).
import pc from 'picocolors';

export const term = {
  isTTY: Boolean(process.stdout.isTTY),
  cols: process.stdout.columns || 0,
};

// Plain mode when we can't draw, the terminal is narrow, or NO_COLOR-ish envs.
export const plain =
  !term.isTTY || term.cols < 80 || process.env.TESS_PLAIN === '1';

export const c = pc;

// Pick fancy vs plain art from a {fancy, plain} sigil object.
export function art(sigil) {
  return plain ? sigil.plain : sigil.fancy;
}

// Dim helper that no-ops sensibly in plain mode.
export function dim(s) {
  return plain ? s : pc.dim(s);
}

export function accent(s) {
  return plain ? s : pc.yellow(s);
}

export function bold(s) {
  return plain ? s : pc.bold(s);
}

// Print a block of lore/art with a blank line of breathing room.
export function block(text) {
  process.stdout.write('\n' + text.replace(/^\n/, '') + '\n');
}

// A framed reveal card. In plain mode it degrades to an indented list.
export function card(title, lines) {
  if (plain) {
    process.stdout.write(`\n${title}\n` + lines.map((l) => `  - ${l}`).join('\n') + '\n');
    return;
  }
  const width = Math.min(Math.max(title.length, ...lines.map((l) => l.length)) + 4, 70);
  const top = '╔' + '═'.repeat(width) + '╗';
  const bot = '╚' + '═'.repeat(width) + '╝';
  // Pad on raw length (no ANSI inside the box so alignment stays exact).
  const pad = (s) => '║ ' + s + ' '.repeat(Math.max(0, width - s.length - 1)) + '║';
  const out = [top, pad(title), pad(''), ...lines.map(pad), bot].join('\n');
  process.stdout.write('\n' + out + '\n');
}
