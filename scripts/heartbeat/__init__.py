"""Memory-continuity heartbeat runner (L2).

See docs/memory-continuity.md for the architecture and scripts/heartbeat/README.md
for operational detail. Entry point is scripts/heartbeat/run.py, normally invoked
by scripts/heartbeat.sh from an external scheduler (see scripts/launchd/ for a
staged, NOT-loaded macOS launchd example — this ships inert, off by default).
"""
