"""Validate WorkflowForge package import boundaries."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PACKAGE_SOURCE_DIRS: Mapping[str, tuple[str, ...]] = {
    "workflowforge_api": ("apps/api/src/workflowforge_api",),
    "workflowforge_worker": ("apps/worker/src/workflowforge_worker",),
    "workflowforge_scheduler": ("apps/scheduler/src/workflowforge_scheduler",),
    "workflowforge_domain": ("packages/domain/src/workflowforge_domain",),
    "workflowforge_contracts": ("packages/contracts/src/workflowforge_contracts",),
    "workflowforge_application": ("packages/application/src/workflowforge_application",),
    "workflowforge_infrastructure": ("packages/infrastructure/src/workflowforge_infrastructure",),
}

WORKFLOWFORGE_PACKAGES = frozenset(PACKAGE_SOURCE_DIRS)

ALLOWED_INTERNAL_IMPORTS_BY_PACKAGE: Mapping[str, frozenset[str]] = {
    "workflowforge_domain": frozenset(),
    "workflowforge_contracts": frozenset({"workflowforge_domain"}),
    "workflowforge_application": frozenset({"workflowforge_domain", "workflowforge_contracts"}),
    "workflowforge_infrastructure": frozenset({"workflowforge_domain", "workflowforge_contracts"}),
    "workflowforge_api": frozenset(
        {
            "workflowforge_domain",
            "workflowforge_contracts",
            "workflowforge_application",
            "workflowforge_infrastructure",
        }
    ),
    "workflowforge_worker": frozenset(
        {
            "workflowforge_domain",
            "workflowforge_contracts",
            "workflowforge_application",
            "workflowforge_infrastructure",
        }
    ),
    "workflowforge_scheduler": frozenset(
        {
            "workflowforge_domain",
            "workflowforge_contracts",
            "workflowforge_application",
            "workflowforge_infrastructure",
        }
    ),
}

FORBIDDEN_IMPORTS_BY_PACKAGE: Mapping[str, frozenset[str]] = {
    "workflowforge_domain": frozenset(
        {
            "alembic",
            "anthropic",
            "boto3",
            "botocore",
            "celery",
            "fastapi",
            "httpx",
            "openai",
            "playwright",
            "redis",
            "sqlalchemy",
            "starlette",
            "uvicorn",
        }
    ),
    "workflowforge_contracts": frozenset(
        {
            "alembic",
            "boto3",
            "botocore",
            "celery",
            "fastapi",
            "redis",
            "sqlalchemy",
            "starlette",
            "uvicorn",
        }
    ),
    "workflowforge_application": frozenset(
        {
            "alembic",
            "anthropic",
            "boto3",
            "botocore",
            "celery",
            "fastapi",
            "openai",
            "redis",
            "sqlalchemy",
            "starlette",
            "uvicorn",
        }
    ),
    "workflowforge_infrastructure": frozenset(),
    "workflowforge_api": frozenset(),
    "workflowforge_worker": frozenset(),
    "workflowforge_scheduler": frozenset(),
}


@dataclass(frozen=True)
class SourcePackage:
    """A WorkflowForge package and its source directory."""

    name: str
    source_dir: Path


@dataclass(frozen=True)
class ImportReference:
    """One statically discovered import reference."""

    module: str
    root: str
    line: int


@dataclass(frozen=True)
class ArchitectureViolation:
    """An import-boundary or syntax violation."""

    package: str
    path: Path
    line: int
    message: str

    def format(self, repository_root: Path) -> str:
        relative_path = self.path.relative_to(repository_root)
        return (
            f"Architecture violation:\n{relative_path}:{self.line}\n{self.package} {self.message}"
        )


@dataclass(frozen=True)
class DependencyGraph:
    """WorkflowForge package dependency graph."""

    edges: Mapping[str, frozenset[str]]


def validate_repository(repository_root: Path) -> list[ArchitectureViolation]:
    """Validate the repository and return architecture violations."""

    root = repository_root.resolve()
    source_packages = discover_source_packages(root)
    violations: list[ArchitectureViolation] = []
    graph_edges: dict[str, set[str]] = {package: set() for package in WORKFLOWFORGE_PACKAGES}

    for source_package in source_packages:
        for python_file in discover_python_files(source_package.source_dir):
            imports, syntax_violation = parse_imports(python_file, source_package.name)
            if syntax_violation is not None:
                violations.append(syntax_violation)
                continue

            for import_reference in imports:
                imported_package = owning_package_for_import(import_reference.module)
                if imported_package is not None and imported_package != source_package.name:
                    graph_edges[source_package.name].add(imported_package)
                    if (
                        imported_package
                        not in ALLOWED_INTERNAL_IMPORTS_BY_PACKAGE[source_package.name]
                    ):
                        violations.append(
                            ArchitectureViolation(
                                package=source_package.name,
                                path=python_file,
                                line=import_reference.line,
                                message=f"must not import {imported_package}",
                            )
                        )

                if import_reference.root in FORBIDDEN_IMPORTS_BY_PACKAGE[source_package.name]:
                    violations.append(
                        ArchitectureViolation(
                            package=source_package.name,
                            path=python_file,
                            line=import_reference.line,
                            message=f"must not import {import_reference.root}",
                        )
                    )

    graph = DependencyGraph(
        edges={package: frozenset(dependencies) for package, dependencies in graph_edges.items()}
    )
    violations.extend(detect_cycle_violations(graph, source_packages))
    return violations


def discover_source_packages(repository_root: Path) -> list[SourcePackage]:
    """Discover configured source packages that exist under the repository root."""

    source_packages: list[SourcePackage] = []
    for package_name, relative_dirs in PACKAGE_SOURCE_DIRS.items():
        for relative_dir in relative_dirs:
            source_dir = repository_root / relative_dir
            if source_dir.exists():
                source_packages.append(SourcePackage(package_name, source_dir))
    return source_packages


def discover_python_files(source_dir: Path) -> Iterable[Path]:
    """Yield Python files below a source package."""

    return sorted(
        path
        for path in source_dir.rglob("*.py")
        if "__pycache__" not in path.parts
        and ".venv" not in path.parts
        and ".mypy_cache" not in path.parts
        and ".ruff_cache" not in path.parts
    )


def parse_imports(
    path: Path, package_name: str
) -> tuple[list[ImportReference], ArchitectureViolation | None]:
    """Parse import statements from a Python file."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [], ArchitectureViolation(
            package=package_name,
            path=path,
            line=exc.lineno or 1,
            message=f"contains invalid Python syntax: {exc.msg}",
        )

    imports: list[ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                ImportReference(module=alias.name, root=module_root(alias.name), line=node.lineno)
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append(
                    ImportReference(
                        module=node.module,
                        root=module_root(node.module),
                        line=node.lineno,
                    )
                )
        elif isinstance(node, ast.Call):
            dynamic_import = literal_dynamic_import(node)
            if dynamic_import is not None:
                imports.append(
                    ImportReference(
                        module=dynamic_import,
                        root=module_root(dynamic_import),
                        line=node.lineno,
                    )
                )

    return imports, None


def literal_dynamic_import(node: ast.Call) -> str | None:
    """Return a string-literal dynamic import target when it is statically obvious."""

    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value

    if (
        isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value

    return None


def module_root(module: str) -> str:
    """Return the top-level import root for a module name."""

    return module.split(".", maxsplit=1)[0]


def owning_package_for_import(module: str) -> str | None:
    """Return the WorkflowForge package root for an import, when known."""

    for package_name in WORKFLOWFORGE_PACKAGES:
        if module == package_name or module.startswith(f"{package_name}."):
            return package_name
    return None


def detect_cycle_violations(
    graph: DependencyGraph, source_packages: Sequence[SourcePackage]
) -> list[ArchitectureViolation]:
    """Detect cycles between WorkflowForge packages."""

    package_paths = {
        source_package.name: source_package.source_dir for source_package in source_packages
    }
    violations: list[ArchitectureViolation] = []
    seen_cycles: set[tuple[str, ...]] = set()

    for package in sorted(graph.edges):
        cycle = find_cycle_from(package, graph)
        if cycle is None:
            continue
        normalized = normalize_cycle(cycle)
        if normalized in seen_cycles:
            continue
        seen_cycles.add(normalized)
        path = package_paths.get(cycle[0], Path("."))
        violations.append(
            ArchitectureViolation(
                package=cycle[0],
                path=path,
                line=1,
                message=f"has a dependency cycle: {' -> '.join(cycle)}",
            )
        )

    return violations


def find_cycle_from(start: str, graph: DependencyGraph) -> list[str] | None:
    """Find one cycle reachable from start using deterministic DFS."""

    def visit(package: str, path: list[str]) -> list[str] | None:
        for dependency in sorted(graph.edges.get(package, ())):
            if dependency == start:
                return [*path, dependency]
            if dependency in path:
                cycle_start = path.index(dependency)
                return [*path[cycle_start:], dependency]
            cycle = visit(dependency, [*path, dependency])
            if cycle is not None:
                return cycle
        return None

    return visit(start, [start])


def normalize_cycle(cycle: Sequence[str]) -> tuple[str, ...]:
    """Normalize a cycle path so duplicate detections compare equal."""

    unique_cycle = list(cycle[:-1])
    minimum_index = min(range(len(unique_cycle)), key=unique_cycle.__getitem__)
    rotated = unique_cycle[minimum_index:] + unique_cycle[:minimum_index]
    return (*rotated, rotated[0])


def format_violations(violations: Sequence[ArchitectureViolation], repository_root: Path) -> str:
    """Format architecture violations for command-line output."""

    return "\n\n".join(violation.format(repository_root.resolve()) for violation in violations)


def main(argv: Sequence[str] | None = None) -> int:
    """Run architecture validation from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to validate. Defaults to the current directory.",
    )
    args = parser.parse_args(argv)

    repository_root = args.root.resolve()
    violations = validate_repository(repository_root)
    if violations:
        print(format_violations(violations, repository_root))
        return 1

    print("Architecture validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
