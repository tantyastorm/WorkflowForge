"""Architecture dependency-cycle tests."""

from pathlib import Path

from scripts.validate_architecture import format_violations, validate_repository


def test_multi_package_cycle_is_detected(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "packages/application/src/workflowforge_application/use_case.py",
        "import workflowforge_contracts\n",
    )
    write_package_file(
        tmp_path,
        "packages/contracts/src/workflowforge_contracts/contracts.py",
        "import workflowforge_domain\n",
    )
    write_package_file(
        tmp_path,
        "packages/domain/src/workflowforge_domain/model.py",
        "import workflowforge_application\n",
    )

    violations = validate_repository(tmp_path)
    output = format_violations(violations, tmp_path)

    assert "has a dependency cycle:" in output
    assert "workflowforge_application" in output
    assert "workflowforge_contracts" in output
    assert "workflowforge_domain" in output


def test_cross_app_cycle_is_detected(tmp_path: Path) -> None:
    write_package_file(
        tmp_path,
        "apps/api/src/workflowforge_api/composition.py",
        "import workflowforge_worker\n",
    )
    write_package_file(
        tmp_path,
        "apps/worker/src/workflowforge_worker/composition.py",
        "import workflowforge_api\n",
    )

    violations = validate_repository(tmp_path)
    output = format_violations(violations, tmp_path)

    assert "workflowforge_api must not import workflowforge_worker" in output
    assert "workflowforge_worker must not import workflowforge_api" in output
    assert "has a dependency cycle:" in output


def write_package_file(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
