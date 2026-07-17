"""Render a `SpecDocument` to the canonical `SPEC.md` markdown text.

Deliverable (1): "SPEC.md schema — ... versioned in git." The `SpecDocument`
dataclass (types.py) is the machine-checkable contract; THIS is the
human-readable projection of it that actually gets committed as
`SPEC.md` at a generated app's repo root. Rendering is a pure, deterministic
function of a `SpecDocument` — the same spec always renders to byte-identical
markdown, so a diff on `SPEC.md` in git is always a diff on real content,
never rendering noise.
"""

from __future__ import annotations

from .types import SpecDocument

DIRECTIVE = (
    "> **CODE IS GENERATED FROM THIS SPEC — never the reverse.** Edit this "
    "file first; do not treat generated code as the source of truth. See "
    "`CLAUDE.md`/`AGENTS.md` in this repo's root for the full rule."
)


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n" if body.strip() else f"## {title}\n\n_(not yet specified)_\n"


def _bullet_list(items) -> str:
    return "\n".join(f"- {item}" for item in items) if items else ""


def _render_what_it_does(spec: SpecDocument) -> str:
    parts = [spec.what_it_does.summary]
    if spec.what_it_does.goals:
        parts.append("**Goals:**\n" + _bullet_list(spec.what_it_does.goals))
    if spec.what_it_does.user_stories:
        parts.append("**User stories:**\n" + _bullet_list(spec.what_it_does.user_stories))
    return "\n\n".join(p for p in parts if p and p.strip())


def _render_how_it_looks(spec: SpecDocument) -> str:
    parts = [spec.how_it_looks.description]
    if spec.how_it_looks.key_screens:
        screens = "\n".join(f"- **{s.name}** — {s.description}" for s in spec.how_it_looks.key_screens)
        parts.append("**Key screens:**\n" + screens)
    if spec.how_it_looks.design_references:
        parts.append("**Design references:**\n" + _bullet_list(spec.how_it_looks.design_references))
    return "\n\n".join(p for p in parts if p and p.strip())


def _render_how_it_works(spec: SpecDocument) -> str:
    parts = [spec.how_it_works.description]
    if spec.how_it_works.key_flows:
        flows = []
        for flow in spec.how_it_works.key_flows:
            steps = "\n".join(f"  {i}. {s}" for i, s in enumerate(flow.steps, start=1))
            flows.append(f"- **{flow.name}**\n{steps}" if steps else f"- **{flow.name}**")
        parts.append("**Key flows:**\n" + "\n".join(flows))
    if spec.how_it_works.integrations:
        parts.append("**Integrations:**\n" + _bullet_list(spec.how_it_works.integrations))
    return "\n\n".join(p for p in parts if p and p.strip())


def _render_data_model(spec: SpecDocument) -> str:
    if not spec.data_model.entities:
        return ""
    blocks = []
    for entity in spec.data_model.entities:
        field_rows = "\n".join(f"| `{f.name}` | {f.type} | {f.description} |" for f in entity.fields)
        table = "| Field | Type | Description |\n|---|---|---|\n" + field_rows if entity.fields else "_(no fields specified)_"
        rel = ("\n\n**Relationships:** " + "; ".join(entity.relationships)) if entity.relationships else ""
        blocks.append(f"### {entity.name}\n\n{table}{rel}")
    return "\n\n".join(blocks)


def _render_open_questions(spec: SpecDocument) -> str:
    if not spec.open_questions:
        return "_(none harvested — nothing ambiguous was found in the intake input)_"
    header = "| ID | Question | Category | Blocking | Status | Raised From |\n|---|---|---|---|---|---|"
    rows = [
        f"| `{q.id}` | {q.question} | {q.category} | {'yes' if q.blocking else 'no'} | {q.status} | {q.raised_from} |"
        for q in spec.open_questions
    ]
    return "\n".join([header] + rows)


def render_markdown(spec: SpecDocument) -> str:
    """Return the full `SPEC.md` text for `spec`. Deterministic: same
    `SpecDocument` in, same markdown string out, every time."""
    lines = [
        f"# {spec.title}",
        "",
        f"> Spec ID: `{spec.spec_id}` · Version {spec.spec_version} · Status: `{spec.status}`",
        f"> Generated: {spec.provenance.generated_at} · Approved by {spec.provenance.approved_by} "
        f"at {spec.provenance.approved_at}",
        f"> Source: `{spec.provenance.source_type}` — \"{spec.provenance.input_excerpt}\"",
        DIRECTIVE,
        "",
        _section("What It Does", _render_what_it_does(spec)),
        _section("How It Looks", _render_how_it_looks(spec)),
        _section("How It Works", _render_how_it_works(spec)),
        _section("Data Model", _render_data_model(spec)),
        _section("Non-Goals", _bullet_list(spec.non_goals)),
        _section("Acceptance Criteria", _bullet_list(spec.acceptance_criteria)),
        "## Open Questions Ledger",
        "",
        _render_open_questions(spec),
        "",
        "## Provenance",
        "",
        f"- Plan ID: `{spec.provenance.plan_id}`",
        f"- Mission ID: `{spec.provenance.mission_id or '(none)'}`",
        f"- Routing decision ID: `{spec.provenance.routing_decision_id or '(none — not routed through intent-router)'}`",
        f"- Entry command: `{spec.provenance.entry_command or '(none)'}`",
        f"- Orchestrator: `{spec.provenance.orchestrator or '(none)'}`",
        "",
    ]
    return "\n".join(lines)
