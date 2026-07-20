"""Celery app factory tests."""

from workflowforge_contracts import DIAGNOSTIC_ECHO_TASK_NAME, SCHEDULER_HEARTBEAT_TASK_NAME
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.tasks import create_celery_app
from workflowforge_infrastructure.tasks.schedules import SCHEDULER_HEARTBEAT_SCHEDULE_NAME


def test_celery_factory_configures_safe_serialization_and_utc() -> None:
    app = create_celery_app(Settings())

    assert app.main == "workflowforge"
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.enable_utc is True
    assert app.conf.timezone == "UTC"
    assert app.conf.task_always_eager is False


def test_celery_factory_configures_queues_limits_and_ack_policy() -> None:
    settings = Settings()

    app = create_celery_app(settings)

    assert app.conf.task_default_queue == "workflowforge"
    assert {queue.name for queue in app.conf.task_queues} == {
        "workflowforge",
        "workflowforge.diagnostics",
    }
    assert app.conf.task_routes["system.diagnostics.*"]["queue"] == "workflowforge.diagnostics"
    assert app.conf.task_acks_late is False
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_track_started is True
    assert app.conf.task_time_limit == 300
    assert app.conf.task_soft_time_limit == 270
    assert app.conf.broker_connection_retry_on_startup is True
    assert app.conf.worker_concurrency == settings.celery.worker_concurrency


def test_celery_factory_registers_diagnostic_tasks_and_beat_schedule() -> None:
    app = create_celery_app(Settings())

    assert DIAGNOSTIC_ECHO_TASK_NAME in app.tasks
    assert SCHEDULER_HEARTBEAT_TASK_NAME in app.tasks
    assert app.conf.beat_schedule[SCHEDULER_HEARTBEAT_SCHEDULE_NAME] == {
        "task": SCHEDULER_HEARTBEAT_TASK_NAME,
        "schedule": 30,
        "options": {"queue": "workflowforge.diagnostics"},
    }


def test_celery_factory_is_repeatable_without_network_connection() -> None:
    settings = Settings()

    first = create_celery_app(settings)
    second = create_celery_app(settings)

    assert first is not second
    assert first.conf.broker_url == "redis://localhost:6379/1"
    assert second.conf.result_backend == "redis://localhost:6379/2"
