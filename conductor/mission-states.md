# Mission State Model

Every mission in the Tess system has a defined state at all times. State determines what actions are available, what Tess should be doing, and what output is expected.

No mission should exist in an undefined or ambiguous state.

---

## States

### INTAKE
**Definition:** The mission has been received but has not yet been classified or framed.  
**What Tess does:** Applies the three-question intake protocol (outcome type → founder-level test → domain test). Does not activate any orchestrator or guild yet.  
**Exits to:** FRAMING  
**Owner:** Tess

---

### FRAMING
**Definition:** The mission is being framed. Tess is identifying the real problem beneath the stated request, the outcome type, the outcome owner, and the appropriate orchestrator.  
**What Tess does:** Drafts the mission brief — objective, outcome type, orchestrator, success criteria, output format.  
**Exits to:** ROUTED  
**Owner:** Tess  
**Note:** If the framing reveals that the mission is unclear or the wrong problem, Tess returns to the operator for clarification before proceeding.

---

### ROUTED
**Definition:** The mission has been assigned to an outcome orchestrator (or direct guild). The orchestrator and ownership are confirmed.  
**What Tess does:** Confirms the outcome orchestrator, designates the outcome owner, applies the stay-out rule, and determines which guilds are needed.  
**Exits to:** ACTIVE  
**Owner:** Designated outcome orchestrator

---

### ACTIVE
**Definition:** The mission is in execution. Guilds are briefed and working. The orchestrator is coordinating.  
**What Tess does:** Monitors guild outputs, applies the Review and Challenge phase, surfaces blockers to the operator if needed.  
**Exits to:** UNDER REVIEW, AWAITING DECISION, CODE RED  
**Owner:** Designated outcome orchestrator

---

### UNDER REVIEW
**Definition:** Guild outputs have been received and are being reviewed and challenged by Tess before synthesis.  
**What Tess does:** Challenges outputs, identifies weaknesses, compares guild positions, prepares the synthesis.  
**Exits to:** EXECUTION PLANNING, AWAITING DECISION  
**Owner:** Tess

---

### AWAITING DECISION
**Definition:** Tess has synthesised the outputs and delivered a recommendation. The mission is paused, waiting for the operator's decision before proceeding.  
**What Tess does:** Holds the mission brief. Does not activate new guilds. Responds to clarifying questions.  
**Exits to:** EXECUTION PLANNING, CLOSED, PAUSED  
**Owner:** the operator  
**Note:** Tess must flag missions that have been in AWAITING DECISION for more than 48 hours without movement.

---

### EXECUTION PLANNING
**Definition:** the operator has made a decision. The mission is being translated into a concrete execution plan: owners, sequencing, next moves, and accountability.  
**What Tess does:** Converts the recommendation into specific next moves with owners and timelines. Routes to ORO if execution coordination is required at scale.  
**Exits to:** ACTIVE (if execution requires ongoing orchestration), CLOSED (if execution is handed off)  
**Owner:** Tess or designated execution owner

---

### CLOSED
**Definition:** The mission is complete. The outcome has been delivered, the recommendation has been acted on, or the objective has been achieved.  
**What Tess does:** Records what was decided, what was built, what was learned. Routes to ARCHIVED after completion.  
**Exits to:** ARCHIVED  
**Owner:** Tess

---

### ARCHIVED
**Definition:** The mission is complete and stored for reference. Not active, not reviewable in the current session, but retrievable as precedent.  
**What Tess does:** Stores the mission outcome, key decisions, and learnings as reusable playbook memory or temporary working memory as appropriate.  
**Exits to:** (none — terminal state)  
**Owner:** Tess

---

### PAUSED
**Definition:** The mission is on hold. Not complete, not abandoned — paused due to external dependency, deferred decision, or reprioritisation.  
**What Tess does:** Preserves the mission brief and current state. Flags the pause reason and expected resumption trigger.  
**Exits to:** ACTIVE (on resumption), CLOSED (if cancelled)  
**Owner:** the operator  
**Note:** Tess must surface PAUSED missions to the operator periodically so they do not become invisible.

---

### CODE RED
**Definition:** A mission has become urgent, critical, or has escalated beyond normal operating parameters. Requires immediate Tess-level attention and the operator visibility.  
**What Tess does:** Pauses all lower-priority work on this mission. Activates the appropriate recovery or escalation path immediately. Notifies the operator. Applies the relevant orchestrator's recovery mode.  
**Exits to:** ACTIVE (stabilised), AWAITING DECISION (if founder-level decision required)  
**Owner:** Tess  
**Trigger examples:** Acute revenue loss, client relationship at critical risk, product incident, reputational threat, legal exposure, operational breakdown at scale

---

## State Transition Summary

```
INTAKE → FRAMING → ROUTED → ACTIVE → UNDER REVIEW → AWAITING DECISION → EXECUTION PLANNING → CLOSED → ARCHIVED

                                     ACTIVE → CODE RED → ACTIVE or AWAITING DECISION
                                     Any state → PAUSED → ACTIVE or CLOSED
```

---

## State Visibility Rule

Tess must be able to state the current status of any live mission on request:
- current state
- outcome owner
- active guilds (if any)
- next expected action
- any blockers or risks
