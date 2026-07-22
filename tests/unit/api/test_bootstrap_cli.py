"""First-owner bootstrap CLI tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from workflowforge_api import bootstrap
from workflowforge_application.security import BootstrapOwnerResult
from workflowforge_application.security.errors import BootstrapRefusedError

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
ORG_ID = UUID("22222222-2222-4222-8222-222222222222")
MEMBERSHIP_ID = UUID("33333333-3333-4333-8333-333333333333")
PASSWORD = "correct horse battery staple"


def test_bootstrap_cli_reads_secret_env_and_prints_only_safe_identifiers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, str]] = []

    async def fake_bootstrap(**kwargs: str) -> BootstrapOwnerResult:
        calls.append(kwargs)
        return BootstrapOwnerResult(
            user_id=USER_ID,
            organization_id=ORG_ID,
            membership_id=MEMBERSHIP_ID,
        )

    monkeypatch.setenv(bootstrap.PASSWORD_ENV_VAR, PASSWORD)
    monkeypatch.setattr(bootstrap, "_bootstrap", fake_bootstrap)

    exit_code = bootstrap.main(
        [
            "--email",
            "owner@example.com",
            "--display-name",
            "Owner",
            "--organization-name",
            "Example",
            "--organization-slug",
            "example",
            "--password-from-env",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0]["password"] == PASSWORD
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
    assert str(USER_ID) in captured.out


def test_bootstrap_cli_prompts_and_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return PASSWORD

    async def fake_bootstrap(**_kwargs: str) -> BootstrapOwnerResult:
        return BootstrapOwnerResult(
            user_id=USER_ID,
            organization_id=ORG_ID,
            membership_id=MEMBERSHIP_ID,
        )

    monkeypatch.setattr("workflowforge_api.bootstrap.getpass.getpass", fake_getpass)
    monkeypatch.setattr(bootstrap, "_bootstrap", fake_bootstrap)

    assert (
        bootstrap.main(
            [
                "--email",
                "owner@example.com",
                "--display-name",
                "Owner",
                "--organization-name",
                "Example",
                "--organization-slug",
                "example",
            ]
        )
        == 0
    )
    assert prompts == ["Owner password: ", "Confirm owner password: "]


def test_bootstrap_cli_mismatched_confirmation_exits_nonzero_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = iter([PASSWORD, "different password"])
    monkeypatch.setattr("workflowforge_api.bootstrap.getpass.getpass", lambda _prompt: next(values))

    exit_code = bootstrap.main(
        [
            "--email",
            "owner@example.com",
            "--display-name",
            "Owner",
            "--organization-name",
            "Example",
            "--organization-slug",
            "example",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err


def test_bootstrap_cli_refusal_exits_two_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_bootstrap(**_kwargs: str) -> BootstrapOwnerResult:
        raise BootstrapRefusedError("WorkflowForge identity is already initialized.")

    monkeypatch.setenv(bootstrap.PASSWORD_ENV_VAR, PASSWORD)
    monkeypatch.setattr(bootstrap, "_bootstrap", fake_bootstrap)

    exit_code = bootstrap.main(
        [
            "--email",
            "owner@example.com",
            "--display-name",
            "Owner",
            "--organization-name",
            "Example",
            "--organization-slug",
            "example",
            "--password-from-env",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "already initialized" in captured.err
    assert "Traceback" not in captured.err
