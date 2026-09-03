#!/usr/bin/env python3
from pathlib import Path

workflow_path = Path('.github/workflows/production-runtime-certification.yml')
workflow = workflow_path.read_text(encoding='utf-8')
source = '    environment: production\n'
target = '    environment: production-runtime-certification\n'
if workflow.count(source) != 1:
    raise SystemExit('production environment reference cardinality mismatch')
workflow_path.write_text(workflow.replace(source, target, 1), encoding='utf-8')

validator_path = Path('scripts/validate_production_runtime_deployment.py')
validator = validator_path.read_text(encoding='utf-8')
source = '        "environment: production",\n'
target = '        "environment: production-runtime-certification",\n'
if validator.count(source) != 1:
    raise SystemExit('validator environment reference cardinality mismatch')
validator_path.write_text(validator.replace(source, target, 1), encoding='utf-8')
