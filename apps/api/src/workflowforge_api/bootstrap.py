"""First-owner bootstrap CLI."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from workflowforge_application.security import (
    BootstrapOwner,
    BootstrapOwnerCommand,
    BootstrapOwnerResult,
)
from workflowforge_application.security.errors import BootstrapRefusedError
from workflowforge_infrastructure.audit import SqlAlchemyAuditRepository
from workflowforge_infrastructure.config import get_settings
from workflowforge_infrastructure.database import (
    SqlAlchemyTransactionManager,
    create_async_database_engine,
    create_async_session_factory,
    dispose_async_engine,
)
from workflowforge_infrastructure.identity import (
    Argon2PasswordHasher,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemyUserRepository,
    Uuid4Generator,
)
from workflowforge_infrastructure.security import SqlAlchemyIdentityBootstrapRepository

PASSWORD_ENV_VAR = "WORKFLOWFORGE_BOOTSTRAP_OWNER_PASSWORD"


def main(argv: list[str] | None = None) -> int:
    """Run the first-owner bootstrap command."""

    parser = argparse.ArgumentParser(description="Bootstrap the first WorkflowForge owner.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument(
        "--password-from-env",
        action="store_true",
        help=f"Read the bootstrap password from {PASSWORD_ENV_VAR}.",
    )
    args = parser.parse_args(argv)
    try:
        password = _password_from_env() if args.password_from_env else _prompt_password()
        result = asyncio.run(
            _bootstrap(
                email=args.email,
                display_name=args.display_name,
                password=password,
                organization_name=args.organization_name,
                organization_slug=args.organization_slug,
            )
        )
    except BootstrapRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("Bootstrap failed.", file=sys.stderr)
        return 1

    print(
        "Bootstrap complete: "
        f"user_id={result.user_id} organization_id={result.organization_id} "
        f"membership_id={result.membership_id}"
    )
    return 0


async def _bootstrap(
    *,
    email: str,
    display_name: str,
    password: str,
    organization_name: str,
    organization_slug: str,
) -> BootstrapOwnerResult:
    settings = get_settings()
    engine = create_async_database_engine(settings.database)
    session = create_async_session_factory(engine)()
    try:
        use_case = BootstrapOwner(
            state=SqlAlchemyIdentityBootstrapRepository(session),
            users=SqlAlchemyUserRepository(session),
            organizations=SqlAlchemyOrganizationRepository(session),
            memberships=SqlAlchemyMembershipRepository(session),
            credentials=SqlAlchemyPasswordCredentialRepository(session),
            password_hasher=Argon2PasswordHasher(),
            audit=SqlAlchemyAuditRepository(session),
            transaction=SqlAlchemyTransactionManager(session),
            ids=Uuid4Generator(),
        )
        return await use_case(
            BootstrapOwnerCommand(
                email=email,
                display_name=display_name,
                password=password,
                organization_name=organization_name,
                organization_slug=organization_slug,
            )
        )
    finally:
        await session.close()
        await dispose_async_engine(engine)


def _password_from_env() -> str:
    value = os.environ.get(PASSWORD_ENV_VAR)
    if not value:
        msg = f"{PASSWORD_ENV_VAR} is required when --password-from-env is used."
        raise ValueError(msg)
    return value


def _prompt_password() -> str:
    password = getpass.getpass("Owner password: ")
    confirmation = getpass.getpass("Confirm owner password: ")
    if password != confirmation:
        msg = "Password confirmation does not match."
        raise ValueError(msg)
    return password


if __name__ == "__main__":
    raise SystemExit(main())
