# Codex Mission — Middleware Governed PSTN Caller

Date: 2026-09-10

## Server
Execute the caller-side portion on `65.109.65.169` only.
Target VICIdial/Asterisk server: `65.21.67.207` through the existing private/mTLS edge.

## Objective
Submit exactly one authenticated request to the governed VICIdial adapter endpoint `POST /v1/calls/originate` for destination `+18496582053`, using the repository-defined HMAC/auth contract and the currently approved external-call policy.

## Required preconditions
- The VICIdial adapter on `65.21.67.207` must be healthy and running the canonical protected-main release.
- `/ready` on the adapter must report the governed one-call production profile and `production_dialing=true`.
- DIDWW route certification must have passed on `65.21.67.207`.
- Durable external-call state must show the authorization has not already been consumed.
- mTLS from `65.109.65.169` to the private edge must validate successfully.

## Request contract
Use a fresh `operation_id` and set the `Idempotency-Key` to the same value. Use a fresh nonce and timestamp, exact identity/scope required for `telephony:external-call`, exact authorized campaign and authorization reference, destination `+18496582053`, `purpose=controlled_test`, and `recording_requested=false`.

Generate the body first, hash/sign the exact bytes required by the HMAC v2 canonicalization contract, then transmit those exact bytes. Do not log or print HMAC keys, client private keys, AMI credentials, or other secrets.

## Retry policy
Submit once only. A transport timeout, 5xx after dispatch, `dispatch_unknown`, `submitted_unknown`, or any ambiguous result is a STOP condition. Reconcile adapter durable state and Asterisk events before any further action. Never blindly resend the same or a new operation ID.

## Evidence
Record only non-secret evidence: UTC timestamp, operation ID, correlation ID, target host, endpoint, HTTP status, response state, adapter release SHA, and reconciliation outcome. Redact authorization material.

## Post-attempt
Confirm with the VICIdial host operator that production dialing is immediately disabled after the attempt and that the adapter returns to its normal fail-closed profile. Do not leave a broad calling capability enabled.

## Repository reconciliation
If the live caller contract differs from this repository, fix the source/tests/docs first, run CI, and merge through normal protected-branch policy. No live-only middleware workaround may remain canonical.
