#!/usr/bin/env python3
from pathlib import Path

validator_path = Path('scripts/validate_production_runtime_deployment.py')
validator = validator_path.read_text(encoding='utf-8')
wrong = 'ROOT / ".github/workflows/middleware-runtime-certification.yml"'
right = 'ROOT / ".github/workflows/production-runtime-certification.yml"'
if validator.count(wrong) != 1:
    raise SystemExit(f'workflow path mismatch count={validator.count(wrong)}')
validator = validator.replace(wrong, right, 1)
if '"environment: middleware-runtime-certification"' not in validator:
    raise SystemExit('validator does not require the dedicated environment')
validator_path.write_text(validator, encoding='utf-8')

workflow_path = Path('.github/workflows/production-runtime-certification.yml')
workflow = workflow_path.read_text(encoding='utf-8')
if workflow.count('environment: middleware-runtime-certification') != 1:
    raise SystemExit('runtime certification environment cardinality mismatch')
if 'environment: production\n' in workflow:
    raise SystemExit('reserved production environment remains referenced')
