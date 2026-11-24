# Alice Gluttony v0.71 — Action Ledger & Verification

v0.71 adds a persistent action lifecycle so Alice never treats an intended or merely executed action as verified success.

## Lifecycle

`planned -> approved -> executed -> verified`

Failures and rollbacks are recorded explicitly. Consequential actions still require explicit approval.

The action engine is provider-neutral: real executors and verifiers are injected by the integration layer. No external delivery or side effect is claimed without an executor result and verification.

## Tests

Run from the repository root:

```bash
pytest -q
```
