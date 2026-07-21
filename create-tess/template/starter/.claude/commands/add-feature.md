---
description: Add a capability (MongoDB, Docker, testing, etc.) to an existing project
scope: starter-kit
argument-hint: <feature> [--list | --force]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion
---

# Add Feature to Existing Project

Add capabilities (MongoDB, Docker, testing, etc.) to an existing starter-kit project after scaffolding. Idempotent — safely updates already-installed features to the latest version.

**Arguments:** $ARGUMENTS

---

## Feature Definitions

The authoritative table of features that can be added to projects. Both `/add-feature` and `/update-project` reference these definitions.

| Feature | Files (from $SOURCE) | Deps | DevDeps | Env Vars | Scripts | CLAUDE.md Rule |
|---------|---------------------|------|---------|----------|---------|----------------|
| `mongo` | `scripts/db-query.ts`, `scripts/queries/example-find-user.ts`, `scripts/queries/example-count-docs.ts` | `strictdb@^0.1.0`, `mongodb@^6.5.0` | `tsx@^4.7.0` | `STRICTDB_URI` | `db:query`, `db:query:list` | Rule 3 |
| `postgres` | `scripts/db-query.ts`, `scripts/queries/example-find-user.ts`, `scripts/queries/example-count-docs.ts` | `strictdb@^0.1.0`, `pg@^8.0.0` | `tsx@^4.7.0` | `STRICTDB_URI` | `db:query`, `db:query:list` | Rule 3 |
| `docker` | Generated from templates (Dockerfile, docker-compose.yml) | — | — | — | — | Rule 10 |
| `vitest` | `vitest.config.ts` | — | `vitest@^2.0.0` | — | `test:unit`, `test:unit:watch`, `test:coverage` | — |
| `playwright` | `playwright.config.ts` | — | `@playwright/test@^1.42.0` | — | `test:e2e`, `test:e2e:ui`, `test:e2e:headed`, `test:e2e:chromium`, `test:e2e:report`, `test:kill-ports` | Rule 4 |
| `content` | `scripts/build-content.ts`, `scripts/content.config.json` | — | — | — | `content:build`, `content:build:id`, `content:list` | — |

---

## Step 0 — Resolve Source (Starter Kit)

Find the starter kit source directory:

1. If CWD has BOTH `claude-mastery-project.conf` AND `.claude/commands/new-project.md` → use CWD as `$SOURCE`
2. Else read `~/.claude/starter-kit-source-path` → verify it still has both files
3. Else ask via AskUserQuestion: "Where is the starter kit cloned?" with a text input

Store as `$SOURCE`.

---

## Step 1 — Parse Arguments

Parse `$ARGUMENTS` for:

- `--list` → display the Feature Definitions table above and exit immediately
- `--force` → set `$FORCE=true` (skip confirmation prompts)
- Everything else → feature name(s), space-separated (e.g., `mongo vitest`)

**Validate feature names:** Each name must match one of the features in the table above. If unknown: "Unknown feature: `<name>`. Use `/add-feature --list` to see available features."

If no feature names and no `--list`: ask via AskUserQuestion:
"Which feature do you want to add?"
- **mongo** — StrictDB database driver, query system, connection management
- **postgres** — StrictDB database driver with parameterized queries, transaction support
- **vitest** — Unit/integration test framework with coverage
- **playwright** — E2E browser testing with multi-browser support

(Show up to 4 most common; user can type "Other" for docker, content, etc.)

---

## Step 2 — Select Target

1. Read `~/.claude/starter-kit-projects.json`
   - If file doesn't exist or empty → error: "No projects found. Use `/new-project` to create one first."

2. **Smart default:** If CWD is inside a registered project directory → offer it first

3. Filter to projects whose `path` directory still exists on disk

4. Display list with AskUserQuestion:
   - "Which project should receive the feature?"
   - Options: up to 4 most recent projects (by `createdAt`), each showing: `name — language/framework — path`
   - If more than 4: the 4th option should be "Other (type a path)"

5. Store selected path as `$TARGET`

### Validations (all must pass — stop with clear error if any fail)

1. `$TARGET` directory exists → if not: "Directory not found: $TARGET"
2. `$TARGET` is a git repo → run: `git -C "$TARGET" rev-parse --is-inside-work-tree 2>/dev/null`
   - If not a git repo: "This project must be a git repo."
3. `$TARGET` is NOT the starter kit itself (compare resolved paths of `$SOURCE` and `$TARGET`)
   - If same: "Cannot add features to the starter kit itself."
4. `$TARGET` is registered in `~/.claude/starter-kit-projects.json`
   - If not registered: "This project isn't in the registry. Use `/convert-project-to-starter-kit` first."

---

## Step 3 — Safety Commit

```bash
cd "$TARGET"
git status --porcelain
```

- **If uncommitted changes exist** (git status --porcelain has output):
  ```bash
  cd "$TARGET" && git add -A && git commit -m "chore: pre-feature snapshot (before /add-feature)"
  ```

- **If clean** (no uncommitted changes):
  ```bash
  cd "$TARGET" && git commit --allow-empty -m "chore: pre-feature marker (before /add-feature)"
  ```

Store the hash: `PRE_FEATURE_HASH=$(git -C "$TARGET" rev-parse HEAD)`

**STOP if git fails** (except "nothing to commit" which is fine — treat as clean).

---

## Step 4 — Read Manifest

Read `$TARGET/.claude/features.json`.

**If missing:** Create an empty manifest:

```json
{
  "schemaVersion": 1,
  "installedBy": "claude-code-mastery-starter-kit",
  "language": "unknown",
  "features": {}
}
```

Write it to `$TARGET/.claude/features.json`.

**If exists:** Parse it. For each requested feature, check if it's already installed:

- **Already installed, same files:** Ask via AskUserQuestion (unless `$FORCE`):
  "Feature `<name>` is already installed (since <installedAt>). Update to latest version?"
  - Yes, update files (Recommended)
  - No, skip this feature

- **Not installed:** Proceed to install

---

## Step 5 — Preview (unless --force)

For each feature to install/update, display:

```
=== Feature Preview: <name> ===

Files to copy:
  + scripts/db-query.ts
  + scripts/queries/example-find-user.ts
  + scripts/queries/example-count-docs.ts

Dependencies to install:
  strictdb@^0.1.0
  mongodb@^6.5.0
  tsx@^4.7.0 (dev)

Environment variables to add (.env.example):
  STRICTDB_URI=your_strictdb_connection_string_here

Scripts to add (package.json):
  db:query → tsx scripts/db-query.ts
  db:query:list → tsx scripts/db-query.ts --list

CLAUDE.md sections:
  Rule 3: Database Access — StrictDB (if missing)
```

Ask via AskUserQuestion:
"Proceed with installing <N> feature(s)?"
- **Yes, install** (Recommended)
- **No, cancel**

If "No, cancel" → stop: "Feature installation cancelled. No changes made."

---

## Step 6 — Execute

For each feature, in order:

### 6a. Create directories

```bash
mkdir -p "$TARGET/$(dirname <each-file>)"
```

### 6b. Copy files

For each file in the feature definition:
- Copy from `$SOURCE/<file>` → `$TARGET/<file>`
- If file already exists and this is an update → overwrite

### 6c. Install dependencies (Node.js projects only)

Detect package manager from target project:
- `pnpm-lock.yaml` exists → `pnpm`
- `bun.lockb` exists → `bun`
- Otherwise → `npm`

```bash
cd "$TARGET"
# Production deps
<pkg-manager> add <deps>
# Dev deps
<pkg-manager> add -D <devDeps>
```

Skip if no deps defined for the feature. Skip if deps already in package.json.

### 6d. Merge .env.example

For each env var in the feature definition:
1. Read `$TARGET/.env.example` (create if missing)
2. Check if key name (before `=`) already exists
3. If missing → append the line with placeholder value
4. Write back

**Env var placeholder values:**
- `STRICTDB_URI` → `your_strictdb_connection_string_here`

### 6e. Merge package.json scripts

For each script in the feature definition:
1. Read `$TARGET/package.json` as JSON
2. Check if script name already exists in `scripts`
3. If missing → add it
4. Write back (preserve formatting)

**Script values:**
- `db:query` → `tsx scripts/db-query.ts`
- `db:query:list` → `tsx scripts/db-query.ts --list`
- `test:unit` → `vitest run`
- `test:unit:watch` → `vitest`
- `test:coverage` → `vitest run --coverage`
- `test:e2e` → `pnpm test:kill-ports && playwright test`
- `test:e2e:ui` → `pnpm test:kill-ports && playwright test --ui`
- `test:e2e:headed` → `pnpm test:kill-ports && playwright test --headed`
- `test:e2e:chromium` → `pnpm test:kill-ports && playwright test --project=chromium`
- `test:e2e:report` → `playwright show-report`
- `test:kill-ports` → `lsof -ti:4000,4010,4020 | xargs kill -9 2>/dev/null || true`
- `content:build` → `tsx scripts/build-content.ts`
- `content:build:id` → `tsx scripts/build-content.ts --id`
- `content:list` → `tsx scripts/build-content.ts --list`

### 6f. Add CLAUDE.md sections (if missing)

Check if the relevant CLAUDE.md rule section exists by searching for the header text. If missing, append it.

**mongo → Rule 3 header check:** Search for `Database Access` or `StrictDB` in `$TARGET/CLAUDE.md`
If missing, append the full Rule 3 section from the starter kit's CLAUDE.md.

**postgres → Rule 3 header check:** Search for `Database Access` or `StrictDB` in `$TARGET/CLAUDE.md`
If missing, append the full Rule 3 section from the starter kit's CLAUDE.md.

**playwright → Rule 4 header check:** Search for `Testing — Explicit Success Criteria` in `$TARGET/CLAUDE.md`
If missing, append the full Rule 4 section.

### 6g. Special: Docker feature

Docker doesn't copy files from source — it generates them based on the target project:

1. Detect language from registry or `$TARGET/.claude/features.json`
2. Generate `Dockerfile` using the appropriate template from the starter kit's `/new-project` command:
   - Node.js → multi-stage with node:20-alpine
   - Go → multi-stage with golang:1.23-alpine → scratch
   - Python → multi-stage with python:3.12-slim
3. Generate `.dockerignore` if missing
4. Add docker-related scripts if applicable

---

## Step 7 — Update Manifest

For each installed/updated feature, write to `$TARGET/.claude/features.json`:

```json
{
  "schemaVersion": 1,
  "installedBy": "claude-code-mastery-starter-kit",
  "language": "<from-registry-or-detection>",
  "features": {
    "<feature-name>": {
      "version": "1.0.0",
      "installedAt": "<ISO-timestamp>",
      "updatedAt": "<ISO-timestamp-or-null>",
      "files": [
        "<list-of-files-copied>"
      ]
    }
  }
}
```

- New install: set `installedAt` to now, `updatedAt` to null
- Update: keep original `installedAt`, set `updatedAt` to now

---

## Step 8 — Commit + Summary

```bash
cd "$TARGET"
git add -A
git commit -m "feat: add <feature-name(s)> via /add-feature"
```

Store: `FEATURE_HASH=$(git -C "$TARGET" rev-parse HEAD)`

**If nothing to commit** (all files unchanged): skip the commit, note "Already up to date."

### Display summary

```
=== Feature Installation Complete ===

Target: $TARGET
Feature(s): <name(s)>

Files:        N added, N updated
Dependencies: N installed
Env vars:     N added to .env.example
Scripts:      N added to package.json
CLAUDE.md:    N sections added

Pre-feature commit:  $PRE_FEATURE_HASH
Feature commit:      $FEATURE_HASH

To undo: git revert HEAD
To review: git diff $PRE_FEATURE_HASH..HEAD

Manifest updated: .claude/features.json
```

---

## Edge Cases

1. **Feature already installed and up to date** — If all files are identical to source, report "Feature `<name>` is already up to date — no changes needed." and skip.

2. **No package.json** — If the target has no package.json (e.g., Go or Python project), skip dependency installation and script merging. Still copy files and update manifest.

3. **Multiple features at once** — Process each feature sequentially. One commit at the end with all features listed.

4. **Go/Python projects requesting mongo** — Copy the query system files but skip npm dependency installation. Note in summary: "Files copied but dependencies not installed (not a Node.js project). Install StrictDB and the MongoDB driver for your language manually."

5. **Source file missing** — If a file listed in the feature definition doesn't exist in `$SOURCE`, warn and skip that file. Don't fail the entire operation.
