# Mission State Model

Every mission in the {{ASSISTANT_NAME}} system has a defined state at all times. State determines what actions are available, what {{ASSISTANT_NAME}} should be doing, and what output is expected.

No mission should exist in an undefined or ambiguous state.

---

## States

### INTAKE
**Definition:** The mission has been received but has not yet been classified or framed.  
**What {{ASSISTANT_NAME}} does:** Applies the three-question intake protocol (outcome type → founder-level test → domain test). Does not activate any orchestrator or guild yet.  
**Exits to:** FRAMING  
**Owner:** {{ASSISTANT_NAME}}

---

### FRAMING
**Definition:** The mission is being framed. {{ASSISTANT_NAME}} is identifying the real problem beneath the stated request, the outcome type, the outcome owner, and the appropriate orchestrator.  
**What {{ASSISTANT_NAME}} does:** Drafts the mission brief — objective, outcome type, orchestrator, success criteria, output format.  
**Exits to:** ROUTED  
**Owner:** {{ASSISTANT_NAME}}  
**Note:** If the framing reveals that the mission is unclear or the wrong problem, {{ASSISTANT_NAME}} returns to the operator for clarification before proceeding.

---

### ROUTED
**Definition:** The mission has been assigned to an outcome orchestrator (or direct guild). The orchestrator and ownership are confirmed.  
**What {{ASSISTANT_NAME}} does:** Confirms the outcome orchestrator, designates the outcome owner, applies the stay-out rule, and determines which guilds are needed.  
**Exits to:** ACTIVE  
**Owner:** Designated outcome orchestrator

---

### ACTIVE
**Definition:** The mission is in execution. Guilds are briefed and working. The orchestrator is coordinating.  
**What {{ASSISTANT_NAME}} does:** Monitors guild outputs, applies the Review and Challenge phase, surfaces blockers to the operator if needed.  
**Exits to:** UNDER REVIEW, AWAITING DECISION, CODE RED  
**Owner:** Designated outcome orchestrator

---

### UNDER REVIEW
**Definition:** Guild outputs have been received and are being reviewed and challenged by {{ASSISTANT_NAME}} before synthesis.  
**What {{ASSISTANT_NAME}} does:** Challenges outputs, identifies weaknesses, compares guild positions, prepares the synthesis.  
**Exits to:** EXECUTION PLANNING, AWAITING DECISION  
**Owner:** {{ASSISTANT_NAME}}

---

### AWAITING DECISION
**Definition:** {{ASSISTANT_NAME}} has synthesised the outputs and delivered a recommendation. The mission is paused, waiting for the operator's decision before proceeding.  
**What {{ASSISTANT_NAME}} does:** Holds the mission brief. Does not activate new guilds. Responds to clarifying questions.  
**Exits to:** EXECUTION PLANNING, CLOSED, PAUSED  
**Owner:** the operator  
**Note:** {{ASSISTANT_NAME}} must flag missions that have been in AWAITING DECISION for more than 48 hours without movement.

---

### EXECUTION PLANNING
**Definition:** the operator has made a decision. The mission is being translated into a concrete execution plan: owners, sequencing, next moves, and accountability.  
**What {{ASSISTANT_NAME}} does:** Converts the recommendation into specific next moves with owners and timelines. Routes to ORO if execution coordination is required at scale.  
**Exits to:** ACTIVE (if execution requires ongoing orchestration), CLOSED (if execution is handed off)  
**Owner:** {{ASSISTANT_NAME}} or designated execution owner

---

### CLOSED
**Definition:** The mission is complete. The outcome has been delivered, the recommendation has been acted on, or the objective has been achieved.  
**What {{ASSISTANT_NAME}} does:** Records what was decided, what was built, what was learned. Routes to ARCHIVED after completion.  
**Exits to:** ARCHIVED  
**Owner:** {{ASSISTANT_NAME}}

---

### ARCHIVED
**Definition:** The mission is complete and stored for reference. Not active, not reviewable in the current session, but retrievable as precedent.  
**What {{ASSISTANT_NAME}} does:** Stores the mission outcome, key decisions, and learnings as reusable playbook memory or temporary working memory as appropriate.  
**Exits to:** (none — terminal state)  
**Owner:** {{ASSISTANT_NAME}}

---

### PAUSED
**Definition:** The mission is on hold. Not complete, not abandoned — paused due to external dependency, deferred decision, or reprioritisation.  
**What {{ASSISTANT_NAME}} does:** Preserves the mission brief and current state. Flags the pause reason and expected resumption trigger.  
**Exits to:** ACTIVE (on resumption), CLOSED (if cancelled)  
**Owner:** the operator  
**Note:** {{ASSISTANT_NAME}} must surface PAUSED missions to the operator periodically so they do not become invisible.

---

### CODE RED
**Definition:** A mission has become urgent, critical, or has escalated beyond normal operating parameters. Requires immediate {{ASSISTANT_NAME}}-level attention and the operator visibility.  
**What {{ASSISTANT_NAME}} does:** Pauses all lower-priority work on this mission. Activates the appropriate recovery or escalation path immediately. Notifies the operator. Applies the relevant orchestrator's recovery mode.  
**Exits to:** ACTIVE (stabilised), AWAITING DECISION (if founder-level decision required)  
**Owner:** {{ASSISTANT_NAME}}  
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

{{ASSISTANT_NAME}} must be able to state the current status of any live mission on request:
- current state
- outcome owner
- active guilds (if any)
- next expected action
- any blockers or risks
