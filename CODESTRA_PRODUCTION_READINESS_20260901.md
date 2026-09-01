# Codestra Production Readiness Gate — Middleware

Status: NOT PRODUCTION CERTIFIED

Governed by `Infustruction-repo/CODESTRA_PRODUCTION_READINESS_WAVE_20260901.md`.

Production requirements: canonical runtime/source authority; project-specific CI; exact-head tests; Critical=0; High=0; no direct provider bypass; operation-specific callers/scopes/audiences; durable transactional outbox for external effects; idempotency and unknown-outcome reconciliation; provider safety gates; OpenBao file-based secret delivery; observability; backup/restore where stateful; rollback; staging E2E; runtime read-back; production read-only canary.

Keep email/SMS/dialing/social/advertising/AI/provider writes disabled until separately certified. Do not modify SSH access or bypass protected branches.
