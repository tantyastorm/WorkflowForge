"""Celery app factory tests."""

from workflowforge_contracts import DIAGNOSTIC_ECHO_TASK_NAME, SCHEDULER_HEARTBEAT_TASK_NAME
from workflowforge_infrastructure.config import Settings
from workflowforge_infrastructure.tasks import close_celery_resources, create_celery_app
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


def test_close_celery_resources_releases_result_backend_and_pools() -> None:
    app = FakeCeleryApp()
    result = FakeResult()

    close_celery_resources(app, result)

    assert result.forgotten is True
    assert app.backend.result_consumer.stopped is True
    assert app.backend.client.closed is True
    assert app.backend.client.connection_pool.disconnected is True
    assert app.pool.closed is True
    assert app.producer_pool.closed is True
    assert app.closed is True


def test_close_celery_resources_still_closes_app_when_result_cleanup_fails() -> None:
    app = FakeCeleryApp()
    result = FakeResult(raises_on_forget=True)

    close_celery_resources(app, result)

    assert app.backend.result_consumer.stopped is True
    assert app.backend.client.closed is True
    assert app.closed is True


class FakeResult:
    def __init__(self, *, raises_on_forget: bool = False) -> None:
        self.raises_on_forget = raises_on_forget
        self.forgotten = False

    def forget(self) -> None:
        if self.raises_on_forget:
            raise RuntimeError("forget failed")
        self.forgotten = True


class FakeResultConsumer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeConnectionPool:
    def __init__(self) -> None:
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class FakeBackendClient:
    def __init__(self) -> None:
        self.closed = False
        self.connection_pool = FakeConnectionPool()

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self) -> None:
        self.result_consumer = FakeResultConsumer()
        self.client = FakeBackendClient()


class FakePool:
    def __init__(self) -> None:
        self.closed = False

    def force_close_all(self) -> None:
        self.closed = True


class FakeCeleryApp:
    def __init__(self) -> None:
        self.backend = FakeBackend()
        self.pool = FakePool()
        self.producer_pool = FakePool()
        self.closed = False

    def close(self) -> None:
        self.closed = True
