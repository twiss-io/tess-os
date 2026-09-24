// verdict-exclusion.test.js — `reviews/verdicts/**` never enters a scaffold.
//
// Signed review verdicts (`tessctl verdict sign` writes the signature into the
// verdict file itself) are this repo's own governance records. If they were
// copied, every verdict commit would make the committed create-tess/template
// bundle stale and would ship the maintainer's verdicts to every adopter.
//
// Run: npm test   (or `node --test test/verdict-exclusion.test.js`)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isExcludedRel, EXCLUDE_DIR_PREFIXES } from '../src/ignore.js';

test('reviews/verdicts is a whole-subtree exclusion', () => {
  assert.equal(isExcludedRel('reviews/verdicts/x.cyra.verdict.md'), true);
  assert.equal(isExcludedRel('reviews/verdicts'), true);
  assert.equal(isExcludedRel('reviews/verdicts/nested/2026-09-24-x.cyra.verdict.md'), true);
  // Case-fold hardening applies like every other prefix.
  assert.equal(isExcludedRel('Reviews/Verdicts/x.cyra.verdict.md'), true);
  assert.ok(EXCLUDE_DIR_PREFIXES.includes('reviews/verdicts'));
});

test('the exclusion is scoped: siblings and look-alike prefixes still ship', () => {
  assert.equal(isExcludedRel('reviews/README.md'), false);
  assert.equal(isExcludedRel('reviews/verdicts-guide.md'), false);
  assert.equal(isExcludedRel('docs/reviews/verdicts.md'), false);
});
