#!/usr/bin/env python3
"""Memory-continuity heartbeat — entry point.

One pass per invocation (an external scheduler like launchd/cron/systemd
does the repetition, not an internal loop — see scripts/launchd/ for the
staged, NOT-loaded macOS example). Per open project card:

  1. Tier-1 evidence probe ($0, no LLM): latest commit + latest PR activity
     on the card's repo.
  2. If that evidence is newer than the card's recorded last_activity ->
     MOVING: mechanically refresh heartbeat.last_activity/activity_proof/
     facts_last_verified (and clear any existing stall — new evidence
     objectively contradicts "stalled", no judgment call needed).
  3. If not moving and elapsed since last_activity > the card's own
     stall_after:
       - not yet stalled -> NEW STALL EVENT -> Tier-2 classify (the one
         model call in the per-card path) -> write stall block, notify/
         escalate per the returned reason, queue resume if warranted.
       - already stalled -> pure-arithmetic repeat-escalation check
         (escalation.py, no LLM) against the 48h/24h-cooldown rule.
  4. Once/day (in the configured timezone, default UTC): the recompile —
     regenerate registry.md from every card, run the fuzzy
     unregistered-work scan via Tier-2 (only if configured — see
     daily_recompile.py), commit+push, send ONE notification digest.

★ OFF BY DEFAULT — two independent gates, both must be satisfied:
  1. Nothing schedules this script. It ships with its scheduler staged, not
     installed (scripts/launchd/README.md's one-command activation is an
     explicit, manual, operator-run step).
  2. Even if someone runs this script directly, `config.is_activated()`
     (heartbeat.config.json's `activated` field, default false) forces
     dry-run regardless of the `--dry-run` CLI flag — see `main()` below.
     This is a second gate specifically because this code now ships to
     every instance of this framework rather than living on one operator's
     own machine; the blast radius of an accidental invocation is larger
     here than in the reference implementation this was ported from, so it
     gets an extra, independent off switch.

--dry-run (or not-yet-activated): every probe still runs for real (that's
the $0 evidence-probe proof this needs), but no card is written to disk, no
`claude -p` is spawned (a documented stand-in classification is used
instead), no notification is actually sent, and no git commit/push happens.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from heartbeat import cards as cards_mod  # noqa: E402
from heartbeat import config as config_mod  # noqa: E402
from heartbeat import daily_recompile  # noqa: E402
from heartbeat import escalation  # noqa: E402
from heartbeat import notify  # noqa: E402
from heartbeat import probes  # noqa: E402
from heartbeat import state_store  # noqa: E402
from heartbeat import tier2_classify  # noqa: E402
from heartbeat.duration import humanize, parse_stall_after  # noqa: E402
from heartbeat.lock import single_instance  # noqa: E402

PROJECTS_DIR = REPO_ROOT / "memory" / "projects"
REGISTRY_PATH = REPO_ROOT / "memory" / "registry.md"


def log(msg: str, verbose_only: bool = False, verbose: bool = True) -> None:
    if verbose_only and not verbose:
        return
    # stderr, deliberately — stdout carries exactly one JSON summary object
    # per run so the output is scriptable/diffable, not a mix of progress
    # text and JSON.
    print(f"[heartbeat] {msg}", file=sys.stderr)


def process_card(path: Path, now: datetime, state: dict, dry_run: bool, cfg: config_mod.HeartbeatConfig, verbose: bool) -> dict:
    """Returns a structured result dict for the summary report."""
    result = {"slug": path.stem, "path": str(path), "action": "no-op", "notes": []}
    try:
        card = cards_mod.read_card(path)
    except cards_mod.CardError as exc:
        result["action"] = "error"
        result["notes"].append(f"card parse failed: {exc}")
        return result
    result["slug"] = card.slug

    try:
        evidence = probes.probe_repo(card.repo)
    except probes.ProbeError as exc:
        result["action"] = "probe-error"
        result["notes"].append(str(exc))
        return result

    result["evidence_proof"] = evidence.proof
    stall_after, parsed_ok = parse_stall_after(card.heartbeat.get("stall_after", ""))
    if not parsed_ok:
        result["notes"].append(
            f"WARNING: could not parse a duration out of stall_after "
            f"({card.heartbeat.get('stall_after')!r}) — using {humanize(stall_after)} fallback"
        )

    recorded_last = card.last_activity
    evidence_latest = evidence.latest_ts

    # Two SEPARATE questions, deliberately not conflated:
    #   (a) refresh — did fresh evidence appear since the card was last checked?
    #       This is a pure mechanical field update, unconditional on the verdict below.
    #   (b) verdict — is the FRESHEST known activity timestamp (not "did it change")
    #       still within stall_after of *now*? A card can have fresh evidence AND
    #       still be stalled (e.g. an open PR nudged a week ago, itself now past
    #       the threshold) — "something changed since we last looked" is not the
    #       same claim as "this project is healthy right now".
    refreshed = bool(evidence_latest and (recorded_last is None or evidence_latest > recorded_last))
    effective_last_activity = evidence_latest if refreshed else recorded_last

    if refreshed:
        result["notes"].append(
            f"REFRESH: fresh evidence ({evidence_latest.isoformat().replace('+00:00','Z')}) newer than "
            f"recorded last_activity ({recorded_last.isoformat().replace('+00:00','Z') if recorded_last else 'none'})"
        )

    if effective_last_activity is None:
        result["action"] = "no-evidence-and-no-baseline"
        result["notes"].append("card has no last_activity and probe returned nothing — cannot classify")
        return result

    elapsed = now - effective_last_activity
    is_within_window = elapsed <= stall_after

    mechanical_updates = {}
    if refreshed:
        mechanical_updates["heartbeat.last_activity"] = evidence_latest.isoformat().replace("+00:00", "Z")
        mechanical_updates["heartbeat.activity_proof"] = evidence.proof
    # Bump facts_last_verified whenever something material changed this run:
    # a refresh, or the stall verdict flipping (clearing a previously-stalled card).
    verdict_is_flipping = is_within_window and card.is_stalled
    if refreshed or verdict_is_flipping:
        mechanical_updates["facts_last_verified"] = now.isoformat().replace("+00:00", "Z")

    if is_within_window:
        result["action"] = "cleared" if card.is_stalled else "healthy"
        result["notes"].append(f"elapsed {humanize(elapsed)} <= stall_after {humanize(stall_after)} (measured from freshest known evidence)")
        if card.is_stalled:
            mechanical_updates.update({"stall.stalled": False, "stall.reason": None, "stall.since": None})
            result["notes"].append("fresh evidence clears a previously-stalled card (mechanical, no Tier-2 needed)")
        if mechanical_updates:
            if not dry_run:
                new_text = cards_mod.apply_updates(card, mechanical_updates)
                path.write_text(new_text, encoding="utf-8")
            result["updates"] = mechanical_updates
        return result

    # Past stall_after, measured against the freshest evidence available —
    # true regardless of whether that evidence is new-to-us this run.
    result["notes"].append(
        f"elapsed {humanize(elapsed)} > stall_after {humanize(stall_after)} "
        "(measured from freshest known evidence)"
    )
    # The objective threshold-crossing moment, not "now we happened to notice" —
    # recomputed every run so a small dribble of evidence (a comment, a nudge)
    # that still isn't enough to clear the stall correctly shifts "since" forward.
    since_ts = effective_last_activity + stall_after

    if not card.is_stalled:
        # NEW STALL EVENT — the one per-card place Tier-2 is invoked.
        result["action"] = "new-stall"
        card_text = path.read_text(encoding="utf-8")
        classification = tier2_classify.classify_stall(
            card_text=card_text,
            evidence_proof=evidence.proof,
            days_silent=elapsed.total_seconds() / 86400,
            existing_reason=card.stall_reason,
            dry_run=dry_run,
            cfg=cfg,
        )
        result["classification"] = {
            "reason": classification.reason,
            "rationale": classification.rationale,
            "mocked": classification.mocked,
        }
        updates = dict(mechanical_updates)
        updates.update({
            "stall.stalled": True,
            "stall.reason": classification.reason,
            "stall.since": since_ts.isoformat().replace("+00:00", "Z"),
            "facts_last_verified": now.isoformat().replace("+00:00", "Z"),
        })
        if not dry_run:
            new_text = cards_mod.apply_updates(card, updates)
            path.write_text(new_text, encoding="utf-8")
        result["updates"] = updates

        if classification.notify_message:
            send_res = notify.send(classification.notify_message, dry_run=dry_run, cfg=cfg)
            result["notify"] = repr(send_res)
            if not dry_run:
                state_store.record_alarm(state, card.slug, now)
        if classification.queue_resume:
            result["notes"].append("would queue resume recipe at top of registry.md on next recompile/write")
        return result

    # Already stalled — pure-arithmetic repeat-escalation check, no LLM.
    # Still apply any mechanical last_activity/proof refresh + a recomputed
    # `since` (a fresh-but-insufficient nudge shifts the floor forward).
    if mechanical_updates or since_ts != card.stall_since:
        refresh_updates = dict(mechanical_updates)
        refresh_updates["stall.since"] = since_ts.isoformat().replace("+00:00", "Z")
        refresh_updates.setdefault("facts_last_verified", now.isoformat().replace("+00:00", "Z"))
        if not dry_run:
            new_text = cards_mod.apply_updates(card, refresh_updates)
            path.write_text(new_text, encoding="utf-8")
        result["updates"] = refresh_updates

    decision = escalation.decide(
        slug=card.slug,
        title=card.title,
        reason=card.stall_reason,
        since=since_ts,
        last_alarmed=state_store.last_alarm_for(state, card.slug),
        now=now,
    )
    result["action"] = "repeat-stall"
    result["escalation_decision"] = {"should_notify": decision.should_notify, "message": decision.message}
    if decision.should_notify:
        send_res = notify.send(decision.message, dry_run=dry_run, cfg=cfg)
        result["notify"] = repr(send_res)
        if not dry_run:
            state_store.record_alarm(state, card.slug, now)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Tess OS memory-continuity heartbeat")
    parser.add_argument("--dry-run", action="store_true", help="read-only probes; no writes, no spawn, no send")
    parser.add_argument("--daily", action="store_true", help="force the daily recompile path this run")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    verbose = not args.quiet

    cfg = config_mod.load()
    activated = cfg.is_activated()
    dry_run = args.dry_run or not activated
    if not activated and not args.dry_run:
        log(
            "not activated (heartbeat.config.json 'activated' is false and "
            "TESS_MEMORY_HEARTBEAT_ACTIVATED is unset) — forcing --dry-run regardless of "
            "flags. See docs/memory-continuity.md to activate.",
            verbose=verbose,
        )

    with single_instance(cfg.resolved_state_dir()) as acquired:
        if not acquired:
            return 0

        now = datetime.now(timezone.utc)
        today_local = now.astimezone(cfg.resolved_tzinfo()).date()
        state = state_store.load(cfg.resolved_state_dir())

        card_paths = cards_mod.list_card_paths(PROJECTS_DIR)
        log(f"pass start {now.isoformat()} — {len(card_paths)} cards under {PROJECTS_DIR}", verbose=verbose)

        results = []
        for path in card_paths:
            r = process_card(path, now, state, dry_run, cfg, verbose)
            results.append(r)
            log(f"{r['slug']}: {r['action']}" + (f" — {r['notes'][0]}" if r["notes"] else ""), verbose=verbose)

        do_daily = args.daily or state_store.recompile_due_today(state, today_local)
        daily_result = None
        if do_daily:
            log("running daily recompile" + (" (forced via --daily)" if args.daily else " (due today)"), verbose=verbose)
            all_cards = [cards_mod.read_card(p) for p in card_paths]
            daily_result = daily_recompile.run(
                all_cards, now, dry_run,
                repo_root=REPO_ROOT, registry_path=REGISTRY_PATH, cfg=cfg,
            )
            if not dry_run:
                state_store.record_recompile(state, today_local)

        if not dry_run:
            state_store.save(state, cfg.resolved_state_dir())

        summary = {
            "dry_run": dry_run,
            "activated": activated,
            "now": now.isoformat(),
            "cards": results,
            "daily_recompile": daily_result,
        }
        import json
        print(json.dumps(summary, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
