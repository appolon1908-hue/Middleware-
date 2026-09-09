from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "staging-intake-e2e-no-effect.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_staging_no_effect_dispatch_is_explicitly_owner_main_gated() -> None:
    text = _workflow()

    assert "if: ${{ false }}" not in text
    assert "github.repository == 'appolon1908-hue/Middleware-'" in text
    assert "github.actor == 'appolon1908-hue'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "inputs.confirm_no_effect == true" in text
    assert "environment: intake-staging-certification" in text
    assert "type: boolean" in text
    assert "default: false" in text


def test_staging_no_effect_dispatch_keeps_effects_disabled() -> None:
    text = _workflow()

    for key in (
        "LIVE_WRITES",
        "ODOO_WRITE",
        "N8N_DELIVERY_ENABLED",
        "LIVE_SMS_DELIVERY",
        "LIVE_EMAIL_DELIVERY",
        "LIVE_PSTN_DIALING",
    ):
        assert f'{key}: "false"' in text
        assert f'{key}: "true"' not in text

    assert "PRODUCTION_DEPLOYMENT_AUTHORIZED=NO" in text
    assert "PRODUCTION_ODOO_WRITES_AUTHORIZED=NO" in text
    assert "PRODUCTION_PSTN_AUTHORIZED=NO" in text
    assert "EXTERNAL_EFFECTS_AUTHORIZED=NONE" in text


def test_staging_no_effect_dispatch_requires_protected_credentials_and_host() -> None:
    text = _workflow()

    assert "vars.STAGING_INTAKE_APPROVED_HOST" in text
    assert "secrets.STAGING_SDK_INTAKE_TOKEN" in text
    assert "secrets.STAGING_RUNTIME_SAFETY_TOKEN" in text
    assert "--base-url \"$BASE_URL\"" in text
    assert "--tenant \"$TENANT_ID\"" in text
    assert "--expected-source-sha \"$EXPECTED_SOURCE_SHA\"" in text
