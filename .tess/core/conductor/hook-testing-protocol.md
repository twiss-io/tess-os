# Hook Testing Protocol

Every hook must pass these tests BEFORE being considered production-ready. The previous prompt-type PreToolUse hooks deadlocked all subagents because they were deployed without testing.

---

## Before Deploying Any Hook

### 1. Syntax Validation
```bash
cat .claude/settings.json | python3 -m json.tool
```
Must exit 0 with valid JSON output.

### 2. Schema Validation
```bash
python3 -c "import json; d=json.load(open('.claude/settings.json')); [print(f'{k}: {len(v)} hooks') for k,v in d.get('hooks',{}).items()]"
```
Must list all hook events and counts correctly.

### 3. Subagent Safety Test
After deploying the hook:
- Dispatch a trivial subagent task (e.g., "Read CLAUDE.md and report the first line")
- Confirm the subagent completes without blocking, deadlocking, or receiving contradictory instructions
- If the subagent fails or blocks: the hook is not safe. Remove it immediately.

### 4. Trigger Verification
For PostToolUse hooks: dispatch an agent and confirm the hook message appears in the session after the agent returns.
For SessionStart hooks: start a new session and confirm the message appears.

---

## Hook Type Safety Rules

| Hook Type | Safe for Tess? | Safe for Subagents? | Use? |
|---|---|---|---|
| `command` (echo) | Yes | Yes — non-blocking | Preferred |
| `prompt` | Risky — spawns LLM eval | DANGEROUS — can deadlock | Never use |
| `agent` | Risky — spawns full agent | DANGEROUS — recursive spawn | Never use |

**Rule: Only use `command` type hooks with `echo` output in the Tess system.**

Prompt and agent hooks spawn additional LLM evaluations that fire in ALL contexts including subagents. They cannot distinguish between Tess and dispatched specialists. They will deadlock.

---

## Post-Deployment Monitoring

After any hook change, monitor the next 3 agent dispatches for:
- Subagent completion (did it finish?)
- Hook message appearance (did the reminder show?)
- No false blocks (did any tool call get incorrectly interrupted?)

If any of these fail, revert the hook immediately.