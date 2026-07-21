"""ApprovalGate adapters. `local_identity.py` ships the DEFAULT, local,
authenticated adapter. A future Telegram-button / web / CLI-with-real-auth
adapter is a drop-in addition here — see `orchestrator/approval_gate.py`'s
`ApprovalGate` docstring for the contract it needs to satisfy. Nothing
under this package is imported eagerly except `local_identity` (wired into
`orchestrator/__init__.py`'s public API as the shipped default).
"""
