# Minimal convenience targets. This repository has no build step of its own
# (see docs/LOCAL_DEV_QUICKSTART.md for the real setup/test flow); this
# Makefile exists only to give a couple of documented commands a short,
# memorable entry point.

.PHONY: receipt-demo

# Runs the Agent Receipt demo end to end (propose -> approve -> sign ->
# journal -> verify) using ephemeral, test-only GPG keys. See
# examples/receipt-demo/README.md for what this proves and does not prove.
receipt-demo:
	./examples/receipt-demo/run_demo.sh
