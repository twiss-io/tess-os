---
description: Activate Product and Delivery Orchestrator routing — optimise for shipped value, delivery integrity, and post-launch learning.
---

# /product-mode

Route the active (or next) mission through the **Product and Delivery Orchestrator** (`product-delivery-orchestrator`). See [conductor/outcome-orchestrators/README.md](../../conductor/outcome-orchestrators/README.md).

**Optimise for:** shipped value, delivery integrity, post-launch learning. Ensure the problem is validated before build begins (research-before-build gate, [conductor/doctrine.md](../../conductor/doctrine.md)). Any prod-touching/client-facing output must clear its mandatory verifier ([conductor/verification-routing.md](../../conductor/verification-routing.md)).

**Applies to:** discovery, product decisions, build sequencing, release readiness, post-launch review.

Relevant playbook: [conductor/playbooks/product-build-mission.md](../../conductor/playbooks/product-build-mission.md). For audit-driven multi-PR fix waves, see [conductor/playbooks/l99-merge-discipline.md](../../conductor/playbooks/l99-merge-discipline.md).
