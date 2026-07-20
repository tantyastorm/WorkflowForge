"""Architecture import-boundary tests."""

from pathlib import Path

from scripts.validate_architecture import (
    format_violations,
    validate_repository,
)


def test_current_repository_import_boundaries_pass() -> None:
    violations = validate_repository(Path.cwd())

    assert violations == []


def test_allowed_internal_dependencies_pass(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/application/src/workflowforge_application/use_case.py",
        "import workflowforge_domain\nfrom workflowforge_contracts.health import SystemHealth\n",
    )
    write_package_file(
        tmp_path,
        "packages/infrastructure/src/workflowforge_infrastructure/adapter.py",
        "import workflowforge_domain\nimport workflowforge_contracts.health\n"
        "from workflowforge_application.health.ports import DependencyHealthCheck\n",
    )
    write_package_file(
        tmp_path,
        "apps/api/src/workflowforge_api/composition.py",
        "import workflowforge_application\nimport workflowforge_infrastructure\n",
    )

    violations = validate_repository(tmp_path)

    assert violations == []


def test_forbidden_internal_dependencies_fail(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/model.py",
        "import workflowforge_application\n",
    )
    write_package_file(
        tmp_path,
        "packages/application/src/workflowforge_application/use_case.py",
        "import workflowforge_infrastructure\n",
    )
    write_package_file(
        tmp_path,
        "packages/contracts/src/workflowforge_contracts/schema.py",
        "import workflowforge_infrastructure\n",
    )
    write_package_file(
        tmp_path,
        "apps/api/src/workflowforge_api/composition.py",
        "import workflowforge_worker\n",
    )

    violations = validate_repository(tmp_path)
    messages = "\n".join(violation.message for violation in violations)

    assert "must not import workflowforge_application" in messages
    assert "must not import workflowforge_infrastructure" in messages
    assert "must not import workflowforge_worker" in messages


def test_forbidden_third_party_dependencies_fail(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/repository.py",
        "import sqlalchemy\n",
    )
    write_package_file(
        tmp_path,
        "packages/contracts/src/workflowforge_contracts/http.py",
        "import fastapi\n",
    )
    write_package_file(
        tmp_path,
        "packages/application/src/workflowforge_application/tasks.py",
        "from celery import Celery\nimport boto3\n",
    )

    violations = validate_repository(tmp_path)
    messages = "\n".join(violation.message for violation in violations)

    assert "must not import sqlalchemy" in messages
    assert "must not import fastapi" in messages
    assert "must not import celery" in messages
    assert "must not import boto3" in messages


def test_submodule_import_matches_forbidden_root(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/repository.py",
        "from sqlalchemy.orm import Session\n",
    )

    violations = validate_repository(tmp_path)

    assert len(violations) == 1
    assert violations[0].line == 1
    assert violations[0].message == "must not import sqlalchemy"


def test_string_literal_dynamic_import_is_detected(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/application/src/workflowforge_application/dynamic.py",
        "import importlib\nimportlib.import_module('workflowforge_infrastructure.config')\n",
    )
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/dynamic.py",
        "__import__('sqlalchemy.orm')\n",
    )

    violations = validate_repository(tmp_path)
    messages = "\n".join(violation.message for violation in violations)

    assert "must not import workflowforge_infrastructure" in messages
    assert "must not import sqlalchemy" in messages


def test_syntax_error_reports_readable_violation(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/broken.py",
        "def broken(:\n",
    )

    violations = validate_repository(tmp_path)
    output = format_violations(violations, tmp_path)

    assert len(violations) == 1
    assert "Architecture violation:" in output
    assert "packages\\domain\\src\\workflowforge_domain\\broken.py:1" in output or (
        "packages/domain/src/workflowforge_domain/broken.py:1" in output
    )
    assert "contains invalid Python syntax" in output


def write_package_file(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
