#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CATALOG="${MIDDLEWARE_AUTHORITY_CATALOG:-${ROOT_DIR}/config/middleware-authority-convergence.v1.json}"
STATE_ROOT="${MIDDLEWARE_AUTHORITY_BACKUP_ROOT:-/var/lib/codestra-middleware/authority-backups}"
REGISTRY_AUTH_FILE="${REGISTRY_AUTH_FILE:-/root/.config/containers/auth.json}"
EXPECTED_HOST="65.109.65.169"
MODE="${1:-status}"

fail() {
  printf 'MIDDLEWARE_LEGACY_BACKUP=FAIL\n' >&2
  printf 'FAILURE_REASON=%s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing_command_$1"
}

[[ -f "$CATALOG" && ! -L "$CATALOG" ]] || fail "catalog_missing_or_symlink"
require_command python3
require_command docker

catalog_host="$(python3 - "$CATALOG" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
print(value["serverA"]["host"])
PY
)"
[[ "$catalog_host" == "$EXPECTED_HOST" ]] || fail "catalog_host_mismatch"

case "$MODE" in
  status|archive|mirror|all) ;;
  *) fail "usage_status_archive_mirror_or_all" ;;
esac

catalog_rows() {
  python3 - "$CATALOG" <<'PY'
from __future__ import annotations
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
for family in value["runtimeImageFamilies"]:
    backup = family["backup"]
    if backup["method"] != "server-a-archive-and-config-digest-mirror":
        continue
    fields = [
        family["id"],
        family["digest"],
        family["runtimeReference"],
        backup["destinationTag"],
        ",".join(family["workloads"]),
    ]
    if any("\t" in str(field) or "\n" in str(field) for field in fields):
        raise SystemExit("catalog contains unsafe tab/newline data")
    print("\t".join(fields))
PY
}

verify_image_and_workloads() {
  local family_id="$1" expected_id="$2" runtime_reference="$3" workload_csv="$4"
  local actual_image_id

  actual_image_id="$(docker image inspect --format '{{.Id}}' "$expected_id" 2>/dev/null)" || {
    printf 'family=%s status=MISSING_IMAGE expected=%s reference=%s\n' \
      "$family_id" "$expected_id" "$runtime_reference" >&2
    return 1
  }
  [[ "$actual_image_id" == "$expected_id" ]] || {
    printf 'family=%s status=IMAGE_ID_MISMATCH expected=%s actual=%s\n' \
      "$family_id" "$expected_id" "$actual_image_id" >&2
    return 1
  }

  local seen=0 workload actual
  IFS=',' read -r -a workloads <<<"$workload_csv"
  for workload in "${workloads[@]}"; do
    if ! docker container inspect "$workload" >/dev/null 2>&1; then
      printf 'family=%s workload=%s status=NOT_PRESENT\n' "$family_id" "$workload"
      continue
    fi
    seen=$((seen + 1))
    actual="$(docker container inspect --format '{{.Image}}' "$workload")"
    if [[ "$actual" != "$expected_id" ]]; then
      printf 'family=%s workload=%s status=RUNTIME_IMAGE_ID_MISMATCH expected=%s actual=%s\n' \
        "$family_id" "$workload" "$expected_id" "$actual" >&2
      return 1
    fi
    printf 'family=%s workload=%s status=MATCH image_id=%s\n' \
      "$family_id" "$workload" "$actual"
  done
  printf 'family=%s image_status=MATCH observed_workloads=%s expected_workloads=%s\n' \
    "$family_id" "$seen" "${#workloads[@]}"
}

archive_family() {
  local family_id="$1" expected_id="$2" runtime_reference="$3" destination_tag="$4" workload_csv="$5"
  local stamp family_dir archive archive_digest
  stamp="$(date -u +'%Y%m%dT%H%M%SZ')"
  family_dir="${STATE_ROOT}/${stamp}/${family_id}"
  archive="${family_dir}/image.tar.gz"
  install -d -m 0700 "$family_dir"

  verify_image_and_workloads "$family_id" "$expected_id" "$runtime_reference" "$workload_csv" \
    >"${family_dir}/runtime-identity.txt"

  docker image inspect --format \
    '{"id":{{json .Id}},"repo_tags":{{json .RepoTags}},"repo_digests":{{json .RepoDigests}},"created":{{json .Created}},"os":{{json .Os}},"architecture":{{json .Architecture}}}' \
    "$expected_id" >"${family_dir}/image-metadata.json"

  docker image save "$expected_id" | gzip -n -9 >"$archive"
  gzip -t "$archive"
  archive_digest="sha256:$(sha256sum "$archive" | awk '{print $1}')"

  python3 - "$family_dir/backup-evidence.json" "$family_id" "$expected_id" \
    "$runtime_reference" "$destination_tag" "$archive" "$archive_digest" "$workload_csv" <<'PY'
from __future__ import annotations
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

(
    output,
    family_id,
    image_id,
    runtime_reference,
    destination_tag,
    archive,
    archive_digest,
    workloads,
) = sys.argv[1:]
value = {
    "schema_version": 1,
    "captured_at": datetime.now(UTC).isoformat(),
    "family_id": family_id,
    "docker_image_id": image_id,
    "runtime_reference": runtime_reference,
    "workloads": workloads.split(","),
    "archive": archive,
    "archive_sha256": archive_digest,
    "planned_appolon_backup_tag": destination_tag,
    "container_restart_performed": False,
    "compose_changed": False,
    "traffic_changed": False,
    "verification": "PASS",
}
Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  printf 'family=%s archive=%s archive_digest=%s status=PASS\n' \
    "$family_id" "$archive" "$archive_digest"
}

mirror_family() {
  local family_id="$1" expected_id="$2" runtime_reference="$3" destination_tag="$4" workload_csv="$5"
  require_command skopeo
  [[ -f "$REGISTRY_AUTH_FILE" && ! -L "$REGISTRY_AUTH_FILE" ]] || fail "registry_auth_file_missing_or_symlink"

  verify_image_and_workloads "$family_id" "$expected_id" "$runtime_reference" "$workload_csv" >/dev/null

  local short temp_ref raw_manifest destination_digest evidence_dir
  short="${expected_id#sha256:}"
  short="${short:0:12}"
  temp_ref="localhost/codestra-middleware-legacy:${family_id}-${short}"
  evidence_dir="${STATE_ROOT}/registry-mirror/$(date -u +'%Y%m%dT%H%M%SZ')/${family_id}"
  install -d -m 0700 "$evidence_dir"

  cleanup_temp_tag() {
    docker image rm "$temp_ref" >/dev/null 2>&1 || true
  }
  trap cleanup_temp_tag RETURN

  docker image tag "$expected_id" "$temp_ref"
  skopeo copy \
    --all \
    --dest-authfile "$REGISTRY_AUTH_FILE" \
    "docker-daemon:${temp_ref}" \
    "docker://${destination_tag}"

  skopeo inspect \
    --authfile "$REGISTRY_AUTH_FILE" \
    --raw "docker://${destination_tag}" >"${evidence_dir}/destination-manifest.json"
  destination_digest="$(
    skopeo inspect \
      --authfile "$REGISTRY_AUTH_FILE" \
      --format '{{.Digest}}' \
      "docker://${destination_tag}"
  )"

  python3 - "${evidence_dir}/destination-manifest.json" "$expected_id" <<'PY'
from __future__ import annotations
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
expected = sys.argv[2]
actual = manifest.get("config", {}).get("digest")
if actual != expected:
    raise SystemExit(
        f"destination OCI config digest mismatch: expected {expected}, got {actual!r}"
    )
PY

  python3 - "$evidence_dir/mirror-evidence.json" "$family_id" "$expected_id" \
    "$runtime_reference" "$destination_tag" "$destination_digest" <<'PY'
from __future__ import annotations
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

output, family_id, image_id, source, destination, destination_digest = sys.argv[1:]
value = {
    "schema_version": 1,
    "mirrored_at": datetime.now(UTC).isoformat(),
    "family_id": family_id,
    "source_runtime_reference": source,
    "source_docker_image_id": image_id,
    "destination_tag": destination,
    "destination_manifest_digest": destination_digest,
    "destination_config_digest": image_id,
    "runtime_mutated": False,
    "container_restart_performed": False,
    "verification": "PASS",
}
Path(output).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  cleanup_temp_tag
  trap - RETURN
  printf 'family=%s destination=%s destination_digest=%s config_digest=%s status=PASS\n' \
    "$family_id" "$destination_tag" "$destination_digest" "$expected_id"
}

failures=0
while IFS=$'\t' read -r family_id expected_id runtime_reference destination_tag workload_csv; do
  case "$MODE" in
    status)
      verify_image_and_workloads "$family_id" "$expected_id" "$runtime_reference" "$workload_csv" || failures=$((failures + 1))
      ;;
    archive)
      archive_family "$family_id" "$expected_id" "$runtime_reference" "$destination_tag" "$workload_csv" || failures=$((failures + 1))
      ;;
    mirror)
      mirror_family "$family_id" "$expected_id" "$runtime_reference" "$destination_tag" "$workload_csv" || failures=$((failures + 1))
      ;;
    all)
      verify_image_and_workloads "$family_id" "$expected_id" "$runtime_reference" "$workload_csv" || { failures=$((failures + 1)); continue; }
      archive_family "$family_id" "$expected_id" "$runtime_reference" "$destination_tag" "$workload_csv" || { failures=$((failures + 1)); continue; }
      mirror_family "$family_id" "$expected_id" "$runtime_reference" "$destination_tag" "$workload_csv" || failures=$((failures + 1))
      ;;
  esac
done < <(catalog_rows)

if [[ "$failures" -ne 0 ]]; then
  fail "${failures}_image_families_failed"
fi

printf 'MIDDLEWARE_LEGACY_BACKUP=PASS\n'
printf 'MODE=%s\n' "$MODE"
printf 'SERVER_A_RUNTIME_MUTATED=NO\n'
printf 'CONTAINERS_RESTARTED=0\n'
printf 'CODESTRA_BACKUP_RETAINED=true\n'
