# Step 3 Email Test Evidence

Date: 2026-08-29

## Passing Local Evidence

```text
python -m pytest tests/test_communications_email.py -q
4 passed, 5 warnings
```

```text
python -m pytest tests/test_communications_email.py tests/test_commands.py tests/test_control_plane_product_auth.py tests/test_sdk_events.py tests/test_models.py tests/test_security.py tests/test_replay.py tests/test_observability.py -q
48 passed, 16 warnings
```

```text
python -m pytest tests/test_communications_email.py tests/test_commands.py tests/test_control_plane_product_auth.py -q
15 passed, 16 warnings
```

## Full Suite Status

```text
python -m pytest -q
144 passed, 23 skipped, 1 failed
```

The single failure is `tests/test_staging_migration_evidence_collector.py::test_shell_syntax_is_valid` because `bash` is not installed in the Windows local environment. This test must be run in Linux CI before Step 3 is declared fully certified.
