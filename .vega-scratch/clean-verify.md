# Verification: clean PR should scan GREEN under the scoped gitleaks fix

Throwaway artifact for verifying issue #96's fix. This branch is clean (no
secret-shaped content of its own) but is pushed to the shared repo AFTER
`test/vega-contaminant-fixture` (an AWS-key-shaped fixture on a sibling
branch) — the fetch-depth:0 checkout will fetch that branch's objects too.
This proves the scoped scan (origin/main..HEAD) ignores sibling-branch
objects and reports 0 leaks. Safe to delete after verification.
