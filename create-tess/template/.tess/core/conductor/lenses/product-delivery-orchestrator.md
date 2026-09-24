# Lens: Product and Delivery (outcome lens)

> Lens, not an agent. The conductor loads this file into its own planning, or into a role's brief, when the task needs this expertise. It adds questions and a quality bar; it never adds permissions. This was the "Product and Delivery Orchestrator" agent; in the ten-role roster it is a planning lens the conductor applies. The long-form doctrine stays in `conductor/outcome-orchestrators/product-delivery-orchestrator.md`.

**Use when:** the mission's outcome is product quality, delivery reliability and product-market fit: the journey from product idea through validated direction, scoped build, delivery, release readiness and post-launch learning.

## Focus

Own the outcome, not the activity. Frame the mission around the result the operator needs, find the real bottleneck, and plan the smallest set of dispatches (roles plus lenses) that moves it. The conductor dispatches; this lens only shapes the plan.

## Questions and principles

- What problem, for whom, and how will we know it is solved?
- What is the smallest shippable slice that proves the direction?
- What must be true before release (tests, security, rollback)?
- Which dependencies or sequencing risks can collide?
- What will we measure after launch, and who reads it?

## Typical plan

- Roles: Morwenna (map) then Ada or Iris (build), Quinn (tests), Vega (release); lenses: elena, freya, josephine, petra, selene, violette.
- Verifier: Reid for the diff, Quinn for release readiness, Cyra for auth, data or protected paths.
- Load only the lenses the task needs. One role with the right lens beats three roles without one.

## Guardrails

- Never invent roles. Every dispatch is one of the nine roles in `conductor/roster.md`.
- Hard-floor items (credentials, money movement, destructive production data, client-external claims) go to the operator.
- If the mission belongs to another outcome lens, say which and why instead of stretching this one.
