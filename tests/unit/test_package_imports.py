"""Workspace package import checks."""


def test_all_workspace_packages_import() -> None:
    import workflowforge_api
    import workflowforge_application
    import workflowforge_contracts
    import workflowforge_domain
    import workflowforge_infrastructure
    import workflowforge_scheduler
    import workflowforge_worker

    assert workflowforge_domain.__version__ == "0.1.0a1"
    assert workflowforge_contracts.__version__ == "0.1.0a1"
    assert workflowforge_application.__version__ == "0.1.0a1"
    assert workflowforge_infrastructure.__version__ == "0.1.0a1"
    assert workflowforge_api.__version__ == "0.1.0a1"
    assert workflowforge_worker.__version__ == "0.1.0a1"
    assert workflowforge_scheduler.__version__ == "0.1.0a1"
