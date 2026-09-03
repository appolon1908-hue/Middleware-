#!/usr/bin/env python3
from pathlib import Path

paths = (
    Path('.github/workflows/production-runtime-certification.yml'),
    Path('scripts/validate_production_runtime_deployment.py'),
    Path('docs/production/PRODUCTION-RUNTIME-CERTIFICATION.md'),
)
old = 'production-runtime-certification'
new = 'middleware-runtime-certification'
replacements = 0
for path in paths:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count:
        path.write_text(text.replace(old, new), encoding='utf-8')
        replacements += count
if replacements < 2:
    raise SystemExit(f'expected at least two environment-name replacements, observed {replacements}')
