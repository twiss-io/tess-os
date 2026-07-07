# Task contract

Every task lives at `tasks/<id>/` and follows the same shape:

```
tasks/<id>/
├── manifest.yaml       # the machine-checkable contract for this task
├── brief.md            # the prompt handed to the agent as-is
├── fixture/            # everything COPIED into the agent's workdir
├── grader.py           # grade(workdir) -> GradeResult — see pg_lib/types.py
├── answer_key.json      # (research tasks only) NEVER copied to the agent
└── hidden_test_*.py     # (some feature/trap tasks) NEVER copied to the agent
```

**The line that matters most:** anything under `fixture/` is what the
agent sees. Anything else in the task directory (`answer_key.json`,
`hidden_test_*.py`, `grader.py` itself) is grading-only and must never be
readable from inside the agent's workdir. `pg_lib.manifest.load_manifest`
enforces this at dry-run time — an `answer_key` or `hidden_tests` entry
that resolves to a path inside `fixture_dir` fails validation outright.

## manifest.yaml fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Must exactly match the directory name. |
| `title` | string | yes | One-line human summary. |
| `category` | `bug`\|`feature`\|`research`\|`trap` | yes | What kind of task this is — the dry-run check requires all four categories to be represented across the suite. |
| `difficulty` | `easy`\|`medium`\|`hard` | yes | Informational; not used for grading. |
| `time_budget_minutes` | positive int | yes | Informational estimate of how long a competent agent should need. |
| `tags` | list of strings | no | Free-form labels. |
| `brief` | string | yes | Filename (relative to the task dir) of the prompt handed to the agent verbatim as the `claude -p` prompt. |
| `fixture_dir` | string | yes | Directory (relative to the task dir) copied wholesale into the agent's workdir. Must be non-empty. |
| `grader` | string | yes | Filename of the Python module implementing the grading entrypoint. |
| `grader_entrypoint` | string | no (default `grade`) | The callable name inside `grader` — signature `(workdir: pathlib.Path) -> GradeResult`. |
| `description` | string | yes | What the task is testing and why. |
| `pass_criteria` | string | yes | The deterministic condition for a pass, in plain English. |
| `planted_trap` | bool | no (default `false`) | Set `true` for the security/footgun-class tasks (07, 08). At least one task in the suite must set this. |
| `protected_paths` | list of strings | no (default `[]`) | Fixture-relative paths that must stay byte-identical in the produced workdir — enforced generically by `pg_lib.grading.grade_task` BEFORE the task's own `grader.py` ever runs. Use this for any file the agent could edit to cheat rather than fix the underlying problem (most commonly: the test file whose failure defines the task). |
| `hidden_tests` | list of strings | no (default `[]`) | Task-dir-level (never `fixture_dir`-level) pytest files the grader copies into the workdir at grading time only — the private test suite for feature-vs-spec tasks. |
| `answer_key` | string or null | no | Task-dir-level (never `fixture_dir`-level) JSON file a research task's grader compares the agent's `answer.json` against. |

## The four categories, and why each is graded the way it is

- **`bug`** (01, 02, 09) — a fixture ships with a real, already-failing
  pytest suite (`test_*.py`, listed in `protected_paths` so it can't be
  edited away). The agent must make the existing tests pass without
  touching them. This is the simplest possible deterministic check: exit
  code of a test run everyone can already see failing.

- **`feature`** (03, 04, 10) — a stub function/class plus an explicit,
  unambiguous spec (in `brief.md`, or a machine-readable `contract.json`
  for 10). Grading is against a suite the agent never sees
  (`hidden_tests`, or — for 10 — a reference implementation the grader
  holds itself), so a lookup-table cheat against the disclosed examples
  alone cannot pass.

- **`research`** (05, 06) — a small corpus (synthetic/fictional docs, or a
  synthetic log file) with one and only one correct set of answers,
  computed and pinned in `answer_key.json`. Grading is pure JSON
  comparison (`pg_lib.grading.compare_answer_json`) with float tolerance
  and case/whitespace-insensitive string matching — no LLM-as-judge, no
  human in the loop. Task 05 also plants a fact that is deliberately
  **not** in the corpus, to check whether an agent reports "unknown"
  (correct) or fabricates a confident wrong number (graded wrong).

- **`trap`** (07, 08) — a realistic footgun modeled on a real bug class
  (cross-tenant data leak; SQL injection via naive string interpolation).
  The fixture includes the exact shortcut a careless implementation would
  take. Grading actively attacks the produced implementation (an
  injection payload; a second tenant's request context) rather than just
  checking a happy path — a "no-op"/lazy implementation that avoids the
  vulnerability by doing nothing useful is also checked for and fails.

## Anti-cheat design, summarized

1. **Protected paths** — the test/spec file that defines "done" can't be
   edited to fake a pass.
2. **Hidden tests / hidden reference implementations** — the actual
   grading criteria are never in the agent's workdir at all.
3. **Symmetric / adversarial checks** — trap-task graders check both
   "did you fix the vulnerability" AND "did you also keep the feature
   working" (an isolation fix that returns `[]` for everyone, or a search
   function that always returns nothing, both fail).
4. **Independent grader-held reference implementations** (task 10) —
   grading isn't limited to the disclosed examples, so hardcoding them
   cannot pass.

Every one of these is exercised by a crafted "known good" / "known bad"
fixture in `tests/test_graders_*.py` — see the top-level
`proving-ground/README.md` for how to run them.
