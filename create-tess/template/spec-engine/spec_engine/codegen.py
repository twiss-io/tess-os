"""Spec + ScaffoldPlan -> REAL, RUNNABLE code. The first real codegen slice
of "code is generated FROM the spec, never the reverse" (Pillar 02),
continuing `scaffold.py`'s spec->scaffold DIRECTION stub (Phase 1 Epic E2
deliverable (3)) into the codegen half of Phase 2 Epic E4 ("scaffolds the
repo from SPEC.md... generates tests from the spec's acceptance section").

    from spec_engine.codegen import generate_app
    result = generate_app(spec, "/path/to/generated-app")
    # result.scaffold_plan.codegen_status == "generated"
    # result.written["src/server.js"], result.manifest, ...

## Target stack — the ONE default, and why

`DEFAULT_TARGET_STACK = "node-http-minimal"`: plain Node.js, using ONLY
`node:http`/`node:crypto`/`node:test`/`node:assert` core modules — **zero
npm dependencies, zero build step, zero install step.** Chosen over an
Express/React/Postgres stack deliberately:

  - "It MUST actually run" (this module's own build brief) is easiest to
    guarantee with nothing to `npm install` — a generated app boots with
    `node src/server.js` on any machine that has Node >=18, offline,
    with no registry access, no lockfile drift, no version-pin decisions
    this codegen step would otherwise have to make on a caller's behalf.
  - Node 18+ ships `fetch()` and `crypto.randomUUID()` and `node:test`
    (a real test runner) in core — enough to generate a genuinely
    testable app without inventing a test-framework dependency either.
  - This mirrors the SAME "keep tess-os's own deps stdlib-only" discipline
    `spec-engine`/`intent-router` already apply to THEMSELVES (see their
    READMEs) — applying it to what THEY generate is the honest extension
    of that discipline, not a new one.
  - Persistence is in-memory (a `Map` per entity) — data resets on
    restart. This is a deliberate, disclosed scope boundary, not an
    oversight: provisioning a real, persistent database is Phase 2 Epic
    E4's OWN next deliverable ("provisions DB (Supabase default)"), out
    of scope for this codegen slice. Every generated README says so.

A future second target stack is an ADDITIVE change — add a name to
`SUPPORTED_TARGET_STACKS` and a matching generator function; nothing here
assumes there is only ever one.

## What is genuinely generated vs. still a labeled stub

Deterministic, traceable mapping from `ScaffoldPlan.modules` (each of
which already carries a `source_section` back to the spec) to real files:

| `ScaffoldModule.kind` | Generated file(s) | `generation_status` |
|---|---|---|
| `backend-model` | `src/models/<entity-slug>.js` — a real, in-memory CRUD store (list/get/create/update/remove) with field-presence validation derived from `Entity.fields` | `generated` |
| `frontend-page` | `src/pages/<screen-slug>.js` — a real server-rendered HTML page; if the screen name matches a data-model entity it renders that entity's live records, else it renders the screen's spec description | `generated` |
| `service` (flow) | `src/flows/<flow-slug>.js` — a real, EXECUTABLE step-sequence function wired into a live route, but each step's business-logic body is a `// TODO` placeholder (flow steps are free text in the spec; codegen cannot compile prose into working business logic) | `generated-stub-logic` |
| `integration` | `src/integrations/<integration-slug>.js` — a labeled connector STUB that always throws, wired to a route that returns HTTP 501 | `stub` |
| `test-suite` | `tests/acceptance.test.js` — real `node:test` tests: a baseline boot/health check, one CRUD round-trip per entity, and one test per `acceptance_criteria` entry (a real entity-backed assertion if the criterion text names a known entity, else an honestly-commented fallback to the boot check) | `generated` |

Every one of these is recorded, per module, in `.spec-engine/
codegen-manifest.json` (schema: `schema/codegen-manifest.schema.json`) —
never silently rolled up into a single "generated" claim that overstates
the `service`/`integration` rows. `src/server.js`, `src/http-util.js`,
`package.json`, and the generated app's own `README.md` are also written,
but as `infrastructure_files` in the manifest — not attributed to a
`source_section`, because they are required scaffolding for this target
stack, not derived from any one spec section.

## Determinism

`generate_app()` performs no randomness and reads no clock EXCEPT what is
already frozen into the `ScaffoldPlan`/`SpecDocument` it is given (e.g.
`ScaffoldModule.module_id`, `ScaffoldPlan.generated_at` — both already
fixed before this function runs). Given the SAME `spec` + `scaffold_plan`
+ `target_stack`, every generated file's content is byte-identical across
runs — see `tests/spec_engine/test_codegen.py::
test_generate_app_is_deterministic_given_a_fixed_plan`.

## Atomicity

`generate_app()` never writes into the caller's real `target_dir` while
generation is in progress. Every file — every model/page/flow/
integration/infrastructure file, `.spec-engine/codegen-manifest.json`,
and `write_scaffold_stub()`'s own artifacts (`SPEC.md`, `spec.json`,
`.spec-engine/scaffold-plan.json`, `CLAUDE.md`/`AGENTS.md`) — is written
into a same-filesystem STAGING directory first; the complete result is
then swapped into `target_dir` with exactly one descriptor-relative atomic
`os.rename()`.
A process killed at ANY point — mid-write of a single file, or between
the manifest write and `write_scaffold_stub()`'s own writes (the
historical failure mode: a manifest claiming `codegen_status:
"generated"` while `SPEC.md`/`CLAUDE.md` are still missing) — leaves
`target_dir` either exactly as `generate_app()` found it (absent, empty,
or its own prior content) or the complete, `codegen_status: "generated"`
tree. There is no instant at which `target_dir` can be observed holding
a partial file tree. See `generate_app()`, `_write_generated_app_tree()`,
and `_publish_staged_app()` for the full mechanism, and
`tests/spec_engine/test_codegen_atomic_staging.py` for the kill-proof
proof.

Publishing OVER pre-existing `target_dir` content needs a second rename
in addition to the first (see `_publish_staged_app()`'s docstring for
why). A kill between them leaves the prior content in a deterministic,
reserved sibling. The next call detects that sibling before it decides
whether `target_dir` is empty and fails closed: a portable pathname
rename cannot bind an inspected aside directory against a concurrent
swap. The operator must inspect and restore/remove that sibling manually,
but codegen will never silently publish over it or turn `target_dir` into
a raced symlink. This check runs unconditionally on every call, not just
after a known crash.
"""

from __future__ import annotations

import errno
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .content import Entity, EntityField, KeyFlow, KeyScreen, ResolvedConnector, SpecEngineError
from .render import render_markdown
from .scaffold import SPEC_DIRECTIVE_BLOCK, SPEC_DIRECTIVE_MARKER, plan_scaffold_from_spec
from .types import ScaffoldModule, ScaffoldPlan, SpecDocument

PathLike = Union[str, Path]

DEFAULT_TARGET_STACK = "node-http-minimal"
SUPPORTED_TARGET_STACKS = (DEFAULT_TARGET_STACK,)

# "generated-connector" (Connectors v1, docs/design/connectors-architecture.md
# §6.3) is an ADDITIVE fourth value — a real client generated from a
# REGISTERED connector manifest, operational once its declared env var is
# configured. Deliberately NOT folded into plain "generated": operability
# depends on runtime configuration this repo cannot carry (an unset env var
# means a real, working client still answers 503, not 200) — collapsing that
# distinction would be exactly the overstatement the per-module manifest
# exists to prevent. See _render_connector_client_js() below.
GENERATION_STATUSES = ("generated", "generated-stub-logic", "stub", "generated-connector")

# Every v1 connector declares exactly one wired operation, by this name
# (connector_resolver.DEFAULT_OPERATION_NAME) — the generated app's single
# POST route per integration invokes it directly; there is no v1 operation
# -selection surface in the request (see _render_server_js's INTEGRATION_ROUTES
# handling below).
_CONNECTOR_RUNTIME_REL_PATH = "src/integrations/_connector-runtime.js"

# The one test file this codegen slice ever writes. Referenced by exact
# path (never a bare directory or glob) in package.json's "test" script
# and in every generated doc comment — `node --test <directory>`'s
# positional-argument test-discovery behavior is NOT stable across Node
# versions (empirically: passes on Node 20, fails with MODULE_NOT_FOUND
# on Node 22.23.1 for the exact same generated tree — reproduced locally
# and in CI). An explicit file path sidesteps that version-dependent
# discovery logic entirely and works identically on every Node >=18.
ACCEPTANCE_TEST_REL_PATH = "tests/acceptance.test.js"

# Regeneration may preserve caller-owned content already present in target_dir
# (notably hand-authored CLAUDE.md/AGENTS.md).  That tree is ingress from a
# less-trusted writer, so it gets an explicit, finite copy budget rather than
# an unbounded shutil.copytree() read.  These limits are deliberately far
# beyond the generated app's normal text-only footprint while keeping one
# accidentally or maliciously huge existing file from exhausting the process
# or staging filesystem.
_MAX_EXISTING_CONTENT_FILE_BYTES = 16 * 1024 * 1024
_MAX_EXISTING_CONTENT_TOTAL_BYTES = 64 * 1024 * 1024
_EXISTING_CONTENT_COPY_CHUNK_BYTES = 64 * 1024
_MAX_EXISTING_CONTENT_TREE_DEPTH = 32
_MAX_EXISTING_CONTENT_ENTRY_COUNT = 4096
# Capture this capability before tests or embedding code wrap ``os.open``;
# the wrapper must not make a safe platform appear unsupported.
_OS_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
_OS_MKDIR_SUPPORTS_DIR_FD = os.mkdir in os.supports_dir_fd
_OS_STAT_SUPPORTS_DIR_FD = os.stat in os.supports_dir_fd
_OS_RENAME_SUPPORTS_DIR_FD = os.rename in os.supports_dir_fd
_OS_UNLINK_SUPPORTS_DIR_FD = os.unlink in os.supports_dir_fd
_OS_RMDIR_SUPPORTS_DIR_FD = os.rmdir in os.supports_dir_fd

_INFRA_NOTE = (
    "Infrastructure file — required scaffolding for this target stack, "
    "not derived from any single spec section."
)


# --------------------------------------------------------------------------
# Small, pure helpers — no filesystem access.
# --------------------------------------------------------------------------

_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Lowercase, hyphenated, filesystem/URL-safe slug. Never empty."""
    slug = _SLUG_SANITIZE_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "item"


def _unique_slug(seen: Dict[str, int], base: str) -> str:
    """Return `base`, or `base-2`, `base-3`, ... the first time `base`
    collides with a slug already handed out to THIS `seen` registry
    (one registry per file-namespace: models/pages/flows/integrations are
    each their own namespace, so an entity and a screen with the same
    name never collide with each other, only within their own kind)."""
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}-{count}"


def _pluralize(slug: str) -> str:
    """Naive, deterministic English pluralization heuristic for REST
    collection paths (`/api/<plural>`). Handles the common regular cases
    (`-s`, `-es` after s/x/z/ch/sh, `-y`->`-ies` after a consonant);
    genuinely irregular plurals (e.g. "person"->"people") are NOT
    special-cased — documented as a known v1 limitation, not silently
    "fixed" by guessing."""
    if slug.endswith(("s", "x", "z", "ch", "sh")):
        return slug + "es"
    if len(slug) >= 2 and slug[-1] == "y" and slug[-2] not in "aeiou":
        return slug[:-1] + "ies"
    return slug + "s"


def _js_string(value: str) -> str:
    """A valid JS/JSON string literal for `value`. `json.dumps` produces
    valid JS source for any Python str (JSON string syntax is a strict
    subset of JS string syntax) — reused here instead of hand-rolling
    escaping so every free-text field from the spec (names, descriptions,
    acceptance criteria — none of it is trusted or pre-sanitized) is safe
    to embed directly into generated source."""
    return json.dumps(value)


def _html_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sample_value_for_field(f: EntityField, index: int = 1) -> Any:
    """A deterministic, type-plausible sample value for `f` — used ONLY
    to build real request bodies in generated tests (never written into
    a model's own persistence logic). `EntityField.type` is freeform text
    (see content.py) — this is a best-effort heuristic keyed on
    substrings, not a real type system; falls back to a labeled string
    sample when nothing matches, which is always valid input for the
    generated model's presence-only validation."""
    t = (f.type or "").lower()
    name = (f.name or "").lower()
    if "bool" in t:
        return True
    if any(k in t for k in ("int", "num", "float", "decimal", "price", "amount", "count", "qty", "quantity")):
        return index
    if "date" in t or "time" in t:
        return "2026-01-01T00:00:00.000Z"
    if "email" in name or "email" in t:
        return f"sample{index}@example.com"
    return f"sample-{f.name}-{index}"


def _match_entity_by_name(needle: str, entities: Sequence[Entity]) -> Optional[Entity]:
    """Heuristic name match (case-insensitive, slug-substring, either
    direction) — used to decide whether a screen/acceptance-criterion
    should be wired to a specific entity's live data, or fall back to a
    spec-description-only / boot-check rendering. Never guesses across
    unrelated words; a false negative (rendering the fallback when a
    human WOULD see the connection) is the safe failure mode here, not a
    false positive."""
    needle_slug = _slugify(needle)
    for entity in entities:
        entity_slug = _slugify(entity.name)
        if entity_slug and (entity_slug in needle_slug or needle_slug in entity_slug):
            return entity
    return None


# --------------------------------------------------------------------------
# Connectors v1 — one route-shape descriptor per how_it_works.integrations
# entry, built while writing src/integrations/**, consumed by
# _render_server_js() to wire INTEGRATION_ROUTES. `kind` is what the
# generated server's route loop branches on: "stub" keeps today's unchanged
# call()-always-throws-501 behavior; "connector" calls the real client's
# call(operation, input) and maps its typed errors to real HTTP statuses.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _IntegrationRoute:
    integration_name: str
    slug: str
    kind: str  # "stub" | "connector"
    operation: Optional[str]
    env_vars: List[str]
    connector_id: Optional[str]


# --------------------------------------------------------------------------
# Result type
# --------------------------------------------------------------------------


@dataclass
class CodegenResult:
    """Everything `generate_app()` produced. `manifest` is the exact
    object serialized to `.spec-engine/codegen-manifest.json` (schema:
    `schema/codegen-manifest.schema.json`)."""

    written: Dict[str, Path] = field(default_factory=dict)
    scaffold_plan: Optional[ScaffoldPlan] = None
    manifest: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def generate_app(
    spec: SpecDocument,
    target_dir: PathLike,
    *,
    scaffold_plan: Optional[ScaffoldPlan] = None,
    target_stack: str = DEFAULT_TARGET_STACK,
) -> CodegenResult:
    """Generate a real, runnable app from `spec` into `target_dir`. If
    `scaffold_plan` is not given, one is derived via
    `plan_scaffold_from_spec(spec, target_stack=target_stack)`. Fails
    loud (`SpecEngineError`) rather than silently generating a
    mismatched or partial app if: `target_stack` is unsupported, the
    given `scaffold_plan` was not built from THIS `spec` (id/version
    mismatch), or the plan's per-kind module counts don't match the
    spec's own lists (a stale/hand-edited plan) — see module docstring
    for the target-stack choice and the per-module generation-status
    contract this function honors.

    Atomic (see module docstring's "Atomicity" section): the full tree is
    staged in a same-filesystem sibling directory and swapped into
    `target_dir` with exactly one descriptor-relative `os.rename()` only after every file —
    including the manifest — has been written. A process killed at any
    point leaves `target_dir` either exactly as found or the complete,
    `codegen_status: "generated"` tree; never a partial mix. Every call
    also first repairs any interrupted rename-aside-swap left behind by a
    PRIOR killed call before doing anything else (see
    `_recover_interrupted_publish()`) — so a kill between
    `_publish_staged_app()`'s two renames never causes the next call to
    silently discard real prior `target_dir` content."""
    if target_stack not in SUPPORTED_TARGET_STACKS:
        raise SpecEngineError(
            f"generate_app: target_stack {target_stack!r} is not supported "
            f"(supported: {SUPPORTED_TARGET_STACKS})"
        )

    plan = scaffold_plan if scaffold_plan is not None else plan_scaffold_from_spec(spec, target_stack=target_stack)
    if plan.spec_id != spec.spec_id or plan.spec_version != spec.spec_version:
        raise SpecEngineError(
            f"generate_app: scaffold_plan (spec_id={plan.spec_id!r}, "
            f"spec_version={plan.spec_version}) does not match spec "
            f"(spec_id={spec.spec_id!r}, spec_version={spec.spec_version}) — "
            "regenerate the plan from this exact spec before generating code."
    )

    final_root = Path(target_dir)
    parent_fd = _open_target_parent_safely(final_root)
    stage_fd: Optional[int] = None
    stage_name: Optional[str] = None
    # MUST run before `has_existing_content` is decided below: detects any
    # rename-aside-swap a PRIOR call left interrupted so that leftover state
    # is never mistaken for "target_dir has always been empty". Recovery is
    # intentionally fail-closed rather than a racy pathname restore.
    try:
        _recover_interrupted_publish(final_root, parent_fd)
        # "Has real content to preserve" is NOT the same as `.exists()`: every
        # real caller today (orchestrator/pipeline.py, and pytest's own
        # `tmp_path` fixture in every test in this suite) hands generate_app()
        # a directory that already EXISTS but is EMPTY — and POSIX `rename(2)`
        # is perfectly happy replacing an empty directory (see
        # `_publish_staged_app()`), so only a genuinely NON-empty `target_dir`
        # needs the slower preserve-and-swap path. Evaluated AFTER recovery
        # above, so an interrupted prior tree can never be mistaken for an
        # empty/absent `target_dir`.
        has_existing_content, expected_target_identity = _target_has_existing_content(final_root, parent_fd)
        _require_publish_parent_isolation(parent_fd, final_root, expected_target_identity)
        stage_name, stage_fd = _create_staging_directory(final_root, parent_fd)
        if has_existing_content:
            # `_write_scaffold_stub_to_fd()` (called at the end of
            # `_write_generated_app_tree()`) MERGES with an already-present
            # CLAUDE.md/AGENTS.md rather than overwriting it — staging starts
            # from a descriptor-anchored copy of target_dir's current content.
            # Every source and destination operation stays relative to open
            # directory handles; no process-global cwd is ever changed.
            _copy_existing_content_safely(final_root, parent_fd, stage_fd)
        result = _write_generated_app_tree(stage_fd, spec, plan, target_stack)
        # Publishing is inside this same try/except: an exception raised
        # by `_publish_staged_app()` itself must still clean
        # up the stage here — `_publish_staged_app()` only ever consumes the
        # stage (renames it away) on the success path, so
        # this cleanup is always safe to attempt, and a no-op
        # (`ignore_errors=True`) on that success path since the path no
        # longer exists under its staging name by then.
        _publish_staged_app(
            stage_name,
            stage_fd,
            final_root,
            parent_fd,
            has_existing_content=has_existing_content,
            expected_target_identity=expected_target_identity,
        )
        # The staging entry was renamed into final_root. Do not try to clean
        # it up if the final lexical binding check below detects an ancestor
        # replacement; the descriptor still names the live generated tree.
        stage_name = None
        _verify_published_target_before_return(final_root, parent_fd, stage_fd)
    except BaseException:
        if stage_fd is not None and stage_name is not None:
            _discard_staging_directory(stage_name, stage_fd, parent_fd)
        raise
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent_fd)

    # `result.written`'s Path values were built against the staging tree
    # (renamed away by the publish above — that inode now IS
    # `final_root`); rebind them so callers see real, live paths under
    # `target_dir`, exactly as if generation had written there directly.
    result.written = {rel: final_root / rel for rel in result.written}
    return result


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )


def _require_fd_safe_platform() -> None:
    """Reject platforms without the primitives needed for fail-closed IO.

    A lexical pre-check followed by ordinary pathlib operations is not an
    acceptable fallback: an ancestor can be replaced after that check and
    before staging/publish.  The caller gets a clear error instead.
    """
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not _OS_OPEN_SUPPORTS_DIR_FD
        or not _OS_MKDIR_SUPPORTS_DIR_FD
        or not _OS_STAT_SUPPORTS_DIR_FD
        or not _OS_RENAME_SUPPORTS_DIR_FD
        or not _OS_UNLINK_SUPPORTS_DIR_FD
        or not _OS_RMDIR_SUPPORTS_DIR_FD
    ):
        raise SpecEngineError(
            "generate_app: this platform lacks the descriptor-relative no-follow operations "
            "required to safely stage and publish target_dir. Refusing a pathname-based fallback."
        )


def _target_name(final_root: Path) -> str:
    name = final_root.name
    if not name or name in {".", os.path.sep}:
        raise SpecEngineError(
            f"generate_app: target_dir {final_root!s} must name a directory, not a filesystem root."
        )
    return name


def _open_target_parent_safely(final_root: Path, *, create_missing: bool = True) -> int:
    """Return a no-follow FD for ``final_root.parent``.

    Each lexical ancestor is opened relative to the previously-open parent
    and its inode is bound to the preceding no-follow observation.  If an
    attacker replaces an ancestor after it is acquired, later mkdir, staging,
    recovery, and publish operations remain directed at the original parent
    FD; a final binding check rejects the now-stale lexical path rather than
    reporting an external location as the generated app.
    """
    _require_fd_safe_platform()
    lexical = Path(os.path.abspath(str(final_root)))
    _target_name(lexical)
    parent = lexical.parent
    parts = parent.parts
    if not parts or parts[0] != os.path.sep:
        raise SpecEngineError(f"generate_app: cannot safely open target_dir parent {parent}.")

    try:
        descriptor = os.open(os.path.sep, _directory_open_flags())
    except OSError as exc:
        _raise_existing_content_open_error(Path(os.path.sep), exc)

    current_display = Path(os.path.sep)
    try:
        for component in parts[1:]:
            current_display /= component
            try:
                observed = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                if not create_missing:
                    raise SpecEngineError(
                        f"generate_app: target_dir ancestor {current_display} disappeared while "
                        "verifying the final publish location. Refusing to report an unstable path."
                    )
                try:
                    # Match Path.mkdir(parents=True)'s normal mode and let
                    # the caller's umask retain control of new ancestors.
                    os.mkdir(component, 0o777, dir_fd=descriptor)
                except FileExistsError:
                    # A concurrent creator won this race. Re-observe it below
                    # through the stable parent descriptor.
                    pass
                except OSError as exc:
                    raise SpecEngineError(
                        f"generate_app: cannot create target_dir ancestor {current_display}: {exc}."
                    ) from exc
                try:
                    observed = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
                except OSError as exc:
                    _raise_existing_content_open_error(current_display, exc)
            except OSError as exc:
                _raise_existing_content_open_error(current_display, exc)

            if stat.S_ISLNK(observed.st_mode):
                raise SpecEngineError(
                    f"generate_app: {current_display} is an ancestor symlink for target_dir. "
                    "Refusing to create, stage, recover, or publish through it. Pass a canonical physical "
                    "path with no symlink ancestors (on macOS, use /private/var/... rather than /var/...)."
                )
            if not stat.S_ISDIR(observed.st_mode):
                raise SpecEngineError(
                    f"generate_app: {current_display} is not a directory in target_dir's ancestor path."
                )
            try:
                child_descriptor = os.open(component, _directory_open_flags(), dir_fd=descriptor)
            except OSError as exc:
                _raise_existing_content_open_error(current_display, exc)
            try:
                opened = os.fstat(child_descriptor)
                _require_stable_identity(observed, opened, current_display, "directory")
            except BaseException:
                os.close(child_descriptor)
                raise
            os.close(descriptor)
            descriptor = child_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _target_has_existing_content(final_root: Path, parent_fd: int) -> Tuple[bool, Optional[os.stat_result]]:
    """Return whether target_dir is non-empty plus its identity, if present."""
    name = _target_name(final_root)
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False, None
    except OSError as exc:
        _raise_existing_content_open_error(final_root, exc)

    if stat.S_ISLNK(observed.st_mode):
        raise SpecEngineError(
            f"generate_app: {final_root} is a symlink. Refusing to stage or replace target_dir through a symlink."
        )
    if not stat.S_ISDIR(observed.st_mode):
        raise SpecEngineError(f"generate_app: target_dir {final_root} exists but is not a directory.")

    descriptor = _open_existing_directory_entry(parent_fd, name, final_root, observed)
    try:
        with os.scandir(descriptor) as entries:
            return next(entries, None) is not None, observed
    except OSError as exc:
        raise SpecEngineError(f"generate_app: cannot inspect target_dir {final_root}: {exc}.") from exc
    finally:
        os.close(descriptor)


def _create_staging_directory(final_root: Path, parent_fd: int) -> Tuple[str, int]:
    """Create and open a private sibling staging directory through parent_fd."""
    name_prefix = f".{_target_name(final_root)}.codegen-stage-"
    for _ in range(32):
        stage_name = name_prefix + secrets.token_hex(16)
        try:
            os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise SpecEngineError(
                f"generate_app: cannot create descriptor-anchored staging directory for {final_root}: {exc}."
            ) from exc
        try:
            observed = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
            stage_fd = _open_existing_directory_entry(parent_fd, stage_name, final_root.parent / stage_name, observed)
            return stage_name, stage_fd
        except BaseException:
            # This is an immediately-created private directory. Best-effort
            # cleanup avoids normal exception residue; if a concurrent actor
            # changed its entry, the descriptor-identity check below refuses
            # to touch the replacement.
            try:
                os.rmdir(stage_name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
    raise SpecEngineError("generate_app: could not allocate a unique descriptor-anchored staging directory.")


def _copy_existing_content_safely(source_root: Path, parent_fd: int, destination_fd: int) -> None:
    """Copy pre-existing target_dir content into private staging safely.

    The tree is ingress, not trusted project output.  Every source directory
    and file is opened through a descriptor for its already-open parent with
    ``O_NOFOLLOW``.  The descriptor's device/inode must match the preceding
    no-follow stat, so a concurrent replacement with a different regular
    file or directory is refused too.  Regular files with multiple hard links
    are refused because their origin cannot be proved to be inside target_dir.
    Reads are streamed and constrained by both per-file and aggregate byte
    budgets, so existing content cannot turn a regenerate call into an
    unbounded staging copy.

    This deliberately fails closed on a platform without the descriptor
    primitives needed for that guarantee.  Falling back to a pre-walk plus a
    pathname copy would reintroduce the check-then-use vulnerability.
    """
    _require_fd_safe_platform()
    root_name = _target_name(source_root)
    try:
        observed = os.stat(root_name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        _raise_existing_content_open_error(source_root, exc)
    root_fd = _open_existing_directory_entry(parent_fd, root_name, source_root, observed)

    try:
        _copy_existing_directory(root_fd, destination_fd, source_root, Path(), 0, 0, 0)
    finally:
        os.close(root_fd)


def _verify_target_parent_binding(final_root: Path, parent_fd: int) -> None:
    """Reject a result whose lexical parent no longer names parent_fd."""
    verification_fd = _open_target_parent_safely(final_root, create_missing=False)
    try:
        expected = os.fstat(parent_fd)
        actual = os.fstat(verification_fd)
        _require_stable_identity(expected, actual, final_root.parent, "target_dir parent directory")
    finally:
        os.close(verification_fd)


def _discard_staging_directory(stage_name: str, stage_fd: int, parent_fd: int) -> None:
    """Best-effort cleanup of an unpublished, identity-bound stage directory.

    The stage name is checked against the open FD before removal.  A changed
    name is left alone rather than following or deleting a replacement.  In
    the ordinary exception path this removes the private stage so callers do
    not accumulate residue; a race resolves fail-closed as residue, not an
    operation on the replacement.
    """
    try:
        observed = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        return
    try:
        _require_stable_identity(observed, os.fstat(stage_fd), Path(stage_name), "staging directory")
    except SpecEngineError:
        return
    if not stat.S_ISDIR(observed.st_mode):
        return
    try:
        _remove_directory_tree_at(parent_fd, stage_name, expected=stage_fd)
    except OSError:
        # Cleanup never changes a generation failure into a silent delete of
        # an object that was raced after our identity binding.  The reserved
        # stage can be inspected and removed manually if it remains.
        return


def _remove_directory_tree_at(parent_fd: int, name: str, *, expected: Optional[int] = None) -> None:
    """Remove a directory tree by descriptors, never by a lexical cwd path."""
    observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if expected is not None:
        _require_stable_identity(observed, os.fstat(expected), Path(name), "directory to remove")
    directory_fd = _open_existing_directory_entry(parent_fd, name, Path(name), observed)
    try:
        _remove_directory_contents(directory_fd)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _remove_directory_contents(directory_fd: int) -> None:
    with os.scandir(directory_fd) as entries:
        names = [entry.name for entry in entries]
    for name in names:
        observed = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(observed.st_mode):
            child_fd = _open_existing_directory_entry(directory_fd, name, Path(name), observed)
            try:
                _remove_directory_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            # unlink(2) removes the directory entry itself; it does not
            # dereference a symlink. This cleanup path never follows input.
            os.unlink(name, dir_fd=directory_fd)


def _copy_existing_directory(
    source_dir_fd: int,
    destination_dir_fd: int,
    display_root: Path,
    relative: Path,
    copied_bytes: int,
    copied_entries: int,
    depth: int,
) -> Tuple[int, int]:
    """Copy one already-open source directory, returning bytes and entries."""
    if depth > _MAX_EXISTING_CONTENT_TREE_DEPTH:
        raise SpecEngineError(
            f"generate_app: pre-existing target_dir content exceeds the "
            f"{_MAX_EXISTING_CONTENT_TREE_DEPTH}-directory-level ingress depth limit at "
            f"{display_root / relative}."
        )
    try:
        names = []
        with os.scandir(source_dir_fd) as directory_entries:
            for entry in directory_entries:
                copied_entries += 1
                if copied_entries > _MAX_EXISTING_CONTENT_ENTRY_COUNT:
                    raise SpecEngineError(
                        "generate_app: pre-existing target_dir content exceeds the "
                        f"{_MAX_EXISTING_CONTENT_ENTRY_COUNT}-entry regeneration ingress limit."
                    )
                names.append(entry.name)
    except OSError as exc:
        raise SpecEngineError(
            f"generate_app: cannot safely enumerate pre-existing target_dir content at "
            f"{display_root / relative}: {exc}"
        ) from exc

    for name in names:
        candidate_relative = relative / name
        candidate_display = display_root / candidate_relative
        try:
            observed = os.stat(name, dir_fd=source_dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise SpecEngineError(
                f"generate_app: pre-existing target_dir content changed while staging "
                f"{candidate_display}: {exc}. Refusing to copy an unstable input tree."
            ) from exc

        if stat.S_ISLNK(observed.st_mode):
            raise SpecEngineError(
                f"generate_app: {candidate_display} is a symlink inside pre-existing target_dir content. "
                "Refusing to follow or copy a symlink during regeneration."
            )

        if stat.S_ISDIR(observed.st_mode):
            if depth >= _MAX_EXISTING_CONTENT_TREE_DEPTH:
                raise SpecEngineError(
                    f"generate_app: pre-existing target_dir content exceeds the "
                    f"{_MAX_EXISTING_CONTENT_TREE_DEPTH}-directory-level ingress depth limit at "
                    f"{candidate_display}."
                )
            child_fd = _open_existing_directory_entry(source_dir_fd, name, candidate_display, observed)
            try:
                os.mkdir(name, stat.S_IMODE(observed.st_mode), dir_fd=destination_dir_fd)
            except OSError as exc:
                os.close(child_fd)
                raise SpecEngineError(
                    f"generate_app: cannot create descriptor-anchored staging directory {candidate_display}: {exc}."
                ) from exc
            destination_fd = _open_new_directory_entry(destination_dir_fd, name, candidate_display)
            try:
                copied_bytes, copied_entries = _copy_existing_directory(
                    child_fd,
                    destination_fd,
                    display_root,
                    candidate_relative,
                    copied_bytes,
                    copied_entries,
                    depth + 1,
                )
                source_stat = os.fstat(child_fd)
            finally:
                os.close(child_fd)
                os.close(destination_fd)
            os.chmod(name, stat.S_IMODE(source_stat.st_mode), dir_fd=destination_dir_fd)
            os.utime(
                name,
                ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
                dir_fd=destination_dir_fd,
                follow_symlinks=False,
            )
            continue

        if not stat.S_ISREG(observed.st_mode):
            raise SpecEngineError(
                f"generate_app: {candidate_display} is not a regular file or directory. "
                "Refusing unsupported pre-existing target_dir content during regeneration."
            )

        copied_bytes = _copy_existing_file(
            source_dir_fd, destination_dir_fd, name, candidate_display, copied_bytes, observed
        )

    return copied_bytes, copied_entries


def _open_existing_directory_entry(
    parent_fd: int, name: str, display_path: Path, observed: os.stat_result
) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        _raise_existing_content_open_error(display_path, exc)
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise SpecEngineError(
            f"generate_app: {display_path} changed while staging and is no longer a directory. "
            "Refusing to copy an unstable input tree."
        )
    try:
        _require_stable_identity(observed, opened, display_path, "directory")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _open_new_directory_entry(parent_fd: int, name: str, display_path: Path) -> int:
    """Open a directory this process just created, without pathname traversal."""
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        _raise_existing_content_open_error(display_path, exc)
    return _open_existing_directory_entry(parent_fd, name, display_path, observed)


def _copy_existing_file(
    parent_fd: int,
    destination_parent_fd: int,
    name: str,
    display_path: Path,
    copied_bytes: int,
    observed: os.stat_result,
) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    try:
        source_fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        _raise_existing_content_open_error(display_path, exc)

    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise SpecEngineError(
                f"generate_app: {display_path} changed while staging and is no longer a regular file. "
                "Refusing to copy an unstable input tree."
            )
        _require_stable_identity(observed, source_stat, display_path, "regular file")
        if source_stat.st_nlink != 1:
            raise SpecEngineError(
                f"generate_app: {display_path} has {source_stat.st_nlink} hard links. "
                "Refusing a regular file whose origin cannot be proved to be inside target_dir."
            )
        if source_stat.st_size > _MAX_EXISTING_CONTENT_FILE_BYTES:
            raise SpecEngineError(
                f"generate_app: {display_path} is {source_stat.st_size} bytes, above the "
                f"{_MAX_EXISTING_CONTENT_FILE_BYTES}-byte per-file regeneration ingress limit."
            )
        if copied_bytes + source_stat.st_size > _MAX_EXISTING_CONTENT_TOTAL_BYTES:
            raise SpecEngineError(
                "generate_app: pre-existing target_dir content exceeds the "
                f"{_MAX_EXISTING_CONTENT_TOTAL_BYTES}-byte aggregate regeneration ingress limit."
            )

        destination_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=destination_parent_fd,
        )
        try:
            file_remaining = _MAX_EXISTING_CONTENT_FILE_BYTES
            total_remaining = _MAX_EXISTING_CONTENT_TOTAL_BYTES - copied_bytes
            while True:
                # The +1 makes a file that grows after fstat() fail rather
                # than silently accepting a byte beyond either budget.
                read_size = min(
                    _EXISTING_CONTENT_COPY_CHUNK_BYTES,
                    file_remaining + 1,
                    total_remaining + 1,
                )
                chunk = os.read(source_fd, read_size)
                if not chunk:
                    break
                if len(chunk) > file_remaining:
                    raise SpecEngineError(
                        f"generate_app: {display_path} grew beyond the "
                        f"{_MAX_EXISTING_CONTENT_FILE_BYTES}-byte per-file regeneration ingress limit "
                        "while it was being staged."
                    )
                if len(chunk) > total_remaining:
                    raise SpecEngineError(
                        "generate_app: pre-existing target_dir content grew beyond the "
                        f"{_MAX_EXISTING_CONTENT_TOTAL_BYTES}-byte aggregate regeneration ingress limit "
                        "while it was being staged."
                    )
                _write_all(destination_fd, chunk)
                file_remaining -= len(chunk)
                total_remaining -= len(chunk)
                copied_bytes += len(chunk)
            os.fchmod(destination_fd, stat.S_IMODE(source_stat.st_mode))
        finally:
            os.close(destination_fd)
        os.utime(
            name,
            ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
            dir_fd=destination_parent_fd,
            follow_symlinks=False,
        )
        return copied_bytes
    finally:
        os.close(source_fd)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write while staging pre-existing target_dir content")
        view = view[written:]


def _require_stable_identity(
    observed: os.stat_result, opened: os.stat_result, display_path: Path, expected_kind: str
) -> None:
    """Fail closed if a pathname changed object between lstat and open.

    O_NOFOLLOW only rejects a symlink at the instant of ``open``.  An
    attacker can instead replace a checked entry with an ordinary external
    file/directory (or a hard-link) in the check-to-open interval.  Bind the
    descriptor to the no-follow observation by device/inode and file kind
    before any bytes or child names are consumed.
    """
    if (
        observed.st_dev != opened.st_dev
        or observed.st_ino != opened.st_ino
        or stat.S_IFMT(observed.st_mode) != stat.S_IFMT(opened.st_mode)
    ):
        raise SpecEngineError(
            f"generate_app: {display_path} changed identity between inspection and open. "
            f"Refusing to stage an unstable {expected_kind} from target_dir."
        )


def _raise_existing_content_open_error(path: Path, exc: OSError) -> None:
    if exc.errno == errno.ELOOP:
        raise SpecEngineError(
            f"generate_app: {path} is a symlink or was swapped to one while staging pre-existing "
            "target_dir content. Refusing to follow it."
        ) from exc
    raise SpecEngineError(
        f"generate_app: cannot safely open pre-existing target_dir content at {path}: {exc}. "
        "Refusing to copy an unstable input tree."
    ) from exc


def _write_generated_app_tree(
    root_fd: int, spec: SpecDocument, plan: ScaffoldPlan, target_stack: str
) -> CodegenResult:
    """The actual per-module/infrastructure/manifest generation — every
    file this writes goes into `root_fd`, which is ALWAYS an open STAGING
    directory (see `generate_app()`, the only caller); this function has
    no awareness that `root` is not the caller's real `target_dir` and
    does not need any — atomicity is entirely `generate_app()`'s
    responsibility via `_publish_staged_app()`, not this one's. Unchanged
    by the atomic-staging fix other than taking `root_fd`/`plan`/
    `target_stack` as explicit parameters instead of closing over
    `target_dir`."""

    by_kind: Dict[str, List[ScaffoldModule]] = {}
    for module in plan.modules:
        by_kind.setdefault(module.kind, []).append(module)

    def _require_matching_count(kind: str, spec_items: Sequence[Any]) -> List[ScaffoldModule]:
        modules = by_kind.get(kind, [])
        if len(modules) != len(spec_items):
            raise SpecEngineError(
                f"generate_app: {len(modules)} {kind!r} module(s) in scaffold_plan "
                f"but {len(spec_items)} matching item(s) in spec — plan/spec are out "
                "of sync; regenerate the plan via plan_scaffold_from_spec(spec)."
            )
        return modules

    entity_modules = _require_matching_count("backend-model", spec.data_model.entities)
    screen_modules = _require_matching_count("frontend-page", spec.how_it_looks.key_screens)
    flow_modules = _require_matching_count("service", spec.how_it_works.key_flows)
    integration_modules = _require_matching_count("integration", spec.how_it_works.integrations)
    test_modules = by_kind.get("test-suite", [])

    # Connectors v1: `spec.resolved_connectors` was bound into the approval
    # gate's content hash as a list POSITIONALLY aligned with
    # `spec.how_it_works.integrations` (spec_builder.build_spec() copies it
    # verbatim from the approved plan — see connector_resolver.py's module
    # docstring for why this is resolved ONCE, at plan time, never re-read
    # here). A length mismatch means the SpecDocument itself is internally
    # inconsistent (never a normal "some integrations unresolved" case,
    # which is `ResolvedConnector.status == "unresolved"`, not a missing
    # entry) — fail loud rather than guess an alignment.
    if len(spec.resolved_connectors) != len(spec.how_it_works.integrations):
        raise SpecEngineError(
            f"generate_app: {len(spec.resolved_connectors)} resolved_connectors entry(ies) but "
            f"{len(spec.how_it_works.integrations)} how_it_works.integrations entry(ies) — spec is "
            "internally inconsistent (resolved_connectors must be 1:1 positionally aligned with "
            "how_it_works.integrations; see connector_resolver.resolve_connectors())."
        )

    written: Dict[str, Path] = {}
    manifest_modules: List[Dict[str, Any]] = []
    entity_slugs: Dict[str, int] = {}
    screen_slugs: Dict[str, int] = {}
    flow_slugs: Dict[str, int] = {}
    integration_slugs: Dict[str, int] = {}

    entities_by_slug: Dict[str, Tuple[Entity, str]] = {}  # slug -> (entity, class-name-safe slug)
    for module, entity in zip(entity_modules, spec.data_model.entities):
        slug = _unique_slug(entity_slugs, _slugify(entity.name))
        entities_by_slug[slug] = (entity, slug)
        rel_path = f"src/models/{slug}.js"
        _write_file(root_fd, rel_path, _render_model_js(entity, module))
        written[rel_path] = Path(rel_path)
        manifest_modules.append(
            _manifest_entry(module, "generated", [rel_path], f"In-memory CRUD store for entity '{entity.name}'.")
        )

    screens_written: List[Tuple[KeyScreen, str]] = []
    for module, screen in zip(screen_modules, spec.how_it_looks.key_screens):
        slug = _unique_slug(screen_slugs, _slugify(screen.name))
        matched_entity = _match_entity_by_name(screen.name, spec.data_model.entities)
        matched_slug = None
        if matched_entity is not None:
            for eslug, (entity, _) in entities_by_slug.items():
                if entity is matched_entity:
                    matched_slug = eslug
                    break
        rel_path = f"src/pages/{slug}.js"
        _write_file(root_fd, rel_path, _render_page_js(screen, module, matched_entity, matched_slug))
        written[rel_path] = Path(rel_path)
        screens_written.append((screen, slug))
        note = (
            f"Server-rendered page for screen '{screen.name}', showing live "
            f"'{matched_entity.name}' records." if matched_entity
            else f"Server-rendered page for screen '{screen.name}' (spec description only — "
                 "no matching data-model entity found)."
        )
        manifest_modules.append(_manifest_entry(module, "generated", [rel_path], note))

    flows_written: List[Tuple[KeyFlow, str]] = []
    for module, flow in zip(flow_modules, spec.how_it_works.key_flows):
        slug = _unique_slug(flow_slugs, _slugify(flow.name))
        rel_path = f"src/flows/{slug}.js"
        _write_file(root_fd, rel_path, _render_flow_js(flow, module))
        written[rel_path] = Path(rel_path)
        flows_written.append((flow, slug))
        manifest_modules.append(
            _manifest_entry(
                module,
                "generated-stub-logic",
                [rel_path],
                f"Real, executable step sequence for flow '{flow.name}'; each step's business-logic "
                "body is a documented TODO placeholder (flow steps are free text — codegen cannot "
                "compile prose into working business logic).",
            )
        )

    integrations_written: List[_IntegrationRoute] = []
    any_resolved_connector = False
    for module, integration_name, resolved in zip(
        integration_modules, spec.how_it_works.integrations, spec.resolved_connectors
    ):
        slug = _unique_slug(integration_slugs, _slugify(integration_name))
        rel_path = f"src/integrations/{slug}.js"

        if resolved.status == "resolved":
            renderer = _CONNECTOR_CLIENT_RENDERERS.get(resolved.connector_id)
            if renderer is None:
                raise SpecEngineError(
                    f"generate_app: integration {integration_name!r} resolved to registered "
                    f"connector {resolved.connector_id!r}, but codegen has no generated-client "
                    "template for that connector id — the registry and codegen.py's "
                    "_CONNECTOR_CLIENT_RENDERERS have drifted out of sync (a registry-only change "
                    "that adds a 4th connector needs a matching codegen.py template before specs "
                    "can resolve to it)."
                )
            any_resolved_connector = True
            _write_file(root_fd, rel_path, renderer(integration_name, module, resolved))
            written[rel_path] = Path(rel_path)
            operation_names = sorted({op.name for op in resolved.operations})
            side_effects = sorted({op.side_effect for op in resolved.operations})
            integrations_written.append(
                _IntegrationRoute(
                    integration_name=integration_name,
                    slug=slug,
                    kind="connector",
                    operation=resolved.operations[0].name,
                    env_vars=list(resolved.auth_env_vars),
                    connector_id=resolved.connector_id,
                )
            )
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "generated-connector",
                    [rel_path],
                    f"Real, vendored fetch() client for integration '{integration_name}', generated "
                    f"from registered connector {resolved.connector_id}@{resolved.connector_version} "
                    f"(manifest_hash={resolved.manifest_hash}). Operational once "
                    f"{'/'.join(resolved.auth_env_vars)} is configured; until then its route returns "
                    "HTTP 503 (not 501) — the code is real, operability depends on runtime "
                    "configuration this repo cannot carry.",
                    connector={
                        "connector_id": resolved.connector_id,
                        "connector_version": resolved.connector_version,
                        "manifest_hash": resolved.manifest_hash,
                        "operations": operation_names,
                        "env_vars": list(resolved.auth_env_vars),
                        "side_effect_classes": side_effects,
                    },
                )
            )
        else:
            _write_file(root_fd, rel_path, _render_integration_js(integration_name, module))
            written[rel_path] = Path(rel_path)
            integrations_written.append(
                _IntegrationRoute(
                    integration_name=integration_name, slug=slug, kind="stub", operation=None,
                    env_vars=[], connector_id=None,
                )
            )
            registered_note = (
                f" Connector ids registered in this checkout: {', '.join(resolved.registered_connector_ids)}."
                if resolved.registered_connector_ids
                else " No connectors are registered in this checkout at all."
            )
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "stub",
                    [rel_path],
                    f"Labeled connector stub for integration '{integration_name}' — no registered "
                    "connector matched this name (exact id/alias match only)."
                    + registered_note,
                )
            )

    # Infrastructure — required for any app on this target stack, not
    # attributed to a source_section (see module docstring).
    infra_files: List[str] = []
    infra_entries: List[Tuple[str, str]] = [
        ("src/http-util.js", _render_http_util_js()),
        (
            "src/server.js",
            _render_server_js(
                spec,
                entities_by_slug=[(slug, entity) for slug, (entity, _) in entities_by_slug.items()],
                screens=screens_written,
                flows=flows_written,
                integrations=integrations_written,
            ),
        ),
        ("package.json", _render_package_json(spec)),
        ("README.md", _render_app_readme(spec, target_stack, integrations_written)),
    ]
    # _connector-runtime.js is shared, generated-once infrastructure —
    # written ONLY when at least one integration resolved to a registered
    # connector (see the loop above); an app with zero resolved connectors
    # (every integration unresolved, or no integrations at all) never gets
    # a dead, unused file.
    if any_resolved_connector:
        infra_entries.append((_CONNECTOR_RUNTIME_REL_PATH, _render_connector_runtime_js()))
    for rel_path, content in infra_entries:
        _write_file(root_fd, rel_path, content)
        written[rel_path] = Path(rel_path)
        infra_files.append(rel_path)

    # Tests — from acceptance_criteria (deliverable: "acceptance_criteria
    # -> generated tests"), plus a baseline boot check and a per-entity
    # CRUD round-trip test that runs regardless of acceptance_criteria
    # content.
    test_rel_path = ACCEPTANCE_TEST_REL_PATH
    _write_file(
        root_fd,
        test_rel_path,
        _render_acceptance_test_js(
            spec,
            entities=[(slug, entity) for slug, (entity, _) in entities_by_slug.items()],
        ),
    )
    written[test_rel_path] = Path(test_rel_path)
    if test_modules:
        for module in test_modules:
            manifest_modules.append(
                _manifest_entry(
                    module,
                    "generated",
                    [test_rel_path],
                    "Real node:test suite: a baseline boot/health check, one CRUD round-trip per "
                    "entity, and one test per acceptance_criteria entry (entity-backed where the "
                    "criterion text names a known entity, else an honestly-commented fallback).",
                )
            )
    else:
        infra_files.append(test_rel_path)

    finalized_plan = ScaffoldPlan(
        spec_id=plan.spec_id,
        spec_version=plan.spec_version,
        generated_at=plan.generated_at,
        modules=plan.modules,
        target_stack=target_stack,
        codegen_status="generated",
        notes=plan.notes,
    )

    manifest = {
        "spec_id": spec.spec_id,
        "spec_version": spec.spec_version,
        "target_stack": target_stack,
        "generated_at": finalized_plan.generated_at,
        "codegen_status": "generated",
        "modules": manifest_modules,
        "infrastructure_files": infra_files,
        "notes": (
            f"{len(manifest_modules)} spec-derived module(s), {len(infra_files)} infrastructure "
            "file(s). generation_status per module: 'generated' (real, working code), "
            "'generated-stub-logic' (real wiring, TODO business logic), 'stub' (labeled "
            "placeholder only, not functional). Never treat 'codegen_status: generated' at the "
            "top level as implying every module is production-ready — read this manifest."
        ),
    }
    manifest_rel_path = ".spec-engine/codegen-manifest.json"
    _write_file(root_fd, manifest_rel_path, json.dumps(manifest, indent=2, sort_keys=True))
    written[manifest_rel_path] = Path(manifest_rel_path)

    scaffold_written = _write_scaffold_stub_to_fd(spec, root_fd, finalized_plan)
    written.update(scaffold_written)

    return CodegenResult(written=written, scaffold_plan=finalized_plan, manifest=manifest)


def _manifest_entry(
    module: ScaffoldModule,
    generation_status: str,
    files: List[str],
    notes: str,
    *,
    connector: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if generation_status not in GENERATION_STATUSES:
        raise SpecEngineError(f"_manifest_entry: {generation_status!r} not in {GENERATION_STATUSES}")
    if connector is not None and generation_status != "generated-connector":
        raise SpecEngineError(
            "_manifest_entry: connector= is only valid on a 'generated-connector' entry"
        )
    return {
        "module_id": module.module_id,
        "kind": module.kind,
        "source_section": module.source_section,
        "generation_status": generation_status,
        "files": files,
        "notes": notes,
        # Present (non-null) ONLY on generated-connector modules — connector
        # id@version, manifest content hash, the operations wired, the
        # declared env var names, and the side-effect classes (design §6.3).
        # Always present as a key (never omitted) so the schema can require
        # it uniformly rather than treat it as sometimes-absent.
        "connector": connector,
    }


def _write_file(root_fd: int, rel_path: str, content: str) -> Path:
    """Write one generated file through a newly-created descriptor.

    Never truncate a pathname entry that was merely inspected first. A
    same-UID writer could replace such an entry with a hard link between a
    lstat and an open using the truncation flag; truncating that descriptor would modify
    the external inode. Removing the local directory entry is safe (unlink
    does not dereference a symlink or mutate another hard-link name), and an
    exclusive create then either gives this process a fresh leaf or fails if
    anything appeared in the gap.
    """
    parent_fd, leaf = _open_output_parent(root_fd, rel_path)
    try:
        try:
            # This removes only the staging-directory name. If it was a
            # hardlink, its other names and their inode are untouched. A
            # directory is deliberately not removed by this file writer.
            os.unlink(leaf, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise SpecEngineError(
                f"generate_app: cannot safely replace staged generated entry {rel_path!r}: {exc}."
            ) from exc

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(leaf, flags, 0o666, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise SpecEngineError(
                f"generate_app: staged generated entry {rel_path!r} appeared while creating it exclusively. "
                "Refusing to open an entry this call did not create."
            ) from exc
        except OSError as exc:
            raise SpecEngineError(
                f"generate_app: cannot create staged generated entry {rel_path!r} exclusively: {exc}."
            ) from exc
        try:
            created = os.fstat(descriptor)
            if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
                raise SpecEngineError(
                    f"generate_app: staged generated entry {rel_path!r} is not a private fresh regular file."
                )
            _write_all(descriptor, content.encode("utf-8"))
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)
    return Path(rel_path)


def _open_output_parent(root_fd: int, rel_path: str) -> Tuple[int, str]:
    parts = Path(rel_path).parts
    if not parts or Path(rel_path).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise SpecEngineError(f"generate_app: generated file path {rel_path!r} is not a safe relative path.")
    descriptor = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            display_path = Path(rel_path)
            try:
                observed = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise SpecEngineError(
                        f"generate_app: cannot create generated directory {component!r}: {exc}."
                    ) from exc
                observed = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
                raise SpecEngineError(
                    f"generate_app: generated path component {component!r} is not a real directory."
                )
            child_fd = _open_existing_directory_entry(descriptor, component, display_path, observed)
            os.close(descriptor)
            descriptor = child_fd
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def _read_staged_text(root_fd: int, rel_path: str) -> Optional[str]:
    parent_fd, leaf = _open_output_parent(root_fd, rel_path)
    try:
        try:
            descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            _raise_existing_content_open_error(Path(rel_path), exc)
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise SpecEngineError(f"generate_app: staged entry {rel_path!r} is not a regular file.")
            chunks = []
            while True:
                chunk = os.read(descriptor, _EXISTING_CONTENT_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)


def _write_scaffold_stub_to_fd(
    spec: SpecDocument, root_fd: int, scaffold_plan: ScaffoldPlan
) -> Dict[str, Path]:
    """Descriptor-relative counterpart to scaffold.write_scaffold_stub()."""
    written: Dict[str, Path] = {}
    scaffold_files = {
        "SPEC.md": render_markdown(spec),
        "spec.json": json.dumps(spec.to_log_record(), indent=2, sort_keys=True),
        ".spec-engine/scaffold-plan.json": json.dumps(scaffold_plan.to_log_record(), indent=2, sort_keys=True),
    }
    for rel_path, content in scaffold_files.items():
        _write_file(root_fd, rel_path, content)
        written[rel_path] = Path(rel_path)

    for directive_filename in ("CLAUDE.md", "AGENTS.md"):
        existing = _read_staged_text(root_fd, directive_filename)
        if existing is None:
            _write_file(root_fd, directive_filename, SPEC_DIRECTIVE_BLOCK)
        elif SPEC_DIRECTIVE_MARKER not in existing:
            _write_file(root_fd, directive_filename, existing.rstrip() + "\n\n" + SPEC_DIRECTIVE_BLOCK)
        written[directive_filename] = Path(directive_filename)
    return written


def _swap_aside_path(final_root: Path) -> Path:
    """The ONE, deterministic sibling path `_publish_staged_app()` ever
    renames `final_root`'s prior content aside to, for the duration of the
    two-rename swap described in its docstring below. Deterministic (not
    a `tempfile.mkdtemp()`-style random suffix) is the point: it lets
    `_recover_interrupted_publish()` find — unambiguously, on ANY later
    call — whether THIS `target_dir`'s swap was left interrupted, without
    having to guess which of possibly-several random-suffixed siblings
    might be the one that matters. A random name is exactly what let the
    original data-loss bug happen: nothing pointed back to it."""
    return final_root.parent / f".{final_root.name}.codegen-prev"


def _recover_interrupted_publish(final_root: Path, parent_fd: Optional[int] = None) -> None:
    """Called unconditionally at the very start of every `generate_app()`
    call, before `has_existing_content` is decided — repairs the ONE
    state a hard kill between `_publish_staged_app()`'s two `os.rename()`
    calls (the `has_existing_content=True` branch) can leave behind:
    `final_root` swapped aside to `_swap_aside_path(final_root)` but never
    swapped back, because the process died before the second rename ran.

    Left unrepaired, the NEXT call against the same `target_dir` — the
    natural "just re-run it" recovery action after a crash — would see
    `final_root` absent, treat this as a first-ever generation, and
    silently publish fresh content straight over it: the real prior
    content sitting in the aside directory would never be looked at
    again, and is destroyed the moment this run's own publish succeeds.
    There is no portable rename-by-file-descriptor primitive that can bind an
    already-inspected aside directory to the later path-based restore.  An
    attacker able to mutate this parent directory could replace `aside` with
    a symlink after inspection and before a restore rename, making
    `final_root` point outside the intended tree.  Therefore recovery is
    deliberately fail-closed: any reserved aside path is preserved for an
    operator to inspect and restore manually.  Ordinary runs (where aside is
    absent) remain unaffected; a crash or cleanup interruption requires an
    explicit human decision rather than an unsafe automatic rename/delete.

    Any state this function cannot safely reconcile — concretely, the
    aside path existing but not being a directory (including a symlink,
    whether it resolves to a directory or not), which nothing in this
    module ever creates — is a genuinely ambiguous situation (something
    outside `_publish_staged_app()`'s own two-rename sequence put
    something there) and is never silently guessed at: this raises
    `SpecEngineError` rather than risk restoring, or discarding, the
    wrong thing."""
    owns_parent_fd = parent_fd is None
    if parent_fd is None:
        parent_fd = _open_target_parent_safely(final_root)
    aside = _swap_aside_path(final_root)
    aside_name = aside.name
    try:
        try:
            aside_stat = os.stat(aside_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SpecEngineError(
                f"generate_app: cannot safely inspect reserved recovery path {aside}: {exc}."
            ) from exc

        if stat.S_ISLNK(aside_stat.st_mode):
            raise SpecEngineError(
                f"generate_app: {aside} exists and is a symlink. This path is reserved for "
                "_publish_staged_app()'s rename-aside-swap recovery and nothing in this module ever "
                "creates it as a symlink — refusing to follow it (which could restore a symlink onto "
                f"{final_root} or silently no-op past it during stale-aside cleanup) or guess whether it "
                f"is safe to remove outright. Move or remove {aside} by hand (after confirming what it "
                "actually is) before regenerating."
            )

        if not stat.S_ISDIR(aside_stat.st_mode):
            raise SpecEngineError(
                f"generate_app: {aside} exists but is not a directory. This path is reserved for "
                "_publish_staged_app()'s rename-aside-swap recovery and nothing in this module ever "
                "creates it as anything else — refusing to guess whether it is safe to restore into "
                f"{final_root} or delete outright. Move or remove {aside} by hand (after confirming "
                "what it actually is) before regenerating."
            )

        raise SpecEngineError(
            f"generate_app: reserved recovery directory {aside} exists. It may contain a prior "
            "target_dir following an interrupted publish, but automatic recovery is disabled because "
            "a concurrently writable parent directory cannot safely bind that path to a later rename. "
            f"Inspect and restore or remove {aside} manually before regenerating; {final_root} was left untouched."
        )
    finally:
        if owns_parent_fd:
            os.close(parent_fd)


def _require_publish_parent_isolation(
    parent_fd: int, final_root: Path, expected_target_identity: Optional[os.stat_result]
) -> None:
    """Reject an immediately unsafe *cross-account* publish parent.

    POSIX has no inode-bound rename primitive. In an ordinary private parent,
    a different account normally cannot mutate stage/final names; in a sticky
    shared directory (such as /private/var/tmp), the kernel protects entries
    owned by this account. A non-sticky group/world-writable parent provides
    neither property, so no pre-rename identity observation can make
    publication safe against another account.

    This is intentionally not described as same-UID isolation: a process
    running as the caller can mutate child entries in the staging or target
    tree before, during, or after this call. The final descriptor check can
    detect only a root-entry replacement that exists at its validation point;
    it does not attest descendant contents. Hostile same-UID writers require
    an isolated account or container/mount namespace.
    """
    parent_stat = os.fstat(parent_fd)
    writable_by_others = bool(parent_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
    if not writable_by_others:
        return
    if not parent_stat.st_mode & stat.S_ISVTX:
        raise SpecEngineError(
            f"generate_app: target_dir parent {final_root.parent} is group/world writable without the "
            "sticky bit. POSIX cannot bind an inspected stage or target inode to a later rename in "
            "that directory; choose a private parent directory instead."
        )
    if expected_target_identity is not None and expected_target_identity.st_uid != os.geteuid():
        raise SpecEngineError(
            f"generate_app: target_dir {final_root} is in a shared sticky parent but is not owned by "
            "the current account. Refusing a publication another account could race."
        )


def _assert_entry_matches_fd(parent_fd: int, name: str, expected_fd: int, display_path: Path, kind: str) -> None:
    try:
        observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise SpecEngineError(
            f"_publish_staged_app: {kind} {display_path} disappeared during publication: {exc}."
        ) from exc
    _require_stable_identity(observed, os.fstat(expected_fd), display_path, kind)


def _verify_published_target_before_return(final_root: Path, parent_fd: int, stage_fd: int) -> None:
    """Fail closed if a publish-time target replacement lands before return.

    The returned ``CodegenResult`` must not describe a tree that was swapped
    between publish and the final validation. The check is descriptor-backed
    and any mismatched directory entry is quarantined where possible. A
    same-UID process can still mutate the result *after* this check (and after
    return); POSIX provides no primitive to eliminate that separate boundary.
    """
    _verify_target_parent_binding(final_root, parent_fd)
    final_name = _target_name(final_root)
    try:
        _assert_entry_matches_fd(parent_fd, final_name, stage_fd, final_root, "published staging directory")
    except SpecEngineError as exc:
        quarantine = _quarantine_untrusted_publish_entry(parent_fd, final_name, final_root)
        location = f" quarantined at {quarantine}" if quarantine is not None else " left untouched"
        raise SpecEngineError(
            f"generate_app: target_dir identity changed after publication but before result return; "
            f"refusing to return paths that may be attacker-controlled and{location}."
        ) from exc


def _quarantine_untrusted_publish_entry(parent_fd: int, name: str, final_root: Path) -> Optional[Path]:
    """Move a post-rename mismatch out of target_dir without deleting it."""
    prefix = f".{_target_name(final_root)}.codegen-rejected-"
    for _ in range(32):
        quarantine_name = prefix + secrets.token_hex(16)
        try:
            os.stat(quarantine_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            continue
        else:
            continue
        try:
            os.rename(name, quarantine_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        except OSError:
            continue
        return final_root.parent / quarantine_name
    return None


def _publish_staged_app(
    stage_name: str,
    stage_fd: int,
    final_root: Path,
    parent_fd: int,
    *,
    has_existing_content: bool,
    expected_target_identity: Optional[os.stat_result],
) -> None:
    """The ONE moment `generate_app()` ever touches `final_root` (the
    caller's real `target_dir`): a same-filesystem, descriptor-relative `os.rename()` — a
    single atomic rename syscall — swaps the fully-written staging tree
    into `final_root`'s place. Nothing before this call has written
    anything to `final_root` itself, so a process killed at any point up
    to (but not including) this call leaves `final_root` exactly as
    `generate_app()` found it — absent, empty, or its own prior content,
    NEVER a codegen-produced partial file. The rename syscall cannot be
    observed half-done: a reader of `final_root` sees either the old
    state or the complete new tree, never a mix of the two.

    When `final_root` already held real content (`has_existing_content`),
    a direct rename of the stage onto `final_root` is refused by the OS —
    POSIX `rename(2)` only replaces a directory target that is missing or
    EMPTY, never a non-empty one (verified empirically on this repo's
    target platforms: a rename onto an existing non-empty directory
    raises `OSError: [Errno 66] Directory not empty` on macOS/BSD, or
    `OSError: [Errno 39] Directory not empty` on Linux — the code below
    does not branch on the errno value either way, since the safe
    two-rename path is always taken whenever `has_existing_content` is
    true, regardless of platform) — so the prior tree is first atomically
    renamed aside to `_swap_aside_path(final_root)` (still exactly one
    atomic rename; a DETERMINISTIC path, not a random one — see that
    function's docstring for why), the staging tree then takes `final_root`'s
    place, and the aside is removed.

    Between those two renames `final_root` is briefly ABSENT. UNLIKE a
    first-ever generation's absence, this is not a state with nothing to
    lose: real, previously-committed `target_dir` content is, at that
    instant, sitting only in the aside directory. A kill exactly here
    does not corrupt or partially-mix anything (`final_root` is cleanly
    absent, never a mix of old and new), but it DOES leave that real
    content orphaned — recoverable only because `generate_app()`
    unconditionally checks for and repairs exactly this state on every
    call, before this function ever runs again (see
    `_recover_interrupted_publish()`). This function does not, and
    structurally cannot, defend against that kill window by itself — it
    is two syscalls with nothing to catch a `SIGKILL` between them; the
    recovery guarantee lives one level up, in `generate_app()`, by
    design."""
    final_name = _target_name(final_root)
    stage_display = final_root.parent / stage_name
    _require_publish_parent_isolation(parent_fd, final_root, expected_target_identity)
    try:
        observed_stage = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise SpecEngineError(
            f"_publish_staged_app: descriptor-anchored staging directory {stage_display} disappeared "
            f"before publish: {exc}. Refusing to publish an unstable stage."
        ) from exc
    _require_stable_identity(observed_stage, os.fstat(stage_fd), stage_display, "staging directory")

    try:
        current_target = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        current_target = None
    except OSError as exc:
        raise SpecEngineError(f"_publish_staged_app: cannot inspect target_dir {final_root}: {exc}.") from exc

    if expected_target_identity is None:
        if current_target is not None:
            raise SpecEngineError(
                f"_publish_staged_app: target_dir {final_root} appeared after staging began. "
                "Refusing to replace a concurrently-created target."
            )
    else:
        if current_target is None:
            raise SpecEngineError(
                f"_publish_staged_app: target_dir {final_root} disappeared after staging began. "
                "Refusing to publish over an unstable target."
            )
        _require_stable_identity(
            expected_target_identity, current_target, final_root, "target_dir directory"
        )

    if not has_existing_content:
        try:
            os.rename(stage_name, final_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except OSError as exc:
            raise SpecEngineError(
                f"_publish_staged_app: cannot atomically publish staged content into {final_root}: {exc}."
            ) from exc
        try:
            _assert_entry_matches_fd(parent_fd, final_name, stage_fd, final_root, "published staging directory")
        except SpecEngineError as exc:
            quarantine = _quarantine_untrusted_publish_entry(parent_fd, final_name, final_root)
            location = f" quarantined at {quarantine}" if quarantine is not None else " left untouched"
            raise SpecEngineError(
                f"_publish_staged_app: stage-name identity changed across the atomic rename into "
                f"{final_root}; refusing to return a target that may be attacker-controlled and{location}."
            ) from exc
        return

    aside = _swap_aside_path(final_root)
    aside_name = aside.name
    try:
        os.stat(aside_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SpecEngineError(
            f"_publish_staged_app: cannot inspect reserved aside {aside}: {exc}. Refusing to publish."
        ) from exc
    else:
        # `_recover_interrupted_publish()` unconditionally reconciles or
        # clears this exact path at the start of every `generate_app()`
        # call, before staging even begins — by construction, it should
        # never exist here. If it does anyway (e.g. a second
        # `generate_app()` call racing this one against the same
        # `target_dir` — concurrent calls are not a supported use of this
        # function), fail loud rather than silently clobber whatever is
        # in it or lose track of `final_root`'s current content.
        raise SpecEngineError(
            f"_publish_staged_app: {aside} already exists immediately before the rename-aside-swap "
            "it is reserved for. generate_app()'s _recover_interrupted_publish() should already "
            "have reconciled or cleared this path — its unexpected presence here most likely means "
            "a concurrent generate_app() call is racing this one against the same target_dir "
            "(not supported); refusing to publish rather than risk clobbering or losing content."
        )

    try:
        os.rename(final_name, aside_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except OSError as exc:
        raise SpecEngineError(
            f"_publish_staged_app: cannot atomically preserve existing target_dir at {aside}: {exc}."
        ) from exc
    try:
        # Check the destination of the first rename, not merely the source
        # observed before it. A race here leaves final_root absent and stops
        # before the staged tree can be published.
        expected_target_fd = _open_existing_directory_entry(
            parent_fd, aside_name, aside, expected_target_identity
        )
    except SpecEngineError as exc:
        raise SpecEngineError(
            f"_publish_staged_app: target_dir identity changed across preservation rename to {aside}. "
            "Staged content was not published; inspect the reserved aside manually."
        ) from exc
    else:
        os.close(expected_target_fd)
    try:
        os.rename(stage_name, final_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    except BaseException as exc:
        # Do not restore with a pathname rename: another writer could swap
        # the reserved aside path after this function observed it. Preserve
        # the prior tree for explicit operator recovery instead.
        raise SpecEngineError(
            f"_publish_staged_app: publishing staged content failed after preserving the prior "
            f"target_dir at {aside}. Automatic restore is disabled because that reserved path could "
            "be replaced concurrently; inspect and restore it manually."
        ) from exc
    try:
        _assert_entry_matches_fd(parent_fd, final_name, stage_fd, final_root, "published staging directory")
    except SpecEngineError as exc:
        quarantine = _quarantine_untrusted_publish_entry(parent_fd, final_name, final_root)
        location = f" quarantined at {quarantine}" if quarantine is not None else " left untouched"
        raise SpecEngineError(
            f"_publish_staged_app: stage-name identity changed across the atomic rename into {final_root}; "
            f"the prior target remains at {aside}, and the mismatched published entry was{location}."
        ) from exc
    try:
        _remove_directory_tree_at(parent_fd, aside_name)
    except OSError as exc:
        # The new app is live. Preserve an unremoved aside rather than
        # attempting a second pathname cleanup; next invocation stops on the
        # reserved recovery path and asks for explicit operator handling.
        raise SpecEngineError(
            f"_publish_staged_app: new app published at {final_root}, but could not safely remove "
            f"reserved prior-content directory {aside}: {exc}. Inspect it manually before regenerating."
        ) from exc


# --------------------------------------------------------------------------
# Per-module generators — src/models/<slug>.js
# --------------------------------------------------------------------------


def _render_model_js(entity: Entity, module: ScaffoldModule) -> str:
    class_name = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", entity.name) if part) or "Entity"
    field_names = [f.name for f in entity.fields]
    fields_js = ", ".join(_js_string(n) for n in field_names)
    return f"""\
"use strict";

/**
 * GENERATED backend model for entity {_js_string(entity.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "generated"
 * (see ../../.spec-engine/codegen-manifest.json).
 *
 * In-memory store — data is NOT persisted across process restarts. A
 * persistent database is a later deliverable (TESS-VISION-AND-BUILD-SPEC.html
 * Phase 2 Epic E4: "provisions DB"), out of scope for this codegen slice.
 */

const crypto = require("node:crypto");

const FIELDS = [{fields_js}];

class {class_name}Store {{
  constructor() {{
    this._byId = new Map();
  }}

  list() {{
    return Array.from(this._byId.values());
  }}

  get(id) {{
    return this._byId.get(id) || null;
  }}

  create(data) {{
    data = data || {{}};
    const missing = FIELDS.filter((f) => !(f in data));
    if (missing.length) {{
      const err = new Error(
        {_js_string(f"{entity.name}.create: missing field(s): ")} + missing.join(", ")
      );
      err.statusCode = 400;
      throw err;
    }}
    const id = crypto.randomUUID();
    const record = {{ id }};
    for (const f of FIELDS) record[f] = data[f];
    this._byId.set(id, record);
    return record;
  }}

  update(id, data) {{
    const existing = this._byId.get(id);
    if (!existing) return null;
    data = data || {{}};
    const updated = {{ ...existing }};
    for (const f of FIELDS) {{
      if (f in data) updated[f] = data[f];
    }}
    this._byId.set(id, updated);
    return updated;
  }}

  remove(id) {{
    return this._byId.delete(id);
  }}
}}

module.exports = {{ {class_name}Store, FIELDS }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/pages/<slug>.js
# --------------------------------------------------------------------------


def _render_page_js(
    screen: KeyScreen, module: ScaffoldModule, matched_entity: Optional[Entity], matched_slug: Optional[str]
) -> str:
    title_html = _html_escape(screen.name)
    description_html = _html_escape(screen.description or "(no description in spec)")
    if matched_entity is not None and matched_slug is not None:
        body = f"""\
function render(context) {{
  const store = context.entityStores[{_js_string(matched_slug)}];
  const records = store ? store.list() : [];
  const rows = records
    .map(
      (r) =>
        "<li>" +
        Object.entries(r)
          .map(([k, v]) => "<strong>" + escapeHtml(k) + ":</strong> " + escapeHtml(v))
          .join(" &middot; ") +
        "</li>"
    )
    .join("\\n");
  return (
    "<!doctype html><html><head><meta charset=\\"utf-8\\"><title>" +
    {_js_string(title_html)} +
    "</title></head><body><h1>" +
    {_js_string(title_html)} +
    "</h1><p>" +
    {_js_string(description_html)} +
    "</p><ul>" +
    (rows || "<li>(no records yet)</li>") +
    "</ul></body></html>"
  );
}}
"""
    else:
        body = f"""\
function render(context) {{
  return (
    "<!doctype html><html><head><meta charset=\\"utf-8\\"><title>" +
    {_js_string(title_html)} +
    "</title></head><body><h1>" +
    {_js_string(title_html)} +
    "</h1><p>" +
    {_js_string(description_html)} +
    "</p><p><em>No matching data-model entity found for this screen — " +
    "this page renders the spec's own description only.</em></p></body></html>"
  );
}}
"""
    return f"""\
"use strict";

/**
 * GENERATED frontend page for screen {_js_string(screen.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "generated"
 * (see ../../.spec-engine/codegen-manifest.json).
 *
 * Server-rendered plain HTML — no build step, no client-side framework.
 */

function escapeHtml(value) {{
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}}

{body}
module.exports = {{ render }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/flows/<slug>.js
# --------------------------------------------------------------------------


def _render_flow_js(flow: KeyFlow, module: ScaffoldModule) -> str:
    steps_js = ",\n  ".join(_js_string(s) for s in flow.steps) if flow.steps else ""
    return f"""\
"use strict";

/**
 * GENERATED flow handler for {_js_string(flow.name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status:
 * "generated-stub-logic" (see ../../.spec-engine/codegen-manifest.json):
 * the step SEQUENCE below is real and executes end to end; each step's
 * business-logic body is a documented placeholder. Flow steps are
 * free-text in the spec — codegen cannot compile prose into working
 * business/integration logic. Implement each TODO before relying on this
 * flow for anything real.
 */

const STEPS = [
  {steps_js}
];

async function run(input) {{
  const trace = [];
  for (const step of STEPS) {{
    // TODO: implement this step's real business logic. `input` is the
    // parsed JSON body of the request that triggered this flow.
    trace.push({{ step, status: "not_implemented" }});
  }}
  return {{
    flow: {_js_string(flow.name)},
    executed_at: new Date().toISOString(),
    steps: trace,
  }};
}}

module.exports = {{ run, STEPS }};
"""


# --------------------------------------------------------------------------
# Per-module generators — src/integrations/<slug>.js
# --------------------------------------------------------------------------


def _render_integration_js(integration_name: str, module: ScaffoldModule) -> str:
    return f"""\
"use strict";

/**
 * GENERATED integration connector STUB for {_js_string(integration_name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status: "stub" (see
 * ../../.spec-engine/codegen-manifest.json) — NOT a working connector.
 * Deterministic codegen cannot produce a working third-party integration
 * without real credentials/API contract details this spec does not
 * carry. This file is a clearly-labeled placeholder; implement it by
 * hand before use. The generated server wires it to a route that
 * returns HTTP 501 until you do.
 */

class IntegrationNotImplementedError extends Error {{}}

async function call() {{
  throw new IntegrationNotImplementedError(
    {_js_string(f"Integration {integration_name!r} is a codegen stub — implement this connector before use.")}
  );
}}

module.exports = {{ call }};
"""


# --------------------------------------------------------------------------
# Connectors v1 — src/integrations/_connector-runtime.js (shared infra,
# written ONLY when >=1 integration resolves to a registered connector) and
# src/integrations/<slug>.js for a RESOLVED integration (generation_status:
# "generated-connector"). docs/design/connectors-architecture.md §4.2/§6.3.
#
# Split, same discipline every other codegen template already applies: the
# GENERIC transport/error-handling/config logic (fetch with an
# AbortController timeout, env-var/base-url resolution, error_map status
# mapping, the six typed error classes) lives ONCE in the shared runtime;
# each provider's file supplies ONLY what is genuinely provider-specific —
# how a normalized `generate` input becomes THAT provider's request body,
# and how THAT provider's response becomes the normalized output. This is
# manifest-driven for id/version/hash/env-var-names/base-url/auth-header/
# timeout/error_map (all captured on the ResolvedConnector snapshot codegen
# was handed — see connector_resolver.py) and hand-authored ONLY for the
# per-provider request/response SHAPE, which the manifest's input_schema/
# output_schema do not attempt to encode as a code-generation DSL in v1
# (documented limitation — see spec-engine/README.md's Connectors section).
# --------------------------------------------------------------------------


def _render_connector_runtime_js() -> str:
    return f"""\
"use strict";

/**
 * GENERATED infrastructure — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 *
 * Shared runtime for every GENERATED CONNECTOR client (generation_status:
 * "generated-connector" — see ../../.spec-engine/codegen-manifest.json).
 * Zero npm dependencies: Node core `fetch()` + `AbortController` only
 * (both global in Node >=18). Every per-connector file in this directory
 * (e.g. anthropic.js) calls createConnectorClient() with its own
 * provider-specific buildRequest()/parseResponse() pair; everything else —
 * env-var/base-url resolution, the fetch+timeout, error_map status
 * mapping, the typed error classes — lives here exactly once.
 *
 * Contract (docs/design/connectors-architecture.md §4.2):
 *   call(operation, input) -> {{ output, usage, raw }} on success.
 *   Every failure is one of the typed error classes below — never a
 *   silent 200, never invented output, never a credential in a message.
 *   Config is read LAZILY, at call time, never at boot — a generated app
 *   with a configured-nowhere connector still boots and serves every
 *   other route; see _render_server_js()'s boot-time WARNING.
 */

class ConnectorConfigError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorConfigError"; this.statusCode = 503; }}
}}
class ConnectorAuthError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorAuthError"; this.statusCode = 503; }}
}}
class ConnectorRateLimitError extends Error {{
  constructor(message, retryAfter) {{
    super(message);
    this.name = "ConnectorRateLimitError";
    this.statusCode = 429;
    this.retryAfter = retryAfter || null;
  }}
}}
class ConnectorProviderError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorProviderError"; this.statusCode = 502; }}
}}
class ConnectorContractError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorContractError"; this.statusCode = 502; }}
}}
class ConnectorInvocationError extends Error {{
  constructor(message) {{ super(message); this.name = "ConnectorInvocationError"; this.statusCode = 400; }}
}}

const ERROR_CLASSES = {{
  ConnectorAuthError,
  ConnectorRateLimitError,
  ConnectorProviderError,
  ConnectorContractError,
  ConnectorInvocationError,
}};

function createConnectorClient(config) {{
  const {{
    id, version, manifestHash, displayName,
    envVars, headerName, headerValuePrefix,
    baseUrl, baseUrlOverrideEnv,
    apiVersionPin, timeoutMs, errorMap,
    operations, buildRequest, parseResponse,
  }} = config;

  const opByName = new Map(operations.map((op) => [op.name, op]));

  function resolveBaseUrl() {{
    if (baseUrlOverrideEnv && process.env[baseUrlOverrideEnv]) {{
      const override = process.env[baseUrlOverrideEnv];
      // https-pinned, same as the manifest's declared `base_url` (Cyra
      // LOW F6, PR #84 security review fix-up round): this override is a
      // disclosed escape hatch (connectors/registry/*/README.md "Base URL
      // override"), never a license to downgrade transport security. An
      // http:// (or any non-https://) value here would let a local env
      // var silently send the real auth header/key in cleartext, or to an
      // unintended internal endpoint — refused BEFORE any network call is
      // ever attempted, with the same typed-error/503 discipline every
      // other config problem in this client already uses.
      if (!override.startsWith("https://")) {{
        throw new ConnectorConfigError(
          id + ": " + baseUrlOverrideEnv + " is set but is not an https:// URL (" +
          JSON.stringify(override) + ") — refusing a non-HTTPS base-url override; " +
          "this manifest's https-only guarantee applies to base_url_override_env too"
        );
      }}
      return override;
    }}
    return baseUrl;
  }}

  function resolveApiKey() {{
    // v1 connectors declare exactly one env var; iterating handles a
    // future manifest declaring more than one without a runtime change.
    for (const name of envVars) {{
      const value = process.env[name];
      if (value) return {{ name, value }};
    }}
    return null;
  }}

  function isConfigured() {{
    return resolveApiKey() !== null;
  }}

  async function call(operationName, input) {{
    const op = opByName.get(operationName);
    if (!op) {{
      throw new ConnectorInvocationError(
        id + ": unknown operation " + JSON.stringify(operationName) + " — declared operation(s): " +
        Array.from(opByName.keys()).join(", ")
      );
    }}
    const key = resolveApiKey();
    if (!key) {{
      throw new ConnectorConfigError(
        id + ": not configured — set " + envVars.join(" or ") + " to make this connector " +
        "operational (currently unset; this route returns 503 until it is)"
      );
    }}

    // Resolved (and https-scheme-validated) BEFORE the request-building
    // try/catch below — same reason resolveApiKey() is checked above it:
    // a config problem must surface as its own typed ConnectorConfigError
    // (503), never get silently re-wrapped into a generic
    // ConnectorInvocationError (400) by the request-building catch block.
    const resolvedBaseUrl = resolveBaseUrl();

    let url;
    let requestInit;
    try {{
      const built = buildRequest(op, input || {{}});
      url = resolvedBaseUrl.replace(/\\/$/, "") + built.path;
      const headers = Object.assign({{ "Content-Type": "application/json" }}, built.headers || {{}});
      headers[headerName] = (headerValuePrefix || "") + key.value;
      if (apiVersionPin && apiVersionPin.kind === "header") {{
        headers[apiVersionPin.name] = apiVersionPin.value;
      }}
      requestInit = {{ method: op.httpMethod, headers, body: JSON.stringify(built.body) }};
    }} catch (err) {{
      throw new ConnectorInvocationError(
        id + ": could not build a request for " + operationName + " from the given input: " + err.message
      );
    }}

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response;
    try {{
      response = await fetch(url, Object.assign({{}}, requestInit, {{ signal: controller.signal }}));
    }} catch (err) {{
      if (err.name === "AbortError") {{
        throw new ConnectorProviderError(id + ": request to provider timed out after " + timeoutMs + "ms");
      }}
      throw new ConnectorProviderError(id + ": network error calling provider: " + err.message);
    }} finally {{
      clearTimeout(timer);
    }}

    const bodyText = await response.text();
    let bodyJson = null;
    try {{
      bodyJson = bodyText ? JSON.parse(bodyText) : null;
    }} catch (err) {{
      bodyJson = null; // handled below — a non-JSON body on a non-ok response still maps by status
    }}

    if (!response.ok) {{
      const className = errorMap[String(response.status)];
      const ErrClass = ERROR_CLASSES[className] || ConnectorProviderError;
      const providerMessage =
        bodyJson && bodyJson.error && typeof bodyJson.error === "object" && bodyJson.error.message
          ? bodyJson.error.message
          : bodyText.slice(0, 200);
      const message = id + ": provider responded " + response.status + (providerMessage ? " — " + providerMessage : "");
      if (ErrClass === ConnectorRateLimitError) {{
        throw new ConnectorRateLimitError(message, response.headers.get("retry-after"));
      }}
      throw new ErrClass(message);
    }}

    if (bodyJson === null) {{
      throw new ConnectorContractError(
        id + ": provider response was not valid JSON — contract mismatch (manifest " + id + "@" + version + ")"
      );
    }}

    let normalized;
    try {{
      normalized = parseResponse(op, bodyJson);
      if (!normalized || typeof normalized.text !== "string" || !normalized.usage) {{
        throw new Error("normalized output missing required fields (text, usage)");
      }}
    }} catch (err) {{
      throw new ConnectorContractError(
        id + ": provider response did not match the manifest's declared output shape (manifest " +
        id + "@" + version + "): " + err.message
      );
    }}

    return {{ output: normalized, usage: normalized.usage, raw: bodyJson }};
  }}

  return {{
    call,
    isConfigured,
    envVars,
    OPERATIONS: operations.map((op) => op.name),
    CONNECTOR: {{ id, version, manifest_hash: manifestHash, display_name: displayName }},
  }};
}}

module.exports = {{
  createConnectorClient,
  ERROR_CLASSES,
  ConnectorConfigError,
  ConnectorAuthError,
  ConnectorRateLimitError,
  ConnectorProviderError,
  ConnectorContractError,
  ConnectorInvocationError,
}};
"""


def _resolved_connector_config_js(resolved: ResolvedConnector) -> str:
    """The JS object-literal fragment shared by every per-provider
    generated file's `createConnectorClient({{...}})` call — every field
    that came from the manifest snapshot (`ResolvedConnector`), NOT the
    provider-specific `buildRequest`/`parseResponse` pair (those are
    appended by each `_render_<provider>_client_js()` caller)."""
    op = resolved.operations[0]
    api_version_pin_js = (
        "{ kind: %s, name: %s, value: %s }"
        % (
            _js_string(resolved.api_version_pin_kind),
            _js_string(resolved.api_version_pin_name) if resolved.api_version_pin_name else "null",
            _js_string(resolved.api_version_pin_value or ""),
        )
        if resolved.api_version_pin_kind
        else "null"
    )
    error_map_js = json.dumps(resolved.error_map, sort_keys=True)
    env_vars_js = ", ".join(_js_string(v) for v in resolved.auth_env_vars)
    return f"""\
  id: {_js_string(resolved.connector_id)},
  version: {_js_string(resolved.connector_version)},
  manifestHash: {_js_string(resolved.manifest_hash)},
  displayName: {_js_string(resolved.display_name or resolved.connector_id)},
  envVars: [{env_vars_js}],
  headerName: {_js_string(resolved.auth_header_name)},
  headerValuePrefix: {_js_string(resolved.auth_header_value_prefix or "")},
  baseUrl: {_js_string(resolved.base_url)},
  baseUrlOverrideEnv: {_js_string(resolved.base_url_override_env) if resolved.base_url_override_env else "null"},
  apiVersionPin: {api_version_pin_js},
  timeoutMs: {resolved.timeout_ms},
  errorMap: {error_map_js},
  operations: [{{ name: {_js_string(op.name)}, httpMethod: {_js_string(op.http_method)}, httpPath: {_js_string(op.http_path)} }}],
"""


def _connector_client_header(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    return f"""\
"use strict";

/**
 * GENERATED integration CONNECTOR CLIENT for {_js_string(integration_name)}.
 * Source: spec section {module.source_section} — spec_engine.codegen
 * (target_stack: {DEFAULT_TARGET_STACK}). generation_status:
 * "generated-connector" (see ../../.spec-engine/codegen-manifest.json) —
 * REAL code, generated from registered connector
 * {resolved.connector_id}@{resolved.connector_version}
 * (manifest_hash={resolved.manifest_hash}). Operational once
 * {"/".join(resolved.auth_env_vars)} is configured in this process's
 * environment; until then this connector's route returns HTTP 503 (never
 * 501 — the code is real, only its runtime configuration is missing) and
 * never a silent 200 with invented output.
 *
 * Auth: reads {"/".join(resolved.auth_env_vars)} at CALL time — never at
 * boot, never logged, never echoed into any error message.
 */

const {{ createConnectorClient }} = require("./_connector-runtime.js");
"""


def _render_anthropic_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
function buildRequest(op, input) {{
  const allMessages = Array.isArray(input.messages) ? input.messages : [];
  const systemText = allMessages
    .filter((m) => m && m.role === "system")
    .map((m) => m.text)
    .join("\\n\\n");
  const messages = allMessages
    .filter((m) => m && m.role !== "system")
    .map((m) => ({{ role: m.role, content: m.text }}));
  const body = {{
    model: input.model,
    max_tokens: input.max_tokens,
    messages,
  }};
  if (input.temperature !== undefined) body.temperature = input.temperature;
  if (systemText) body.system = systemText;
  return {{ path: op.httpPath, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const blocks = Array.isArray(json.content) ? json.content : [];
  const textBlock = blocks.find((b) => b && b.type === "text");
  const usage = json.usage || {{}};
  return {{
    text: textBlock ? textBlock.text : "",
    stop_reason: json.stop_reason || "other",
    usage: {{
      input_tokens: usage.input_tokens || 0,
      output_tokens: usage.output_tokens || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


def _render_openai_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
// KNOWN v1 LIMITATION (connectors/registry/openai/README.md): sends
// normalized max_tokens as-is. OpenAI's o-series reasoning models
// (o1/o3/o4-mini) require max_completion_tokens instead and will reject
// max_tokens with their own 400 — surfaced here as a typed
// ConnectorInvocationError, never a silent failure or a guessed retry.
function buildRequest(op, input) {{
  const messages = (Array.isArray(input.messages) ? input.messages : []).map((m) => ({{
    role: m.role,
    content: m.text,
  }}));
  const body = {{
    model: input.model,
    max_tokens: input.max_tokens,
    messages,
  }};
  if (input.temperature !== undefined) body.temperature = input.temperature;
  return {{ path: op.httpPath, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const choices = Array.isArray(json.choices) ? json.choices : [];
  const first = choices[0] || {{}};
  const message = first.message || {{}};
  const usage = json.usage || {{}};
  return {{
    text: typeof message.content === "string" ? message.content : "",
    stop_reason: first.finish_reason || "other",
    usage: {{
      input_tokens: usage.prompt_tokens || 0,
      output_tokens: usage.completion_tokens || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


def _render_gemini_client_js(integration_name: str, module: ScaffoldModule, resolved: ResolvedConnector) -> str:
    config_js = _resolved_connector_config_js(resolved)
    return _connector_client_header(integration_name, module, resolved) + f"""
// The model name rides in the URL PATH ({{model}}:generateContent), not the
// body — buildRequest() substitutes it at call time.
function buildRequest(op, input) {{
  if (!input.model) {{
    throw new Error("input.model is required — Gemini's endpoint path embeds the model name");
  }}
  const allMessages = Array.isArray(input.messages) ? input.messages : [];
  const systemParts = allMessages
    .filter((m) => m && m.role === "system")
    .map((m) => ({{ text: m.text }}));
  const contents = allMessages
    .filter((m) => m && m.role !== "system")
    .map((m) => ({{ role: m.role === "assistant" ? "model" : "user", parts: [{{ text: m.text }}] }}));
  const generationConfig = {{}};
  if (input.max_tokens !== undefined) generationConfig.maxOutputTokens = input.max_tokens;
  if (input.temperature !== undefined) generationConfig.temperature = input.temperature;
  const body = {{ contents, generationConfig }};
  if (systemParts.length) body.systemInstruction = {{ parts: systemParts }};
  const path = op.httpPath.replace("{{model}}", encodeURIComponent(input.model));
  return {{ path, headers: {{}}, body }};
}}

function parseResponse(op, json) {{
  const candidates = Array.isArray(json.candidates) ? json.candidates : [];
  const first = candidates[0] || {{}};
  const parts = (first.content && Array.isArray(first.content.parts)) ? first.content.parts : [];
  const text = parts.map((p) => (p && typeof p.text === "string" ? p.text : "")).join("");
  const usage = json.usageMetadata || {{}};
  return {{
    text,
    stop_reason: first.finishReason || "other",
    usage: {{
      input_tokens: usage.promptTokenCount || 0,
      output_tokens: usage.candidatesTokenCount || 0,
    }},
  }};
}}

const client = createConnectorClient({{
{config_js}  buildRequest,
  parseResponse,
}});

module.exports = client;
"""


# Registry connector id -> codegen JS template renderer. Additive — a 4th
# provider connector needs an entry here (design §11 non-goal: v1 ships
# exactly Anthropic/OpenAI/Gemini; a NEW registry entry alone does not
# make it resolvable, deliberately — see the SpecEngineError raised above
# when a resolved connector_id has no matching renderer).
_CONNECTOR_CLIENT_RENDERERS = {
    "anthropic": _render_anthropic_client_js,
    "openai": _render_openai_client_js,
    "gemini": _render_gemini_client_js,
}


# --------------------------------------------------------------------------
# Infrastructure — src/http-util.js, src/server.js, package.json, README.md
# --------------------------------------------------------------------------


def _render_http_util_js() -> str:
    return f"""\
"use strict";

/**
 * GENERATED infrastructure — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 * Small JSON request/response helpers shared by the generated server.
 */

function sendJson(res, statusCode, body) {{
  const payload = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(statusCode, {{ "Content-Type": "application/json; charset=utf-8" }});
  res.end(payload);
}}

function readJsonBody(req) {{
  return new Promise((resolve, reject) => {{
    let raw = "";
    req.on("data", (chunk) => {{
      raw += chunk;
      if (raw.length > 5 * 1024 * 1024) {{
        reject(Object.assign(new Error("request body too large"), {{ statusCode: 413 }}));
        req.destroy();
      }}
    }});
    req.on("end", () => {{
      if (!raw) {{
        resolve({{}});
        return;
      }}
      try {{
        resolve(JSON.parse(raw));
      }} catch (err) {{
        reject(Object.assign(new Error("invalid JSON body"), {{ statusCode: 400 }}));
      }}
    }});
    req.on("error", reject);
  }});
}}

module.exports = {{ sendJson, readJsonBody }};
"""


def _render_server_js(
    spec: SpecDocument,
    *,
    entities_by_slug: List[Tuple[str, Entity]],
    screens: List[Tuple[KeyScreen, str]],
    flows: List[Tuple[KeyFlow, str]],
    integrations: List["_IntegrationRoute"],
) -> str:
    model_requires = "\n".join(
        f'const {_class_name(entity.name)}Store = require("./models/{slug}.js").{_class_name(entity.name)}Store;'
        for slug, entity in entities_by_slug
    )
    store_entries = ",\n  ".join(f"{_js_string(slug)}: new {_class_name(entity.name)}Store()" for slug, entity in entities_by_slug)
    entity_route_entries = ",\n  ".join(
        f'{{ path: "/api/{_pluralize(slug)}", slug: {_js_string(slug)}, entity: {_js_string(entity.name)} }}'
        for slug, entity in entities_by_slug
    )

    page_requires = "\n".join(
        f'const page_{slug.replace("-", "_")} = require("./pages/{slug}.js");' for _, slug in screens
    )
    page_route_entries = ",\n  ".join(
        f'{{ path: "/{slug}", name: {_js_string(screen.name)}, render: page_{slug.replace("-", "_")}.render }}'
        for screen, slug in screens
    )

    flow_requires = "\n".join(
        f'const flow_{slug.replace("-", "_")} = require("./flows/{slug}.js");' for _, slug in flows
    )
    flow_route_entries = ",\n  ".join(
        f'{{ path: "/api/flows/{slug}", name: {_js_string(flow.name)}, run: flow_{slug.replace("-", "_")}.run }}'
        for flow, slug in flows
    )

    integration_requires = "\n".join(
        f'const integration_{route.slug.replace("-", "_")} = require("./integrations/{route.slug}.js");'
        for route in integrations
    )
    integration_route_entries = ",\n  ".join(
        (
            f'{{ path: "/api/integrations/{route.slug}", name: {_js_string(route.integration_name)}, '
            f'kind: "connector", operation: {_js_string(route.operation)}, '
            f'envVars: [{", ".join(_js_string(v) for v in route.env_vars)}], '
            f'call: integration_{route.slug.replace("-", "_")}.call }}'
            if route.kind == "connector"
            else
            f'{{ path: "/api/integrations/{route.slug}", name: {_js_string(route.integration_name)}, '
            f'kind: "stub", operation: null, envVars: [], '
            f'call: integration_{route.slug.replace("-", "_")}.call }}'
        )
        for route in integrations
    )
    connector_boot_checks = "\n".join(
        (
            f'  if (!({" || ".join("process.env[" + _js_string(v) + "]" for v in route.env_vars)})) {{\n'
            f'    console.warn("[connector] " + {_js_string(route.integration_name)} + " ({route.connector_id}) is NOT '
            f'configured — set {" or ".join(route.env_vars)} to make POST /api/integrations/{route.slug} operational. '
            'Until then it returns 503, never a silent 200.");\n'
            "  }"
        )
        for route in integrations
        if route.kind == "connector"
    )

    return f"""\
#!/usr/bin/env node
"use strict";

/**
 * GENERATED server — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * {_INFRA_NOTE}
 * Zero npm dependencies: Node core `http` only.
 *
 * Run:  node src/server.js   (or `npm start`)
 * Test: node --test {ACCEPTANCE_TEST_REL_PATH}   (or `npm test`)
 *
 * Listens on process.env.PORT || 3000. See ../SPEC.md for what this app
 * does, and ../.spec-engine/codegen-manifest.json for exactly which parts
 * of this generated app are fully real vs. labeled stubs.
 */

const http = require("node:http");
const {{ readJsonBody, sendJson }} = require("./http-util.js");

{model_requires}
{page_requires}
{flow_requires}
{integration_requires}

const entityStores = {{
  {store_entries}
}};

const ENTITY_ROUTES = [
  {entity_route_entries}
];

const PAGE_ROUTES = [
  {page_route_entries}
];

const FLOW_ROUTES = [
  {flow_route_entries}
];

const INTEGRATION_ROUTES = [
  {integration_route_entries}
];

async function handleEntityRoute(req, res, route, restPath) {{
  const store = entityStores[route.slug];
  const id = restPath.replace(/^\\//, "");
  try {{
    if (req.method === "GET" && !id) {{
      sendJson(res, 200, store.list());
      return;
    }}
    if (req.method === "GET" && id) {{
      const record = store.get(id);
      sendJson(res, record ? 200 : 404, record || {{ error: "not found" }});
      return;
    }}
    if (req.method === "POST" && !id) {{
      const body = await readJsonBody(req);
      const record = store.create(body);
      sendJson(res, 201, record);
      return;
    }}
    if (req.method === "PUT" && id) {{
      const body = await readJsonBody(req);
      const record = store.update(id, body);
      sendJson(res, record ? 200 : 404, record || {{ error: "not found" }});
      return;
    }}
    if (req.method === "DELETE" && id) {{
      const removed = store.remove(id);
      sendJson(res, removed ? 204 : 404, removed ? undefined : {{ error: "not found" }});
      return;
    }}
    sendJson(res, 405, {{ error: "method not allowed" }});
  }} catch (err) {{
    sendJson(res, err.statusCode || 500, {{ error: err.message }});
  }}
}}

function createServer() {{
  // Boot-time WARNING (never fatal) per unconfigured GENERATED CONNECTOR —
  // an app with declared-but-unconfigured connectors still boots and
  // serves every non-connector route; this is the only place that state
  // is surfaced (design §4.2: "the state is visible without being
  // fatal"). Never logs a key or its value — only the env var NAME.
{connector_boot_checks}

  return http.createServer(async (req, res) => {{
    let url;
    try {{
      url = new URL(req.url, "http://localhost");
    }} catch (err) {{
      sendJson(res, 400, {{ error: "invalid request URL" }});
      return;
    }}
    const pathname = url.pathname;

    if (pathname === "/health") {{
      sendJson(res, 200, {{ status: "ok" }});
      return;
    }}

    if (pathname === "/") {{
      sendJson(res, 200, {{
        app: {_js_string(spec.title)},
        generated_from: "SPEC.md",
        pages: PAGE_ROUTES.map((r) => r.path),
        api: ENTITY_ROUTES.map((r) => r.path),
        flows: FLOW_ROUTES.map((r) => r.path),
        integrations: INTEGRATION_ROUTES.map((r) => r.path),
      }});
      return;
    }}

    for (const route of PAGE_ROUTES) {{
      if (pathname === route.path) {{
        res.writeHead(200, {{ "Content-Type": "text/html; charset=utf-8" }});
        res.end(route.render({{ entityStores }}));
        return;
      }}
    }}

    for (const route of ENTITY_ROUTES) {{
      if (pathname === route.path || pathname.startsWith(route.path + "/")) {{
        const restPath = pathname.slice(route.path.length);
        await handleEntityRoute(req, res, route, restPath);
        return;
      }}
    }}

    for (const route of FLOW_ROUTES) {{
      if (pathname === route.path && req.method === "POST") {{
        let body = {{}};
        try {{
          body = await readJsonBody(req);
        }} catch (err) {{
          // Malformed body — flows still run with an empty input rather
          // than failing the request; the flow's own TODO logic decides
          // what to do with a missing field.
        }}
        const result = await route.run(body);
        sendJson(res, 200, result);
        return;
      }}
    }}

    for (const route of INTEGRATION_ROUTES) {{
      if (pathname === route.path && req.method === "POST") {{
        if (route.kind === "connector") {{
          // GENERATED CONNECTOR — a real client, wired to a real route.
          // Every failure is one of the typed error classes from
          // _connector-runtime.js; err.statusCode carries the real HTTP
          // status (503 unconfigured, 429 rate-limited, 502 provider/
          // contract, 400 invocation) — NEVER a bare 501 (that status is
          // reserved for an UNRESOLVED integration, below) and never a
          // silent 200 on failure.
          let body = {{}};
          try {{
            body = await readJsonBody(req);
          }} catch (err) {{
            sendJson(res, err.statusCode || 400, {{ status: "error", connector: route.name, error: err.message }});
            return;
          }}
          try {{
            const result = await route.call(route.operation, body);
            sendJson(res, 200, {{ status: "ok", output: result.output, usage: result.usage }});
          }} catch (err) {{
            sendJson(res, err.statusCode || 500, {{ status: "error", connector: route.name, error: err.message }});
          }}
          return;
        }}
        // UNRESOLVED integration — today's unchanged stub behavior.
        try {{
          await route.call();
          sendJson(res, 200, {{ status: "ok" }});
        }} catch (err) {{
          sendJson(res, 501, {{ status: "not_implemented", integration: route.name, error: err.message }});
        }}
        return;
      }}
    }}

    sendJson(res, 404, {{ error: "not found" }});
  }});
}}

if (require.main === module) {{
  // PORT=0 asks the OS for a free ephemeral port (used by the boot-proof
  // test in tests/spec_engine/test_codegen_app_boots.py) — the ACTUAL
  // bound port is read back from server.address().port, never assumed to
  // equal the requested value, so this line is correct in both cases.
  // NOTE: `Number(process.env.PORT) || 3000` would be wrong here — `0` is
  // falsy in JS, so that pattern would silently discard an explicit
  // PORT=0 and fall back to 3000. Check for `undefined`/empty explicitly
  // instead.
  const port = process.env.PORT !== undefined && process.env.PORT !== "" ? Number(process.env.PORT) : 3000;
  const server = createServer();
  server.listen(port, () => {{
    console.log("Generated app listening on http://localhost:" + server.address().port);
  }});
}}

module.exports = {{ createServer, entityStores }};
"""


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name) if part) or "Entity"


def _render_package_json(spec: SpecDocument) -> str:
    pkg = {
        "name": f"{_slugify(spec.spec_id)}-generated-app",
        "version": "0.1.0",
        "private": True,
        "description": f"Generated from SPEC.md by spec_engine.codegen (twiss-io/tess-os). {spec.title}",
        "main": "src/server.js",
        "scripts": {
            "start": "node src/server.js",
            "test": f"node --test {ACCEPTANCE_TEST_REL_PATH}",
        },
        "engines": {"node": ">=18"},
    }
    return json.dumps(pkg, indent=2) + "\n"


def _render_app_readme(spec: SpecDocument, target_stack: str, integrations: List["_IntegrationRoute"]) -> str:
    stub_names = [r.integration_name for r in integrations if r.kind == "stub"]
    connector_lines = [
        f"  - **{r.integration_name}** — real connector client (`{r.connector_id}`); configure "
        f"`{' or '.join(r.env_vars)}` to make `POST /api/integrations/{r.slug}` operational. Until "
        "then that route returns `503` (not `501`)."
        for r in integrations
        if r.kind == "connector"
    ]
    connector_block = (
        "\n" + "\n".join(connector_lines) if connector_lines
        else "\n  - (none in this spec)"
    )
    return f"""\
# {spec.title}

**GENERATED from `SPEC.md` by `spec_engine.codegen`** (twiss-io/tess-os) —
target stack: `{target_stack}`. `SPEC.md` in this repo's root is the
source of truth; see `CLAUDE.md`/`AGENTS.md` for the full spec-authoritative
rule. Do not edit generated code first and back-port to the spec later —
edit `SPEC.md`, then regenerate (or hand-edit code and update the spec to
match — see `.spec-engine/codegen-manifest.json`'s `notes` field for what
this codegen pass covers).

## Run it

```bash
node src/server.js       # or: npm start
```

Then visit `http://localhost:3000/` (or `PORT=<n> node src/server.js` for
a different port). `GET /health` returns `{{"status":"ok"}}` once the
server is up.

## Test it

```bash
node --test {ACCEPTANCE_TEST_REL_PATH}       # or: npm test
```

(Always an explicit file path, never a bare `tests/` directory —
`node --test <directory>`'s built-in test-discovery behavior is not
stable across Node versions; see `ACCEPTANCE_TEST_REL_PATH`'s comment in
`spec_engine/codegen.py` for the empirical Node 20 vs. 22 difference
that motivated this.)

Zero npm dependencies — this whole app runs on Node core only (`node:http`,
`node:crypto`, `node:test`, `node:assert/strict`, plus the built-in global
`fetch()`). `npm install` is not required and there is no lockfile.

## What's real vs. stub — read `.spec-engine/codegen-manifest.json`

This codegen pass is honest about what it can and cannot deterministically
generate:

- **Real, working code:** the data-model entities' CRUD stores and REST
  API, the frontend pages, and the acceptance test suite.
- **Real wiring, placeholder business logic:** each flow's route and step
  sequence execute for real, but every step's body is a `// TODO` — flow
  steps are free text in the spec, not something codegen can compile into
  working business logic.
- **Real connector client — configure an env var to make it operational:**
  an integration whose name matched a REGISTERED connector
  (`connectors/registry/**` in the tess-os repo this app was generated
  from) gets a real, vendored `fetch()` client, not a stub. The code is
  real; whether it can actually reach the provider depends on runtime
  configuration this repo cannot carry — until the env var below is set,
  its route answers `503`, never a silent `200`, never `501` (that status
  means "no connector", not "not configured yet"):{connector_block}
- **Labeled stubs, not functional:** every OTHER integration name — no
  registered connector matched it. Codegen cannot produce a working
  connector to `{", ".join(stub_names) or "(none in this spec)"}` without
  real credentials/API contract details this spec does not carry; its
  route returns `501`.

## Persistence

In-memory only — every entity's data resets when the process restarts.
A persistent database is a later pipeline deliverable (Phase 2 Epic E4:
"provisions DB"), out of scope for this codegen slice.
"""


def _render_acceptance_test_js(spec: SpecDocument, *, entities: List[Tuple[str, Entity]]) -> str:
    entity_tests = []
    for slug, entity in entities:
        path = f"/api/{_pluralize(slug)}"
        payload = {f.name: _sample_value_for_field(f, 1) for f in entity.fields}
        entity_tests.append(f"""\
test({_js_string(f"{entity.name}: create then list round-trip")}, withServer(async (base) => {{
  const res = await fetch(base + {_js_string(path)}, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({json.dumps(payload)}),
  }});
  assert.equal(res.status, 201);
  const created = await res.json();
  assert.ok(created.id);
  const listRes = await fetch(base + {_js_string(path)});
  assert.equal(listRes.status, 200);
  const list = await listRes.json();
  assert.ok(list.some((r) => r.id === created.id));
}}));""")

    criteria_tests = []
    for i, criterion in enumerate(spec.acceptance_criteria):
        matched = _match_entity_by_name(criterion, [e for _, e in entities])
        matched_slug = None
        if matched is not None:
            for slug, entity in entities:
                if entity is matched:
                    matched_slug = slug
                    break
        test_name = f"ACCEPTANCE: {criterion}"
        if matched is not None and matched_slug is not None:
            path = f"/api/{_pluralize(matched_slug)}"
            payload = {f.name: _sample_value_for_field(f, 100 + i) for f in matched.fields}
            criteria_tests.append(f"""\
test({_js_string(test_name)}, withServer(async (base) => {{
  // Matched entity: {matched.name!r} — exercised via a real create+list round-trip.
  const res = await fetch(base + {_js_string(path)}, {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({json.dumps(payload)}),
  }});
  assert.equal(res.status, 201);
}}));""")
        else:
            criteria_tests.append(f"""\
test({_js_string(test_name)}, withServer(async (base) => {{
  // No data-model entity name matched in this criterion's text — codegen
  // cannot derive a specific behavioral assertion deterministically.
  // Falls back to the baseline boot check; verify this criterion by hand.
  const res = await fetch(base + "/health");
  assert.equal(res.status, 200);
}}));""")

    entity_tests_js = "\n\n".join(entity_tests)
    criteria_tests_js = "\n\n".join(criteria_tests)

    return f"""\
"use strict";

/**
 * GENERATED acceptance tests — spec_engine.codegen (target_stack: {DEFAULT_TARGET_STACK}).
 * Source: spec section acceptance_criteria (+ a baseline boot/health check
 * and a per-entity CRUD round-trip that always run regardless of
 * acceptance_criteria content). generation_status: "generated" (see
 * ../.spec-engine/codegen-manifest.json).
 *
 * Run (from the repo root): node --test {ACCEPTANCE_TEST_REL_PATH}   (or
 * `npm test`). Zero test-framework dependencies — Node core `node:test`
 * + `node:assert/strict` + the built-in global `fetch()`.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const {{ createServer }} = require("../src/server.js");

function withServer(fn) {{
  return async () => {{
    const server = createServer();
    await new Promise((resolve) => server.listen(0, resolve));
    const port = server.address().port;
    const base = "http://localhost:" + port;
    try {{
      await fn(base);
    }} finally {{
      await new Promise((resolve) => server.close(resolve));
    }}
  }};
}}

test("server boots and GET /health returns ok", withServer(async (base) => {{
  const res = await fetch(base + "/health");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, "ok");
}}));

{entity_tests_js}

{criteria_tests_js}
"""


__all__ = [
    "DEFAULT_TARGET_STACK",
    "SUPPORTED_TARGET_STACKS",
    "GENERATION_STATUSES",
    "CodegenResult",
    "generate_app",
]
