// version.js — this package's own version, read from its package.json (which
// every published tarball includes). User-facing messages that say "not
// supported in create-tess X" use it, so they always name the version that is
// actually running instead of a hard-coded release number.
import { readFileSync } from 'node:fs';

export const CREATE_TESS_VERSION = JSON.parse(
  readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
).version;
