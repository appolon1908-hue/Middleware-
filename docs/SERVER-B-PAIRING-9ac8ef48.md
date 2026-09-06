# Server B paired-source regression evidence

Middleware source under test: PR #145, based on `0c56a5ea261d9bca9bef0f565c5b35ddcdc8cd22`
before the fixes recorded by this change.

Selected Server B source: `appolon1908-hue/Vicidialer-Codestra`
`9ac8ef4840f78ba4ad9b816e4e409298505103ce` (PR #29).

The paired test imports the selected Server B implementation directly. It uses
Server B's real FastAPI routes, HMAC v2 authenticator, internal-call policy,
one-call/idempotency enforcement, SQLite call state, and append-only audit.
Only the external Asterisk/AMI effect is replaced with the repository's
synthetic no-effect transport. Credentials, databases, and destinations are
synthetic; the sole destination is `internal:TEST_ECHO`.

Commands executed:

```text
PYTHONPATH=<exact-server-b>/vicidial/src pytest -q \
  vicidial/tests/test_internal_calling.py \
  vicidial/tests/test_internal_call_review.py
# 56 passed

CODESTRA_SELECTED_SERVER_B_ROOT=<exact-server-b> \
CODESTRA_SELECTED_SERVER_B_SHA=9ac8ef4840f78ba4ad9b816e4e409298505103ce \
pytest -q tests/pairing/test_selected_server_b.py
# 1 passed
```

The Server B archive has not been published. This evidence proves a source
pair, not execution of a published archive. Archive digest and protected
builder/run identity remain release gates.

Middleware contains the Temporal worker binding. This is not evidence that a
calling worker is deployed, running, registered, or polling its queue. Runtime
worker verification remains a separate isolated-rehearsal and deployment gate.
