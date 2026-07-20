"""Typed accessors for API application state."""

from dataclasses import dataclass
from typing import cast

from fastapi import Request
from starlette.datastructures import State
from workflowforge_application.health import DependencyHealthService


@dataclass
class ReadinessState:
    """Per-application readiness marker."""

    ready: bool = False

    def mark_ready(self) -> None:
        """Mark this application instance as ready."""

        self.ready = True

    def mark_not_ready(self) -> None:
        """Mark this application instance as not ready."""

        self.ready = False


def set_readiness_state(state: State, readiness_state: ReadinessState) -> None:
    """Store readiness state on the application state container."""

    state.readiness = readiness_state


def get_readiness_state(request: Request) -> ReadinessState:
    """Return readiness state for the current application instance."""

    return cast("ReadinessState", request.app.state.readiness)


def set_dependency_health_service(
    state: State,
    service: DependencyHealthService,
) -> None:
    """Store dependency health service on the application state container."""

    state.dependency_health_service = service


def get_dependency_health_service(request: Request) -> DependencyHealthService:
    """Return the dependency health service for the current application instance."""

    return cast("DependencyHealthService", request.app.state.dependency_health_service)
