# Sanitized import test results

- Python syntax compilation: PASS.
- Unit tests in isolated, network-disabled container: PASS — 207 passed, 3 skipped.
- Runtime Docker image build: PASS.
- Captured Dockerfile test target: FAIL — it pins Alpine OpenSSL `3.5.7-r0`, while the pinned base resolves with `3.5.8-r0`.
- Temporary evidence-only test Dockerfile using the available OpenSSL patch: build PASS and unit tests PASS. It is not part of this repository.
- Docker Compose config for `deploy/compose.runtime.yaml`, with sanitized example environment and no interpolation: PASS.
- Ruff: FAIL — 20 existing source/test findings.
- Mypy: FAIL — 9 existing errors in 5 source files.
- `git diff --check`: PASS.
- Gitleaks and manual secret patterns: PASS.
- Integration/provider-effect tests were not run because no isolated PostgreSQL/Redis/provider environment was supplied.
