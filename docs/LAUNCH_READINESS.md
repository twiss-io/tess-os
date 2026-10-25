# Launch readiness

An app your agents build can pass every test and still cost you money or a
lawsuit in its first week. Tess OS 1.0.0 adds three things that help prevent
that:

1. a **launch-readiness checklist** (`tessctl launch`) that each project
   answers before it calls itself launched, and that the ship gate enforces
   once it does;
2. a **`doctor` warning** while the ship gate still reviews none of your app
   code (the production rule ships as a placeholder);
3. the bundled **`security-audit` skill** as a required step for
   security-tier changes, releases and launches.

The doctrine is in [conductor/playbooks/launch-readiness.md](../conductor/playbooks/launch-readiness.md)
and [conductor/verification-routing.md](../conductor/verification-routing.md).

---

## 1. The checklist

### The six items

| Item id | The failure it prevents | What counts as an answer | Checked by |
|---|---|---|---|
| `spend-limits` | A traffic spike, a scraper or a DDoS on a metered host or AI API runs up a five- or six-figure bill | Each metered service has a hard cap or an automatic shutdown, or at least a billing alert, and the evidence says which (an alert alone does not stop a bill). Rate limits are set at the CDN or host | Vega |
| `self-trigger-guards` | A function writes to the bucket, table or queue that triggers it and calls itself all night | Every event-triggered function never writes to its own trigger source, or checks a marker and stops; instances or concurrency are capped | Reid |
| `public-key-data-access` | Row-level security left off, so anyone holding the public key that ships in the JavaScript can read every user | Proven with the **public/anon key against staging, never production**: anonymous and cross-user reads of every exposed table and bucket return zero rows. An "enabled" flag alone is not proof | Cyra |
| `messaging-consent` | Bulk texts or emails to a list without consent; some laws set a fixed amount per message | A consent record exists for each recipient and the sending code checks it. The legal reading stays with the business owner | Reid with the `aveline` lens |
| `accessibility` | A site that a keyboard or screen-reader user cannot use | An automated scan (axe, pa11y or Lighthouse) and a keyboard-only pass on the main pages: alt text, keyboard reach, visible focus, contrast | Quinn |
| `security-audit` | A release nobody security-audited | The `security-audit` skill ran on this release, `tessctl audit validate <run-dir>` passed, and no confirmed critical or high finding is open | Cyra |

### Commands

```bash
./tessctl launch init           # writes launch-readiness.json, every item open
./tessctl launch check          # lists what is answered and what is open
./tessctl launch check --json   # the same, for scripts
./tessctl launch mark-launched  # sets "launched"; refused while anything is open
```

### The record

`launch-readiness.json` sits at the project root and is committed with the
code it describes:

```json
{
  "format": "tess-launch-readiness/1",
  "status": "preparing",
  "items": {
    "spend-limits": {
      "status": "done",
      "evidence": "Hosting plan has a hard bandwidth cap; AI key has a monthly hard limit; functions max 10 instances.",
      "evidence_files": ["netlify.toml"]
    },
    "messaging-consent": {
      "status": "n/a",
      "reason": "The app sends no SMS, email or calls; only password-reset email from the auth provider."
    }
  }
}
```

- `"status": "done"` needs `evidence` (at least 15 characters, saying what was
  checked and how; "yes", "done", "TODO" do not count). `evidence_files` is
  optional; each path must exist in the same tree, inside the project.
- `"status": "n/a"` needs a `reason` (at least 15 characters).
- An item missing from the record counts as open. Items are never skipped.
- An unknown item id, a wrong `format` or a `status` other than `preparing` or
  `launched` is an error.

### What is enforced

| Record status | `launch check` | `doctor` | Ship gate (`gate pre-push`, `gate ci`) |
|---|---|---|---|
| no record | prints a hint, exit 0 | nothing | nothing |
| `preparing` | lists open items, exit 0 | a warning | nothing |
| `launched`, every item answered, production rule set | OK, exit 0 | OK | passes this check |
| `launched` with an item open, invalid or missing, an evidence file absent, or the production rule still the placeholder | **FAIL, exit 1** | **FAIL, exit 1** | **refuses the push** (`LAUNCH_READINESS_INCOMPLETE`) |
| a record that cannot be read (bad JSON, unknown status, a symlink) | **FAIL, exit 1** | **FAIL, exit 1** | **refuses the push** |
| a push that deletes a record the previous commit had as `launched` | n/a | n/a | **refuses the push**; set `"status": "preparing"` instead |

The gate reads the record from each pushed commit, not from your working
folder, and refuses only when something changed in the push. In CI logs it
names the reason code only.

### What Tess cannot check

Tess cannot see your hosting dashboard, your staging database or your consent
store. The evidence is your word and your verifiers' word, plus the files it
names. That is why each item has a checker, and why Quinn's release-readiness
verdict must cite the evidence, not restate the item. For
`public-key-data-access`, Tess adds an advisory note when the item is N/A but
the tree contains `supabase/`, `firebase.json`, `firestore.rules`,
`storage.rules` or `database.rules.json`.

---

## 2. Put your app code under the ship gate

`core/policy/policy.yaml` decides which changed paths need a signed review
before a push. A new project ships with one production rule,
`example-prod-service-placeholder`, pointed at `__REPLACE_ME__/prod/**`, which
matches nothing. Until you change it, the ship gate reviews none of your app
code, `./tessctl doctor` prints:

```text
  WARNING     core/policy/policy.yaml: rule example-prod-service-placeholder still points at __REPLACE_ME__/..., so the ship gate reviews none of your app code. ...
```

and `./tessctl launch mark-launched` refuses.

**Easiest: at install.** `npm create tess` asks which folders hold your live
app or client-facing code (press Enter to skip), or take them as a flag:
`npm create tess my-os -- --prod-paths "src,api/**"`. A folder name covers
everything under it. The wizard writes them into this rule, the first push
still passes without a review, and the warning never appears.

**Updates keep them.** `./tessctl update` copies your list of paths into the
new release's version of this rule; the rest of the rule (who must review,
whether a review is required) comes from the signed release. It does this
only while the rule's `id` stays `example-prod-service-placeholder` and you
changed nothing in it but its `globs` (plain paths such as `src/**`, at most
20). If you changed anything else in the rule, the update shows the
difference and asks you to approve the release's version, and you set your
paths again afterwards.

To set it later, in **your own terminal** (agents cannot write this file):

1. Open `core/policy/policy.yaml` and put your production and client-facing
   paths in the rule's `globs`. Keep its `id`, so `./tessctl update` carries
   your paths into later releases. For example:

   ```yaml
       - id: example-prod-service-placeholder
         ...
         globs:
           - "src/**"
           - "app/**"
           - "api/**"
   ```

   If your app keeps data rules in a backend-as-a-service, add a rule that
   needs Cyra for them (the policy file carries a commented example):

   ```yaml
       - id: data-access-rules
         description: Row-level security and storage rules.
         globs:
           - "supabase/migrations/**"
           - "supabase/config.toml"
           - "firestore.rules"
           - "storage.rules"
         classification: [prod_touching]
         require_verdict: true
         allowed_verifiers: [Cyra]
   ```

2. Set the edit aside and approve it (the file is one of Tess's safety files):

   ```bash
   ./tessctl capture core/policy/policy.yaml
   ./tessctl approve core/policy/policy.yaml --rationale "name our production paths"
   ./tessctl doctor
   ```

3. Commit it. The push of a policy change itself needs your approval at your
   own terminal (`./tessctl gate approve`), like any change to Tess's safety
   files; see [When Tess stops a push](WHEN_TESS_STOPS_A_PUSH.md).

If the project has no app code at all (a documents-only folder), delete the
placeholder rule the same way instead; the warning goes away.

---

## 3. The security audit as a standard step

The `security-audit` skill (Cloudflare's open-source method, vendored at
`.tess/core/skills/security-audit/`, available to Claude Code and Codex) is
required for:

- any change to a security-tier or protected path: a scoped audit of the
  change;
- every release and every externally visible launch: a full audit for a
  first launch, a major or a minor release; at least a scoped audit of the
  change since the last release for a patch.

To run it, ask your assistant for a security audit of the project (full) or
of the change (scoped). Tess reads the skill's `TESS.md`, runs its six phases
with Cyra as hunter and a fresh Reid or Quinn as verifier, and writes the run
**outside the project**, in `~/security-audit-skill/<repo>/run-<N>`. Then:

```bash
./tessctl audit validate ~/security-audit-skill/<repo>/run-<N>
```

A release or launch is ready when the validators pass, `run_status` is
`complete` (or the reason it is not is accepted in writing), and no confirmed
critical or high finding is open. Record only the summary in
`launch-readiness.json` (`security-audit` item) and in the verdict: reviewed
commit, scope, counts, validator result, and the sha256 of `findings.json`.
Never copy finding details into the repository, an issue or a chat.
