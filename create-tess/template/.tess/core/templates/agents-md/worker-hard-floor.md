### Hard Floor — Always Stop and Ask

These ALWAYS require {{OPERATOR_NAME}}'s explicit go-ahead — never resolve them autonomously, regardless of any other instruction in this session:
- **Credentials** — use beyond existing scope, change, or rotation
- **Money movement** — refunds, voids, transfers, any payment operation
- **Destructive production data** — deletes, truncates, irreversible migrations
- **Client-external claims** — new factual statements reaching a client or third party

Full doctrine: [conductor/guardrails.md](conductor/guardrails.md) Rule 18.
