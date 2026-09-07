import json
from pathlib import Path

from scripts import validate_repository


def _write_migration(path: Path, revision: str, down_revision: str | None) -> None:
    path.write_text(
        f"revision = {revision!r}\ndown_revision = {down_revision!r}\n",
        encoding="utf-8",
    )


def _repository(tmp_path: Path, required_head: str = "0056_required") -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "migrations/versions").mkdir(parents=True)
    (tmp_path / "config/middleware-forward-release-authority.v1.json").write_text(
        json.dumps({"artifactAuthority": {"requiredSchemaHead": required_head}}),
        encoding="utf-8",
    )
    _write_migration(tmp_path / "migrations/versions/0055.py", "0055_parent", None)
    _write_migration(
        tmp_path / "migrations/versions/0056.py", required_head, "0055_parent"
    )
    return tmp_path


def test_current_repository_matches_production_migration_authority() -> None:
    errors: list[str] = []
    validate_repository.validate_production_migration_head(errors)
    assert errors == []


def test_rejects_a_new_head_without_platform_tuple_review(
    tmp_path: Path, monkeypatch
) -> None:
    root = _repository(tmp_path)
    _write_migration(
        root / "migrations/versions/0057.py", "0057_unapproved", "0056_required"
    )
    monkeypatch.setattr(validate_repository, "ROOT", root)

    errors: list[str] = []
    validate_repository.validate_production_migration_head(errors)

    assert errors == [
        "production migration head drift: authority requires '0056_required', "
        "repository heads are ['0057_unapproved']; update the platform tuple through "
        "separate protected review before adding a head"
    ]


def test_rejects_multiple_heads(tmp_path: Path, monkeypatch) -> None:
    root = _repository(tmp_path)
    _write_migration(root / "migrations/versions/branch.py", "branch_head", "0055_parent")
    monkeypatch.setattr(validate_repository, "ROOT", root)

    errors: list[str] = []
    validate_repository.validate_production_migration_head(errors)

    assert "repository heads are ['0056_required', 'branch_head']" in errors[0]
