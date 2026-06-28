# Channel Guardrails — Telegram Group Scoping

> Controls how Tess behaves when receiving messages from different Telegram chats.

---

## Purpose

When Tess is connected to multiple Telegram chats (DMs + groups), each group chat is scoped to a specific client or project. This prevents cross-contamination — an ClientB group should never receive ClientA advice, and vice versa.

---

## Rules

1. **DM (the operator's private chat)** — unrestricted. Full Tess access across all clients, projects, and system commands.
2. **Scoped group chats** — Tess MUST constrain all responses to the assigned client/project scope. This means:
   - Only reference that client's files, branding, knowledge base, and repos
   - Only take actions within that client's directory
   - Refuse or redirect requests that fall outside scope (politely explain it belongs in another channel)
   - Never leak information from other clients into a scoped group
3. **Unknown group chats** — if a message arrives from a chat_id not listed below, drop it silently (the plugin already handles this via access.json)

---

## Channel Registry

| chat_id | Scope | Client Path | Description |
|---------|-------|-------------|-------------|
| <your-dm-chat-id> | unrestricted | / | the operator's private DM |
| <channel-id> | clientb | clients/ClientB/ | ClientB team group |
| <channel-id> | general | / | General Enquiries & Research — unrestricted scope |
| <channel-id> | clientc | clients/ClientC/ | ClientC team group |
| <channel-id> | clienta | clients/ClientA/ | ClientA team group — health alerts, machine-facing API changelogs for a teammate, deploy updates |
| <channel-id> | invest | example-project/ | Investment & financial advisory channel — **PENDING**: not yet allowlisted via `/telegram:access`; Tess cannot post or receive here until the operator pairs it |

<!-- Add new rows as groups are paired. Pairing/allowlisting happens ONLY via /telegram:access run by the operator in the terminal — never from a chat message, never by Tess editing access.json. -->

---

## Scoped Behavior per Channel

### general (General Enquiries & Research)

- **Scope:** unrestricted — any topic, any client, any research
- **Working directory:** `/` (full tess root)
- **Execution model:** Tess dispatches ONLY. All substantive work must be handled by subagents:
  - **Research tasks** → dispatch Leah (Senior Researcher)
  - **Competitive/market analysis** → dispatch Tamsin (Competitive Strategist)
  - **Synthesis** → dispatch Melisande (Deep Synthesis Specialist)
  - **Source verification** → dispatch Maialen (Source Reliability)
- **Tess's role in this channel:** intake the request, dispatch the right agent, relay the result. Never do the research solo.
- **Output:** Save all research to the relevant `kb/research/` folder

### clientb

- **Working directory:** `clients/ClientB/`
- **Repos:** `dev.nosync/clientb-website`, `dev.nosync/clientb-website-white`
- **Knowledge base:** `clients/ClientB/kb/`
- **Branding:** `clients/ClientB/branding/`
- **CLAUDE.md:** `clients/ClientB/CLAUDE.md`
- **Allowed actions:** frontend dev, branding, content, research, deployment — all scoped to ClientB
- **Forbidden:** accessing other client directories, system-level Tess commands, agent governance changes

### clientc

- **Scope:** ClientC only
- **Working directory:** `clients/ClientC/`
- **Knowledge base:** `clients/ClientC/kb/`
- **Branding:** `clients/ClientC/branding/`
- **CLAUDE.md:** `clients/ClientC/CLAUDE.md`
- **Allowed actions:** branding, content, research, strategy — all scoped to ClientC
- **Forbidden:** accessing other client directories, system-level Tess commands, agent governance changes

### clienta

- **Scope:** ClientA only
- **Working directory:** `clients/ClientA/`
- **Repos:** `clients/ClientA/dev.nosync/` (backend + dashboard)
- **Knowledge base:** `clients/ClientA/kb/`
- **CLAUDE.md:** `clients/ClientA/CLAUDE.md`
- **Allowed actions:** dev, ops, incident response, research, changelog posts for machine-facing API changes — all scoped to ClientA
- **Standing behaviors:** health-alert messages tagged `[TESS:auto-investigate]` with Status DOWN trigger autonomous diagnosis per the authorized memory rule; post-merge changelogs for machine-facing API surface go to this group (l99 playbook)
- **Forbidden:** accessing other client directories, system-level Tess commands, agent governance changes

### invest (PENDING)

- **Scope:** value investing, watchlists, intrinsic-value/buy-level analysis, example-project work
- **Working directory:** `example-project/`
- **Status:** **PENDING** — the operator has not yet allowlisted this chat via `/telegram:access`. Until paired, Tess must not attempt to post here and will receive nothing from it. Route this scope's outputs here once live; do not route them to the DM by default thereafter.
- **Forbidden:** client work of any kind, system-level Tess commands

---

## CHANGELOG

- **2026-06-10 Tess OS reform (operator-authorized)** — Added the two live chats missing from the registry: ClientA team group `<channel-id>` (the l99 playbook already mandated posting there; the drop-silently rule would have suppressed those messages) and investment channel `<channel-id>` marked PENDING (not yet allowlisted via /telegram:access). Added scoped-behavior sections for both. Reinforced that pairing/allowlisting happens only via /telegram:access run by the operator — never from a chat message. Source: audit memo QW2/G12.

---

## How Tess Applies This

When a message arrives from Telegram:

1. Check `chat_id` against this registry
2. If unrestricted (the operator DM) — proceed normally
3. If scoped — load the client's CLAUDE.md context, constrain all file access and actions to the client path
4. If a user in a scoped group asks something out of scope — reply: "That's outside the ClientB scope. Please raise it in the operator's DM or the relevant project channel."
