"""Typed accessors for API application state."""

from dataclasses import dataclass
from typing import cast

from fastapi import Request
from starlette.datastructures import State


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
