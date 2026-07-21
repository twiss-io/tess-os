# DESIGN.md Integration Design
**Date:** 2026-04-09  
**Status:** Implemented  
**Reference:** VoltAgent/awesome-design-md

> **Implementation status 2026-04-09:** All files created and complete. ClientB DESIGN.md fully populated from Phase 1 staging documents. ClientC, ClientD, ClientA, and `_template/` all have 9-section scaffold files. Frontend-design-rule.md updated with DESIGN.md-first check and quality gate entry.

---

## Context

The Tess system manages multiple clients, each with a `branding/` folder containing logos, color guides, and style documents. The current frontend-design-rule tells agents to "check `branding/` before designing" — but there is no standardised, machine-readable design spec format. Agents must manually scan multiple files to piece together a client's visual system.

The awesome-design-md project (VoltAgent/awesome-design-md) establishes a plain-markdown design spec standard — a `DESIGN.md` file with 9 structured sections — that AI agents can read and immediately apply when building UIs. This integration adopts that standard across all Tess clients.

**Outcome:** Every client gets a `DESIGN.md` as the authoritative AI-readable design spec. Agents check it first. Branding work automatically flows into it via a sync workflow.

---

## DESIGN.md Location and Format

### Location

Each client gets a `DESIGN.md` at the root of their `branding/` folder:

```
clients/<client>/branding/DESIGN.md
```

Not inside `current/` or `staging/` — it sits at the branding root because it is a living spec, not a staged deliverable. Raw assets (logos, images, SVGs) continue to live in `branding/current/`.

### Format — 9-Section Standard

Following the awesome-design-md format exactly:

1. **Visual Theme & Atmosphere** — Overall feel, design philosophy, brand character
2. **Color Palette & Roles** — All color tokens with semantic usage rules
3. **Typography Rules** — Font families, scale, weights, tracking, line-height
4. **Component Stylings** — Buttons, cards, inputs, nav, and other UI components
5. **Layout Principles** — Spacing system, grid, alignment rules
6. **Depth & Elevation** — Shadows, layers, layered background system
7. **Do's and Don'ts** — Design guardrails and anti-patterns
8. **Responsive Behavior** — Mobile-first adaptations, breakpoints
9. **Agent Prompt Guide** — Direct instructions for AI agents on how to apply this spec

---

## Client Launch State

| Client | DESIGN.md at Launch |
|---|---|
| ClientB | **Generated** — full spec from existing staging documents |
| ClientC | **Template** — empty 9-section scaffold |
| ClientD | **Template** — empty 9-section scaffold |
| ClientA | **Template** — empty 9-section scaffold |
| `_template` | **Template** — added to the client template folder |

### ClientB Source Documents

The ClientB DESIGN.md is generated from staging documents already produced in Phase 1:

| Section | Source |
|---|---|
| Visual Theme & Atmosphere | `lavinia-visual-direction-brief.md` |
| Color Palette & Roles | `cerise-identity-system.md` (CSS tokens included) |
| Typography Rules | `cerise-identity-system.md` + `lavinia-visual-direction-brief.md` |
| Component Stylings | `cerise-identity-system.md` |
| Layout Principles | `cerise-identity-system.md` (spacing system, 4px base) |
| Depth & Elevation | `lavinia-visual-direction-brief.md` (shadow system, grain texture) |
| Do's and Don'ts | `lavinia-visual-direction-brief.md` + brand strategy |
| Responsive Behavior | `lavinia-visual-direction-brief.md` (motion + responsive notes) |
| Agent Prompt Guide | Synthesised from all source docs |

---

## Branding Sync Workflow

### Purpose

When new branding work is done (new assets in staging, new color decisions, new components), those updates need to flow into DESIGN.md. The sync workflow handles this.

### Trigger

Run on demand via `/sync-design-spec [client]` or called by Tess after any branding session concludes.

### Process

1. **Scan** `branding/current/` and `branding/staging/` for files added or updated since the last sync (tracked by last-modified timestamps or a sync log)
2. **Read** those files and extract anything not yet represented in DESIGN.md (new color tokens, new component specs, new typography rules, new motion specs, etc.)
3. **Propose additions** as a readable diff shown to the operator for review — never make changes silently
4. **Append only** — the operator approves → additions are written to DESIGN.md; the operator declines → nothing changes
5. **Never remove or modify** existing DESIGN.md content without explicit user permission

### Hard Rule

The sync agent operates in append-only mode. Removal or modification of any existing content requires the operator to explicitly instruct it. This is enforced in the agent's system prompt, not just documented.

### Sync Log

A lightweight log is maintained at `branding/.sync-log.md` per client — records the last sync date, what was scanned, and what was added. This prevents re-proposing the same additions.

---

## Frontend-Design-Rule Update

### Current Rule

> "Always check the client's `branding/` folder before designing. It may contain logos, color guides, style guides, or images. If assets exist there, use them."

### Updated Behaviour

```
1. Check branding/DESIGN.md first
   → If it exists and is non-empty: use it as the authoritative design spec
   → Still load actual asset files (logos, SVGs) from branding/current/

2. If DESIGN.md is absent or empty: fall back to current behaviour
   (manually scan branding/ for color guides, style docs, etc.)
```

DESIGN.md is the fast path. It resolves ambiguity about which staging document takes precedence — the spec file is the single resolved answer.

### Quality Gate Addition

Add to the frontend-design-rule quality checklist:

```
- [ ] branding/DESIGN.md checked — if present and non-empty, used as authoritative spec
- [ ] Raw assets (logos, SVGs) loaded from branding/current/
```

---

## Files Modified

| File | Change |
|---|---|
| `clients/ClientB/branding/DESIGN.md` | Created — generated from staging docs |
| `clients/ClientC/branding/DESIGN.md` | Created — empty template |
| `clients/ClientD/branding/DESIGN.md` | Created — empty template |
| `clients/ClientA/branding/DESIGN.md` | Created — empty template |
| `clients/_template/branding/DESIGN.md` | Created — template for future clients |
| `~/.claude/rules/frontend-design-rule.md` | Updated — DESIGN.md check added |
| `clients/ClientB/branding/.sync-log.md` | Created — initial sync log |

---

## Verification

After implementation:

1. Open `clients/ClientB/branding/DESIGN.md` — confirm all 9 sections are populated with real ClientB values (Obsidian `#0E0C0A`, Burnished Gold `#C9A84C`, Cormorant Garamond, etc.)
2. Open any other client's `DESIGN.md` — confirm it has the 9-section scaffold with clear `[PLACEHOLDER]` markers
3. Read `frontend-design-rule.md` — confirm DESIGN.md check appears before the general branding scan
4. Confirm `_template/branding/DESIGN.md` exists so new clients inherit the format automatically
