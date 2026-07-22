"""First-owner bootstrap use case."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from workflowforge_domain.audit import AuditEvent, AuditEventType, AuditOutcome, AuditRequestContext
from workflowforge_domain.identity import (
    EmailAddress,
    Membership,
    Organization,
    OrganizationSlug,
    Role,
    User,
)

from workflowforge_application.audit import AuditRecorder
from workflowforge_application.identity import (
    IdGenerator,
    MembershipRepository,
    OrganizationRepository,
    PasswordCredentialRepository,
    PasswordHasher,
    SetUserPassword,
    SetUserPasswordCommand,
    TransactionManager,
    UserRepository,
)
from workflowforge_application.security.errors import BootstrapRefusedError
from workflowforge_application.security.ports import IdentityBootstrapRepository


@dataclass(frozen=True, slots=True)
class BootstrapOwnerCommand:
    """Input for secure first-owner bootstrap."""

    email: str
    display_name: str
    password: str
    organization_name: str
    organization_slug: str
    audit_context: AuditRequestContext | None = None


@dataclass(frozen=True, slots=True)
class BootstrapOwnerResult:
    """Safe bootstrap result."""

    user_id: UUID
    organization_id: UUID
    membership_id: UUID


class BootstrapOwner:
    """Create the first user, organization, owner membership, credential and audit row."""

    def __init__(
        self,
        *,
        state: IdentityBootstrapRepository,
        users: UserRepository,
        organizations: OrganizationRepository,
        memberships: MembershipRepository,
        credentials: PasswordCredentialRepository,
        password_hasher: PasswordHasher,
        audit: AuditRecorder,
        transaction: TransactionManager,
        ids: IdGenerator,
    ) -> None:
        self._state = state
        self._users = users
        self._organizations = organizations
        self._memberships = memberships
        self._credentials = credentials
        self._password_hasher = password_hasher
        self._audit = audit
        self._transaction = transaction
        self._ids = ids

    async def __call__(self, command: BootstrapOwnerCommand) -> BootstrapOwnerResult:
        """Bootstrap the first owner or refuse when identity state already exists."""

        try:
            now = datetime.now(UTC)
            await self._state.acquire_bootstrap_lock()
            bootstrap_state = await self._state.bootstrap_state()
            if bootstrap_state.initialized:
                await self._audit.record(
                    AuditEvent.create(
                        id=self._ids.new_uuid(),
                        event_type=AuditEventType.BOOTSTRAP_REFUSED,
                        outcome=AuditOutcome.DENIED,
                        occurred_at=now,
                        request_context=command.audit_context,
                        metadata={
                            "users": bootstrap_state.users,
                            "organizations": bootstrap_state.organizations,
                        },
                    )
                )
                await self._transaction.commit()
                msg = "WorkflowForge identity is already initialized."
                raise BootstrapRefusedError(msg)

            user_id = self._ids.new_uuid()
            organization_id = self._ids.new_uuid()
            membership_id = self._ids.new_uuid()
            user = User.create(
                id=user_id,
                email=EmailAddress(command.email),
                display_name=command.display_name,
                now=now,
            )
            organization = Organization.create(
                id=organization_id,
                name=command.organization_name,
                slug=OrganizationSlug(command.organization_slug),
                now=now,
            )
            membership = Membership.activate_directly(
                id=membership_id,
                user_id=user_id,
                organization_id=organization_id,
                role=Role.OWNER,
                now=now,
            )
            await self._users.add(user)
            await self._organizations.add(organization)
            await self._memberships.add(membership)
            await SetUserPassword(
                users=self._users,
                credentials=self._credentials,
                password_hasher=self._password_hasher,
            )(
                SetUserPasswordCommand(user_id=user_id, password=command.password),
                now=now,
            )
            await self._audit.record(
                AuditEvent.create(
                    id=self._ids.new_uuid(),
                    event_type=AuditEventType.BOOTSTRAP_OWNER_CREATED,
                    outcome=AuditOutcome.SUCCESS,
                    occurred_at=now,
                    actor_user_id=user_id,
                    organization_id=organization_id,
                    request_context=command.audit_context,
                )
            )
            await self._transaction.commit()
            return BootstrapOwnerResult(
                user_id=user_id,
                organization_id=organization_id,
                membership_id=membership_id,
            )
        except BootstrapRefusedError:
            raise
        except Exception:
            await self._transaction.rollback()
            raise
