"""Identity and tenancy domain policies."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from workflowforge_domain.identity.entities import Membership
from workflowforge_domain.identity.enums import MembershipStatus, Role
from workflowforge_domain.identity.errors import LastActiveOwnerViolation


class MembershipMutation(StrEnum):
    """Membership mutations covered by the last-active-owner invariant."""

    DEMOTE_OWNER = "demote_owner"
    SUSPEND_OWNER = "suspend_owner"
    REMOVE_OWNER = "remove_owner"


class MembershipPolicy:
    """Pure membership policies that operate on supplied domain objects only."""

    @staticmethod
    def ensure_not_last_active_owner(
        *,
        target: Membership,
        memberships: Iterable[Membership],
        mutation: MembershipMutation,
    ) -> None:
        """Reject mutations that would remove the final active owner.

        Only active owner memberships in the target organization count. Duplicate
        membership objects are de-duplicated by membership identifier.
        """

        if target.role is not Role.OWNER or target.status is not MembershipStatus.ACTIVE:
            return

        if mutation not in {
            MembershipMutation.DEMOTE_OWNER,
            MembershipMutation.SUSPEND_OWNER,
            MembershipMutation.REMOVE_OWNER,
        }:
            return

        active_owner_ids = {target.id}
        active_owner_ids.update(
            membership.id
            for membership in memberships
            if membership.organization_id == target.organization_id
            and membership.role is Role.OWNER
            and membership.status is MembershipStatus.ACTIVE
        )

        if len(active_owner_ids) <= 1 and target.id in active_owner_ids:
            msg = "Cannot mutate the final active owner membership."
            raise LastActiveOwnerViolation(msg)
