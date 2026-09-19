# Python 3.13 image security corrections

The middleware runtime, worker, connector-runtime and test images are built from
the digest-pinned official `python:3.13.15-*-bookworm` images (`Dockerfile.runtime`).
Corrections that exist upstream but are not yet in a released 3.13.x are applied
to the installed standard library in the `patched-final-base` and `test` stages by
a digest-pinned applier — never by GNU `patch`, and never in a way that survives a
base-image change unnoticed.

| Finding | Component | Upstream fix | Image resolution | Scanner |
| --- | --- | --- | --- | --- |
| CVE-2026-82049 | `tarfile` `data`/`tar` extraction filters follow a hard link to a symlink outside the destination (CVSS 8.4, High) | python/cpython `b8f23e307097552eaea2604383a12ab280520d0d` on branch `3.13` (2026-09-10); not in 3.13.15 (tagged 2026-08-05) | `security/python313/apply_cve_2026_82049.py` rewrites `/usr/local/lib/python3.13/tarfile.py` from sha256 `9fedddf7…a17d01` (v3.13.15 bytes) to `7ad04a66…77929`; provenance in `CVE-2026-82049-tarfile-hardlink-symlink.patch` | `.grype.yaml` ignores `python@3.13.15` for this CVE only |

## Exposure

No module shipped in the runtime images (`app/`, `workers/`, `connectors/`, the
three `scripts/*.py` copied into the image, `services/connector-runtime`) imports
`tarfile`; the only importers in the repository are
`scripts/validate_production_runtime_deployment.py` and its test, which are not
part of the runtime image. The correction is applied as defence in depth so the
interpreter the images ship is not vulnerable regardless of future code.

## Expiry

`apply_cve_2026_82049.py` fails the image build unless the target is byte-identical
to the 3.13.15 `tarfile.py`. When `Dockerfile.runtime` moves to a base that already
contains the fix (any 3.13.16+ or 3.14+), the build stops until the `COPY`/`RUN`
lines in both stages, the `.grype.yaml` entry and this row are removed together.
`tests/test_container_vulnerability_dispositions.py` keeps the three in step.

## Verification

```text
docker run --rm python:3.13.15-slim-bookworm@sha256:00faa2de… sha256sum /usr/local/lib/python3.13/tarfile.py
  9fedddf7e814c226cb7e1ac0aa603092eda40047367ec00ad740a81484a17d01
docker build --file Dockerfile.runtime --target runtime … ; docker run --rm --entrypoint sha256sum <image> /usr/local/lib/python3.13/tarfile.py
  7ad04a66bb92373bd6d2552a2f01fce8a4ca95463ebf661612fd574465977929
```
