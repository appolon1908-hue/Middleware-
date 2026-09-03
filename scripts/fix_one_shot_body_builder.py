#!/usr/bin/env python3
"""Write a syntactically checked, execution-ready copy of the one-shot builder."""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path("scripts/one_shot_build_webhook_body_reconciliation.py")
DESTINATION = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/body-reconciliation-builder.py")

text = SOURCE.read_text(encoding="utf-8")


def wrap_dedent_assignment(
    value: str,
    *,
    variable: str,
    next_marker: str,
    prefix: str,
) -> str:
    line_anchor = f"\n{variable} ="
    try:
        assignment_start = value.index(line_anchor) + 1
    except ValueError:
        if value.startswith(f"{variable} ="):
            assignment_start = 0
        else:
            raise SystemExit(f"cannot locate assignment for {variable}") from None
    marker_start = value.index(next_marker, assignment_start)
    segment = value[assignment_start:marker_start]
    call_start = segment.index("textwrap.dedent(")
    if "textwrap.indent(textwrap.dedent(" in segment:
        raise SystemExit(f"{variable} is already normalized")
    segment = segment[:call_start] + "textwrap.indent(" + segment[call_start:]
    close = segment.rfind(")")
    if close < 0 or segment[close + 1 :].strip():
        raise SystemExit(f"cannot locate the closing dedent call for {variable}")
    segment = segment[:close] + f"), {prefix!r})" + segment[close + 1 :]
    return value[:assignment_start] + segment + value[marker_start:]


transformations = (
    ("reconciliation_method", "if ingress.count(method_anchor) != 1:", "    "),
    (
        "enabled_anchor",
        "enabled_replacement = enabled_anchor + textwrap.dedent(",
        "        ",
    ),
    ("enabled_replacement", "if ingress.count(enabled_anchor) != 1:", "        "),
    (
        "replacement",
        "ingress = ingress[:start] + replacement + ingress[end:]",
        "        ",
    ),
    ("repository_method", "if repository.count(repository_anchor) != 1:", "    "),
    (
        "service_anchor",
        "service_replacement = service_anchor + textwrap.dedent(",
        "    ",
    ),
    (
        "service_replacement",
        "replace_once(\n    app_path,\n    service_anchor,",
        "    ",
    ),
    (
        "readiness_anchor",
        "readiness_replacement = textwrap.dedent(",
        "        ",
    ),
    (
        "readiness_replacement",
        "replace_once(\n    app_path,\n    readiness_anchor,",
        "        ",
    ),
)

for variable, marker, prefix in transformations:
    text = wrap_dedent_assignment(
        text,
        variable=variable,
        next_marker=marker,
        prefix=prefix,
    )

dependency_anchor = '''run(
    "python",
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--require-hashes",
    "-r",
    "requirements-test.txt",
)
'''
dependency_replacement = '''run(
    "python",
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--require-hashes",
    "-r",
    "requirements-test.txt",
)
run(
    "python",
    "-m",
    "pip",
    "install",
    "--disable-pip-version-check",
    "--require-hashes",
    "--target",
    "/tmp/connector-runtime-deps",
    "-r",
    "requirements-connector-runtime.txt",
)
'''
if text.count(dependency_anchor) != 1:
    raise SystemExit("hashed dependency installation anchor changed")
text = text.replace(dependency_anchor, dependency_replacement, 1)

pythonpath_anchor = '''test_env["PYTHONPATH"] = (
    "services/connector-runtime/src:"
    + test_env.get("PYTHONPATH", "")
)
'''
pythonpath_replacement = '''test_env["PYTHONPATH"] = (
    "/tmp/connector-runtime-deps:services/connector-runtime/src:"
    + test_env.get("PYTHONPATH", "")
)
'''
if text.count(pythonpath_anchor) != 1:
    raise SystemExit("connector test PYTHONPATH anchor changed")
text = text.replace(pythonpath_anchor, pythonpath_replacement, 1)

compile(text, str(DESTINATION), "exec")
DESTINATION.write_text(text, encoding="utf-8")
print(f"BODY_RECONCILIATION_BUILDER_NORMALIZED={DESTINATION}")
