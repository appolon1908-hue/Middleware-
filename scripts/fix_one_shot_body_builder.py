#!/usr/bin/env python3
"""Write a syntactically checked, indentation-corrected copy of the one-shot builder."""

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
    assignment_start = value.index(f"{variable} =")
    marker_start = value.index(next_marker, assignment_start)
    segment = value[assignment_start:marker_start]
    call_start = segment.index("textwrap.dedent(")
    if "textwrap.indent(textwrap.dedent(" in segment:
        raise SystemExit(f"{variable} is already normalized")
    segment = (
        segment[:call_start]
        + "textwrap.indent("
        + segment[call_start:]
    )
    close = segment.rfind(")")
    if close < 0 or segment[close + 1 :].strip():
        raise SystemExit(f"cannot locate the closing dedent call for {variable}")
    segment = segment[:close] + f"), {prefix!r})" + segment[close + 1 :]
    return value[:assignment_start] + segment + value[marker_start:]


transformations = (
    (
        "reconciliation_method",
        "if ingress.count(method_anchor) != 1:",
        "    ",
    ),
    (
        "enabled_anchor",
        "enabled_replacement = enabled_anchor + textwrap.dedent(",
        "        ",
    ),
    (
        "enabled_replacement",
        "if ingress.count(enabled_anchor) != 1:",
        "        ",
    ),
    (
        "replacement",
        "ingress = ingress[:start] + replacement + ingress[end:]",
        "        ",
    ),
    (
        "repository_method",
        "if repository.count(repository_anchor) != 1:",
        "    ",
    ),
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

compile(text, str(DESTINATION), "exec")
DESTINATION.write_text(text, encoding="utf-8")
print(f"BODY_RECONCILIATION_BUILDER_NORMALIZED={DESTINATION}")
