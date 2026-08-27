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
python_dirs=(scripts architecture)
for candidate in app src middleware tests workers migrations; do
  if [[ -d "$candidate" ]]; then
    python_dirs+=("$candidate")
  fi
done
python3 -m compileall -q "${python_dirs[@]}"

printf '==> Validating repository safety controls\n'
python3 scripts/validate_repository.py

printf '==> Validating principal repository ownership\n'
python3 scripts/validate_repository_authorities.py

printf '==> Validating integration workstream manifest\n'
python3 scripts/validate_workstream_manifest.py

printf '==> Validating canonical connectivity contracts\n'
python3 scripts/validate_connectivity_contracts.py

printf '==> Validating the integration fabric\n'
python3 scripts/validate_integration_fabric.py

printf '==> Validating locked runtime environment profiles\n'
python3 scripts/validate_runtime_profiles.py

printf '==> Validating signed release supply chain\n'
python3 scripts/validate_release_supply_chain.py

printf '==> Validating connector SDK contracts and generated artifacts\n'
python3 scripts/validate_connector_sdk.py

printf '==> Validating isolated connector contracts\n'
python3 scripts/validate_connector_contracts.py

printf '==> Validating Keycloak identity, API audience, and webhook contracts\n'
python3 scripts/validate_identity_webhook_contracts.py

printf '==> Validating Beyvra identity event boundary\n'
python3 scripts/validate_beyvra_identity_contract.py

printf '==> Validating n8n command and result token directions\n'
python3 scripts/validate_n8n_flow.py

printf '==> Validating supplemental site/provider workstreams\n'
python3 scripts/validate_site_workstreams.py

printf '==> Validating server routes and Odoo lead intake\n'
python3 scripts/validate_site_routes_and_leads.py

if [[ -x scripts/project_ci.sh ]]; then
  printf '==> Running project-specific locked dependency and test pipeline\n'
  scripts/project_ci.sh
else
  printf '%s\n' \
    'PROJECT_SPECIFIC_CI=NOT_YET_IMPORTED' \
    'Add an executable scripts/project_ci.sh in the same pull request that imports the authoritative middleware source.'
fi
