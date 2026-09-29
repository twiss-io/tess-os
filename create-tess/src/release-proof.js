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

// Printed when the bundled template is used but this copy of the package has
// no proof (a local `npm pack` without a release, or a damaged download):
// the install still works, but its first push is judged without the proof.
export const MISSING_PROOF_WARNING =
  'Note: this copy of create-tess has no release proof, so the first push of your ' +
  'project will need a review before the Tess check on GitHub passes.\n';

// Returns true when a proof was written into targetDir. When the bundled
// template is in use but the proof is missing, says so in one plain line
// (Reid, v1.0 review) instead of returning false silently.
export function installReleaseProof(
  targetDir,
  { bundled, source = BUNDLED_RELEASE_PROOF, warn = (line) => process.stdout.write(line) } = {},
) {
  if (!bundled) return false;
  if (!existsSync(source)) {
    warn(MISSING_PROOF_WARNING);
    return false;
  }
  mkdirSync(join(targetDir, '.tess'), { recursive: true });
  copyFileSync(source, join(targetDir, INSTALLED_RELEASE_PROOF));
  return true;
}
