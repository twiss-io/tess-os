# Architectural Decisions

> Record WHY you chose X over Y. Future-you (and future-Claude) will thank you.

---

## Decision Template

When adding a new decision, copy this template:

```markdown
## ADR-XXX: [Title]

**Date:** YYYY-MM-DD
**Status:** Accepted | Superseded by ADR-XXX | Deprecated

### Context
What is the issue or situation that motivated this decision?

### Decision
What is the change we're making?

### Alternatives Considered
| Option | Pros | Cons |
|--------|------|------|
| Option A | ... | ... |
| Option B | ... | ... |

### Consequences
What are the positive and negative results of this decision?
```

---

## ADR-001: TypeScript Over JavaScript

**Date:** (today)
**Status:** Accepted

### Context
AI-assisted development needs explicit type information to avoid guessing. JavaScript provides no type contracts, leading to runtime errors that are hard to trace.

### Decision
All new code MUST be TypeScript with strict mode. When editing existing JavaScript files, convert to TypeScript first.

### Alternatives Considered
| Option | Pros | Cons |
|--------|------|------|
| JavaScript + JSDoc | Less setup | AI still guesses, JSDoc can be wrong |
| TypeScript (strict) | Explicit contracts, better AI accuracy | Slightly more verbose |

### Consequences
- Claude can reason about types without guessing
- Refactoring is safer with compile-time checks
- New team members learn the codebase from type signatures

---

## ADR-002: StrictDB for All Database Access

**Date:** (today)
**Status:** Accepted

### Context
Without centralized database access, each file creates its own connection, leading to pool exhaustion. This starter kit originally shipped a custom database adapter that evolved into StrictDB — a standalone npm package and unified driver supporting MongoDB, PostgreSQL, MySQL, MSSQL, SQLite, and Elasticsearch through a single API.

### Decision
All database access uses StrictDB directly. Install `strictdb` + your database driver, create a single `StrictDB` instance at app startup, and share it across the application. NEVER import native database drivers (`mongodb`, `pg`, etc.) directly.

### Consequences
- Single connection pool prevents exhaustion
- One place to add logging, metrics, retries
- Easy to mock for testing
- One API for all backends — switching databases requires only changing STRICTDB_URI
- Built-in sanitization, guardrails, and AI-first discovery (describe, validate, explain)
- StrictDB-MCP server gives AI agents direct database access with all guardrails enforced
