#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

printf '==> Checking Git whitespace errors\n'
git diff --check

printf '==> Checking shell syntax\n'
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find scripts -type f -name '*.sh' -print0 | sort -z)

printf '==> Compiling Python source\n'
python_dirs=(scripts)
for candidate in app src middleware tests workers migrations; do
  if [[ -d "$candidate" ]]; then
    python_dirs+=("$candidate")
  fi
done
python3 -m compileall -q "${python_dirs[@]}"

printf '==> Validating repository safety controls\n'
python3 scripts/validate_repository.py

printf '==> Validating integration workstream manifest\n'
python3 scripts/validate_workstream_manifest.py

printf '==> Validating connectivity and communication contracts\n'
python3 scripts/validate_connectivity_contracts.py

if [[ -x scripts/project_ci.sh ]]; then
  printf '==> Running project-specific locked dependency and test pipeline\n'
  scripts/project_ci.sh
else
  printf '%s\n' \
    'PROJECT_SPECIFIC_CI=NOT_YET_IMPORTED' \
    'Add an executable scripts/project_ci.sh in the same pull request that imports the live middleware source.'
fi
