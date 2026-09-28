// release-proof.js — hand the install the proof of the release it came from.
//
// The published package carries release-proof.json, built by publish-npm.yml
// from the signed tag the package was built from (scripts/build-release-proof.py).
// Copied to <install>/.tess/release-proof.json before the first commit, it
// lets the install's first push pass the review gate without a verdict,
// because every protected file is exactly that signed release (tessctl
// checks the signatures and every file hash itself; this file is never
// trusted as given). A source checkout or --template-source install has no
// proof: its first push then needs a verdict, as before.
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const BUNDLED_RELEASE_PROOF = fileURLToPath(new URL('../release-proof.json', import.meta.url));
export const INSTALLED_RELEASE_PROOF = join('.tess', 'release-proof.json');

// Returns true when a proof was written into targetDir.
export function installReleaseProof(targetDir, { bundled, source = BUNDLED_RELEASE_PROOF } = {}) {
  if (!bundled || !existsSync(source)) return false;
  mkdirSync(join(targetDir, '.tess'), { recursive: true });
  copyFileSync(source, join(targetDir, INSTALLED_RELEASE_PROOF));
  return true;
}
