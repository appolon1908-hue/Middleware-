#!/usr/bin/env python3
from pathlib import Path

workflow_path = Path('.github/workflows/production-runtime-certification.yml')
workflow = workflow_path.read_text(encoding='utf-8')
old = '''          ssh_options=(
            -i "$SSH_KEY_FILE"
            -p "$DEPLOY_PORT"
            -o BatchMode=yes
            -o IdentitiesOnly=yes
            -o StrictHostKeyChecking=yes
            -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE"
            -o ConnectTimeout=15
            -o ServerAliveInterval=15
            -o ServerAliveCountMax=3
          )
'''
new = old + '''          scp_options=(
            -i "$SSH_KEY_FILE"
            -P "$DEPLOY_PORT"
            -o BatchMode=yes
            -o IdentitiesOnly=yes
            -o StrictHostKeyChecking=yes
            -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE"
            -o ConnectTimeout=15
          )
'''
if workflow.count(old) != 1:
    raise SystemExit('SSH option block cardinality mismatch')
workflow = workflow.replace(old, new, 1)
replacements = {
    'scp "${ssh_options[@]}" "$BUNDLE_ARCHIVE" "$remote:$remote_bundle"':
        'scp "${scp_options[@]}" "$BUNDLE_ARCHIVE" "$remote:$remote_bundle"',
    'scp "${ssh_options[@]}" "$remote:$evidence_remote" "$evidence_local"':
        'scp "${scp_options[@]}" "$remote:$evidence_remote" "$evidence_local"',
}
for source, target in replacements.items():
    if workflow.count(source) != 1:
        raise SystemExit(f'SCP call cardinality mismatch: {source}')
    workflow = workflow.replace(source, target, 1)
workflow_path.write_text(workflow, encoding='utf-8')

validator_path = Path('scripts/validate_production_runtime_deployment.py')
validator = validator_path.read_text(encoding='utf-8')
old_validator = '''        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
        "codestra-middleware-deploy",
    ):
        require(item in workflow, f"workflow requirement missing: {item}")
    for item in ("ssh-keyscan", "appleboy/ssh-action", "StrictHostKeyChecking=no"):
        require(item not in workflow, f"workflow contains unsafe SSH behavior: {item}")
'''
new_validator = '''        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
        "ssh_options=(",
        "scp_options=(",
        '-p "$DEPLOY_PORT"',
        '-P "$DEPLOY_PORT"',
        'scp "${scp_options[@]}" "$BUNDLE_ARCHIVE"',
        'scp "${scp_options[@]}" "$remote:$evidence_remote"',
        "codestra-middleware-deploy",
    ):
        require(item in workflow, f"workflow requirement missing: {item}")
    for item in (
        "ssh-keyscan",
        "appleboy/ssh-action",
        "StrictHostKeyChecking=no",
        'scp "${ssh_options[@]}"',
    ):
        require(item not in workflow, f"workflow contains unsafe SSH behavior: {item}")
'''
if validator.count(old_validator) != 1:
    raise SystemExit('validator SSH block cardinality mismatch')
validator_path.write_text(validator.replace(old_validator, new_validator, 1), encoding='utf-8')
