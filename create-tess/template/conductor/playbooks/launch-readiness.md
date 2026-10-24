# Playbook: Launch Readiness

**Orchestrator:** Product and Delivery (Rollout Mode)
**Mode:** `/product-mode`
**Owner of the verdict:** Quinn (release readiness, [verification-routing.md](../verification-routing.md))
**Output:** a `launch-readiness.json` record with every item answered, and Quinn's release-readiness verdict citing each item's primary evidence

This is the release checklist Tess OS ships for the apps your agents build. It
exists because an app can pass every test and still cost its owner money or a
lawsuit in its first week. Each item below is a way that has happened to apps
built quickly with AI agents: a metered hosting or AI bill with no cap, a
function that calls itself all night, a database whose row-level security was
never on, bulk texts sent without consent, a site a keyboard or screen-reader
user cannot use, and a release nobody security-audited.

---

## When it runs

It is a **mandatory predecessor** of:

- the **first public deploy** of an app or site;
- any **client-facing web release**;
- any release that adds a new metered service, a new event-triggered function,
  a new data store reachable from the browser, or a new way to message people.

Internal tools with no public URL, no real user data and no outbound messages
may skip it, and the mission record says so.

---

## The items

Run `./tessctl launch init` once. It writes `launch-readiness.json` at the
project root with every item open. Each item is answered one of two ways:

- `"status": "done"` with `"evidence"` saying what was checked and how, and
  optional `"evidence_files"` (paths in the repository: a config file, a probe
  output, a scan report);
- `"status": "n/a"` with a `"reason"` saying why it does not apply.

An item is never deleted or left blank. Tess treats a missing item as open.

| Item id | What counts as an answer | Checked by | Primary evidence |
|---|---|---|---|
| `spend-limits` | Every metered service (hosting bandwidth, serverless invocations, database egress, AI API keys) has a hard cap or an automatic shutdown, or at least a billing alert, and the evidence says which. An alert alone does not stop a bill. Rate limits are set at the CDN or host. | Vega | The plan or budget setting, the cap value, the config file (`netlify.toml`, `vercel.json`, max instances) |
| `self-trigger-guards` | Every event-triggered function (storage, database, queue, webhook, cron) cannot re-trigger itself: it never writes to its own trigger source, or it checks a marker and stops. Instances or concurrency are capped. | Reid | The function code and its trigger configuration |
| `public-key-data-access` | Row-level security (or the platform's rules) is **proven with the public/anon key against staging, never production**: anonymous and cross-user reads of every exposed table and bucket return zero rows. An "enabled" flag alone is not proof. | Cyra | The probe script and its output |
| `messaging-consent` | Before any bulk SMS, email or call to people: a consent record exists for each recipient, and the sending code checks it. This is an engineering gate; the legal reading stays with the business owner. | Reid with the `aveline` lens | Where consent is stored, the check in the sending code |
| `accessibility` | An automated scan (axe, pa11y or Lighthouse) and a keyboard-only pass ran on the main pages: alt text, keyboard reach, visible focus, contrast. | Quinn (Iris supplies the rendered pages) | The scan report and the keyboard-pass notes |
| `security-audit` | The `security-audit` skill ran on this release (a full audit, or a scoped audit of the change since the last launch), `./tessctl audit validate <run-dir>` passed, and no confirmed critical or high finding is open. | Cyra | Run status, counts per severity, and the sha256 of `findings.json`. The run folder stays outside the repository |

---

## Sequence

1. **Put the app under the ship gate.** Replace the placeholder production
   rule in `core/policy/policy.yaml` with your real production and
   client-facing paths. `./tessctl doctor` warns until you do, and
   `./tessctl launch mark-launched` refuses. See
   [docs/LAUNCH_READINESS.md](../../docs/LAUNCH_READINESS.md).
2. **Open the record.** `./tessctl launch init`.
3. **Dispatch the checkers in parallel**, one brief per item, each with the
   primary artifacts (the config, the code, the staging URL), never a summary.
   The probe for `public-key-data-access` runs against staging only.
4. **Fill in the record** from what each checker reports. A checker that could
   not verify something says so; that item stays open.
5. **Quinn verifies.** Quinn reads the record and the evidence it names and
   drafts the release-readiness verdict. Quinn rejects "N/A" without a reason,
   evidence that only restates the item, and evidence files that do not show
   what the item asks.
6. **Mark it launched.** `./tessctl launch mark-launched` sets the status only
   when every item is answered and the production rule names real paths.
   Commit the record with the release.

---

## What Tess enforces and what it does not

- **Enforced:** once the record says `"launched"`, `./tessctl launch check`
  and `./tessctl doctor` fail and the ship gate (`tessctl gate pre-push` and
  `tessctl gate ci`) refuses every push of that commit while any item is open,
  malformed or missing, while an evidence file it names is absent, or while
  the production rule is still the placeholder. A record Tess cannot read is
  treated the same way, and so is a push that deletes a launched record (a
  project steps back by setting the status to `"preparing"`).
- **Advisory:** Tess cannot see your hosting dashboard, your staging database
  or your consent store. While the status is `"preparing"` the record only
  lists what is open. Whether the evidence is true is the verifiers' job, and
  the verdict is the operator's to accept.

---

## Common failure modes to avoid

- Treating a budget alert as a spend cap.
- Proving row-level security with the service key, or against production.
- "RLS enabled" with no policy behind it.
- Marking an item N/A because nobody checked it.
- Running the accessibility scan on one page only.
- Copying security-audit findings into the repository, a ticket or a chat.
