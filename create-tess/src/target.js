// target.js — turn --target into the REAL directory create-tess writes, and
// record what existed before the run so a rollback removes only what the run
// created.
//
// Why: every check (clobberReason, the --force plan, the pre-run snapshot)
// and every write must look at the same directory. A --target that is itself
// a symlink used to be snapshotted as empty (the walk never follows a link)
// while promote() wrote through it, so a failed forced run "verified" an empty
// tree against an empty tree and printed "left clean" over the scaffold's
// leftovers. Following the link once, up front, removes that split.
import { existsSync, lstatSync, realpathSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

function lstatOrNull(p) {
  try {
    return lstatSync(p);
  } catch {
    return null;
  }
}

function danglingLink(p) {
  return new Error(
    `${p} is a symlink to a path that does not exist. Pass an existing directory, ` +
      'or a path that does not exist yet.',
  );
}

// Returns { dir, given, viaSymlink, existed, createdRoot }:
//   dir         the real path every check and write uses;
//   given       the absolute path the operator passed;
//   viaSymlink  --target itself was a symlink (the caller says so);
//   existed     the directory existed before the run;
//   createdRoot when it did not, the shallowest directory the run will create
//               (mkdir -p may create several levels); rollback removes it.
export function resolveTarget(raw) {
  const given = resolve(raw);
  const st = lstatOrNull(given);
  if (st && st.isSymbolicLink() && !existsSync(given)) throw danglingLink(given);
  if (existsSync(given)) {
    return {
      dir: realpathSync(given),
      given,
      viaSymlink: Boolean(st && st.isSymbolicLink()),
      existed: true,
      createdRoot: null,
    };
  }
  let top = given;
  while (!existsSync(dirname(top)) && dirname(top) !== top) {
    if (lstatOrNull(dirname(top))) throw danglingLink(dirname(top));
    top = dirname(top);
  }
  const parentReal = realpathSync(dirname(top));
  return {
    dir: join(parentReal, relative(dirname(top), given)),
    given,
    viaSymlink: false,
    existed: false,
    createdRoot: join(parentReal, relative(dirname(top), top)),
  };
}
