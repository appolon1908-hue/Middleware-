from __future__ import annotations

import hashlib
from pathlib import Path


VALIDATOR_PATH = Path(".codestra/validate-production-orchestrator-contract.py")
SCRIPT_PATH = Path("scripts/staging-intake-e2e-no-effect.py")


OLD = '''def require_mutating_jobs_disabled(workflow: str, path: str) -> None:
    mutating_jobs = 0
    script_aliases = workflow_script_aliases(workflow, path)
    for job_name, job in workflow_jobs(workflow, path).items():
        if job_reusable_workflow_mutation(job, path) or any(
            step_has_runtime_mutation(job, step, path, script_aliases)
            or contains_runtime_action(step)
            for step in workflow_steps(job, path)
        ):
            mutating_jobs += 1
            require(
                "RUNTIME_MUTATION_DISABLED=true" in job.raw,
                f"mutating job lacks disable marker: {path}:{job_name}",
            )
            require(
                job_condition(job) == "${{ false }}",
                f"mutating job is not unconditionally disabled: {path}:{job_name}",
            )
    require(mutating_jobs > 0, f"native mutation classification drift: {path}")
'''


TEMPLATE = '''STAGING_NO_EFFECT_WORKFLOW_PATH = ".github/workflows/staging-intake-e2e-no-effect.yml"
STAGING_NO_EFFECT_JOB_NAME = "certify-no-effect"
STAGING_NO_EFFECT_SCRIPT_SHA256 = "__SCRIPT_SHA__"
STAGING_NO_EFFECT_FALSE_FLAGS = (
    "LIVE_WRITES",
    "ODOO_WRITE",
    "N8N_DELIVERY_ENABLED",
    "LIVE_SMS_DELIVERY",
    "LIVE_EMAIL_DELIVERY",
    "LIVE_PSTN_DIALING",
)


def require_staging_no_effect_mutation_authority(
    workflow: str,
    path: str,
    job_name: str,
    job: WorkflowJob,
    script_aliases: dict[str, str],
) -> None:
    require(
        path == STAGING_NO_EFFECT_WORKFLOW_PATH
        and job_name == STAGING_NO_EFFECT_JOB_NAME,
        f"unapproved live mutation exception: {path}:{job_name}",
    )
    condition = job_condition(job)
    require(isinstance(condition, str), "staging no-effect job condition is missing")
    for fragment in (
        "github.event_name == 'workflow_dispatch'",
        "github.repository == 'appolon1908-hue/Middleware-'",
        "github.actor == 'appolon1908-hue'",
        "github.ref == 'refs/heads/main'",
        "inputs.confirm_no_effect == true",
    ):
        require(fragment in condition, f"staging no-effect authority drift: {fragment}")
    require(
        job.data.get("environment") == "intake-staging-certification",
        "staging no-effect protected environment drift",
    )

    try:
        document = yaml.load(workflow, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ContractError("staging no-effect workflow is not valid YAML") from exc
    require(isinstance(document, dict), "staging no-effect workflow root is invalid")
    root_env = document.get("env")
    require(isinstance(root_env, dict), "staging no-effect root env is missing")
    for flag in STAGING_NO_EFFECT_FALSE_FLAGS:
        require(
            root_env.get(flag) == "false",
            f"staging effect flag enabled or missing: {flag}",
        )

    script_path = ROOT / "scripts/staging-intake-e2e-no-effect.py"
    require(
        script_path.is_file() and not script_path.is_symlink(),
        "staging certification script is missing or unsafe",
    )
    require(
        hashlib.sha256(script_path.read_bytes()).hexdigest()
        == STAGING_NO_EFFECT_SCRIPT_SHA256,
        "staging certification script hash drift",
    )

    mutating_steps = [
        step
        for step in workflow_steps(job, path)
        if step_has_runtime_mutation(job, step, path, script_aliases)
        or contains_runtime_action(step)
    ]
    require(
        len(mutating_steps) == 1,
        f"staging no-effect job must have exactly one mutating step: {path}:{job_name}",
    )
    step = mutating_steps[0]
    run = step.get("run")
    require(
        isinstance(run, str),
        "staging no-effect mutation must be an explicit run step",
    )
    run_lines = [
        line.strip().rstrip(chr(92)).strip()
        for line in run.splitlines()
        if line.strip()
    ]
    require(
        run_lines
        == [
            "set -Eeuo pipefail",
            "python3 scripts/staging-intake-e2e-no-effect.py",
            '--base-url "$BASE_URL"',
            '--tenant "$TENANT_ID"',
            '--expected-source-sha "$EXPECTED_SOURCE_SHA"',
        ],
        "staging no-effect mutating command drift",
    )
    step_env = step.get("env")
    require(isinstance(step_env, dict), "staging no-effect mutation env is missing")
    require(
        step_env.get("STAGING_SDK_INTAKE_TOKEN")
        == "${{ secrets.STAGING_SDK_INTAKE_TOKEN }}"
        and step_env.get("STAGING_RUNTIME_SAFETY_TOKEN")
        == "${{ secrets.STAGING_RUNTIME_SAFETY_TOKEN }}"
        and step_env.get("STAGING_INTAKE_APPROVED_HOST")
        == "${{ vars.STAGING_INTAKE_APPROVED_HOST }}"
        and step_env.get("BASE_URL") == "${{ inputs.base_url }}"
        and step_env.get("TENANT_ID") == "${{ inputs.tenant_id }}"
        and step_env.get("EXPECTED_SOURCE_SHA") == "${{ github.sha }}",
        "staging no-effect protected input binding drift",
    )
    for boundary in (
        "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO",
        "PRODUCTION_ODOO_WRITES_AUTHORIZED=NO",
        "PRODUCTION_PSTN_AUTHORIZED=NO",
        "EXTERNAL_EFFECTS_AUTHORIZED=NONE",
    ):
        require(
            boundary in workflow,
            f"staging non-authorization boundary drift: {boundary}",
        )


def require_mutating_jobs_disabled(workflow: str, path: str) -> None:
    mutating_jobs = 0
    script_aliases = workflow_script_aliases(workflow, path)
    for job_name, job in workflow_jobs(workflow, path).items():
        if job_reusable_workflow_mutation(job, path) or any(
            step_has_runtime_mutation(job, step, path, script_aliases)
            or contains_runtime_action(step)
            for step in workflow_steps(job, path)
        ):
            mutating_jobs += 1
            if (
                path == STAGING_NO_EFFECT_WORKFLOW_PATH
                and job_name == STAGING_NO_EFFECT_JOB_NAME
            ):
                require_staging_no_effect_mutation_authority(
                    workflow,
                    path,
                    job_name,
                    job,
                    script_aliases,
                )
                continue
            require(
                "RUNTIME_MUTATION_DISABLED=true" in job.raw,
                f"mutating job lacks disable marker: {path}:{job_name}",
            )
            require(
                job_condition(job) == "${{ false }}",
                f"mutating job is not unconditionally disabled: {path}:{job_name}",
            )
    require(mutating_jobs > 0, f"native mutation classification drift: {path}")
'''


def main() -> None:
    validator = VALIDATOR_PATH.read_text(encoding="utf-8")
    if validator.count(OLD) != 1:
        raise SystemExit("expected exactly one mutating-job authority function")
    script_sha = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()
    VALIDATOR_PATH.write_text(
        validator.replace(OLD, TEMPLATE.replace("__SCRIPT_SHA__", script_sha), 1),
        encoding="utf-8",
    )
    print(f"STAGING_NO_EFFECT_SCRIPT_SHA256={script_sha}")


if __name__ == "__main__":
    main()
