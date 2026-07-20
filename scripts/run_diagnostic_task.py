"""Publish and retrieve the safe diagnostic echo task."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from workflowforge_contracts import DIAGNOSTIC_ECHO_TASK_NAME, DiagnosticEchoPayload
from workflowforge_infrastructure.config import get_settings
from workflowforge_infrastructure.tasks import close_celery_resources, create_celery_app


def main(argv: Sequence[str] | None = None) -> int:
    """Run the diagnostic task and print its JSON result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", default="hello", help="Diagnostic message to echo.")
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="Result wait timeout in seconds."
    )
    parser.add_argument("--correlation-id", default=None, help="Optional task correlation ID.")
    args = parser.parse_args(argv)

    payload = DiagnosticEchoPayload(message=args.message)
    app = create_celery_app(get_settings())
    async_result = None
    headers = {"x-correlation-id": args.correlation_id} if args.correlation_id else None
    try:
        async_result = app.send_task(
            DIAGNOSTIC_ECHO_TASK_NAME,
            args=(payload.model_dump(mode="json"),),
            headers=headers,
        )
        result = async_result.get(timeout=args.timeout)
    finally:
        close_celery_resources(app, async_result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
