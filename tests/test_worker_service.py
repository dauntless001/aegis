from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest, asyncio
from unittest.mock import AsyncMock, patch
from app.models.task import Task, TaskAttempt
from app.services.worker_service import WorkerService
from app.utils.enums import TaskStatus
from sqlalchemy import select
from types import SimpleNamespace
from app.services.task_registry import TaskRegistry, task_registry
from app.services.handlers import add_numbers


@pytest.mark.asyncio
async def test_worker_claims_pending_task(session_factory):
    # Insert the task in its own session.
    async with session_factory() as session:
        task = Task(
            name="test_task",
            queue_name="default",
            payload={"message": "hello"},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=3,
        )

        session.add(task)
        await session.commit()
        task_id = task.id

    # Use a fresh session for the worker operation.
    async with session_factory() as worker_session:
        worker = WorkerService(
            db=worker_session,
            session_factory=session_factory,
        )

        claimed_task = await worker.claim_task(worker_id="test-worker")

        assert claimed_task is not None
        assert claimed_task.id == task_id
        assert claimed_task.status == TaskStatus.RUNNING
        assert claimed_task.attempts == 1
        assert claimed_task.locked_by == "test-worker"
        assert claimed_task.locked_until is not None
        assert claimed_task.lease_token is not None


@pytest.mark.asyncio
async def test_two_workers_do_not_claim_same_task(session_factory):
    # Create one pending task.
    async with session_factory() as session:
        task = Task(
            name="concurrency_test",
            queue_name="default",
            payload={"message": "process me"},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=3,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    # Give each worker its own database session.
    async def claim(worker_id):
        async with session_factory() as session:
            worker = WorkerService(
                db=session,
                session_factory=session_factory,
            )
            return await worker.claim_task(worker_id=worker_id)

    first, second = await asyncio.gather(
        claim("worker-1"),
        claim("worker-2"),
    )

    # Only one worker should claim the single available task.
    claimed_tasks = [task for task in (first, second) if task is not None]

    assert len(claimed_tasks) == 1
    assert claimed_tasks[0].id == task_id
    assert claimed_tasks[0].status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_failed_task_is_scheduled_for_retry(session_factory):
    # Create a task that can be attempted up to three times.
    async with session_factory() as session:
        task = Task(
            name="retry_test",
            queue_name="default",
            payload={"message": "fail once"},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=3,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    # Claim the task so it has a valid lease and running attempt.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )
        claimed_task = await worker.claim_task(worker_id="retry-worker")

        assert claimed_task is not None
        assert claimed_task.id == task_id

        lease_token = claimed_task.lease_token
        assert lease_token is not None

    # Record the handler failure using a fresh session.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )

        before_failure = datetime.now(timezone.utc)

        recorded = await worker.fail_task(
            task_id=task_id,
            lease_token=lease_token,
            error="ValueError: intentional test failure",
        )

        assert recorded is True

    # Reload the task and verify its retry state.
    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RETRYING
        assert task.attempts == 1
        assert task.last_error == "ValueError: intentional test failure"
        assert task.scheduled_at >= before_failure + timedelta(seconds=2)
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            __import__("sqlalchemy").select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.FAILED
        assert attempt.error == "ValueError: intentional test failure"
        assert attempt.finished_at is not None

@pytest.mark.asyncio
async def test_execute_task_records_handler_failure(session_factory):
    async with session_factory() as session:
        task = Task(
            name="failing_handler_test",
            queue_name="default",
            payload={"message": "trigger failure"},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=3,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    # Claim the task to obtain a valid lease.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )
        claimed_task = await worker.claim_task(worker_id="execution-test-worker")

        assert claimed_task is not None
        assert claimed_task.id == task_id

        # Save the lease before closing this session.
        lease_token = claimed_task.lease_token

    assert lease_token is not None

    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )

        async def pending_heartbeat(*args, **kwargs):
            await asyncio.Event().wait()

        # Prevent a real heartbeat loop; let the handler failure path run.
        with patch.object(
            worker,
            "heartbeat",
            new_callable=AsyncMock,
        ) as heartbeat:
            heartbeat.side_effect = pending_heartbeat

            with patch.object(
                worker,
                "_run_handler",
                new_callable=AsyncMock,
            ) as handler:
                handler.side_effect = ValueError(
                    "intentional handler failure"
                )

                async with session_factory() as read_session:
                    claimed_task = await read_session.get(Task, task_id)
                    assert claimed_task is not None

                    task_for_execution = {
                        "id": claimed_task.id,
                        "lease_token": claimed_task.lease_token,
                        "name": claimed_task.name,
                        "payload": claimed_task.payload,
                    }

                # Use a lightweight object containing the already-loaded values.
                from types import SimpleNamespace

                await worker.execute_task(SimpleNamespace(**task_for_execution))

    # Verify the failure was persisted.
    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RETRYING
        assert task.attempts == 1
        assert task.last_error == (
            "ValueError: intentional handler failure"
        )


@pytest.mark.asyncio
async def test_execute_task_marks_task_succeeded(session_factory):
    # Create a pending task.
    async with session_factory() as session:
        task = Task(
            name="successful_handler_test",
            queue_name="default",
            payload={"a": 10, "b": 20},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=3,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    # Claim it to establish a valid lease.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )
        claimed_task = await worker.claim_task(
            worker_id="success-test-worker"
        )

        assert claimed_task is not None
        assert claimed_task.id == task_id

    # Execute the task with a successful mocked handler.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )

        async def pending_heartbeat(*args, **kwargs):
            await asyncio.Event().wait()

        with patch.object(
            worker,
            "heartbeat",
            new_callable=AsyncMock,
        ) as heartbeat:
            heartbeat.side_effect = pending_heartbeat

            with patch.object(
                worker,
                "_run_handler",
                new_callable=AsyncMock,
            ) as handler:
                handler.return_value = {"result": 30}

                # Use a detached, lightweight object so no ORM session
                # transaction is opened just to read task attributes.
                from types import SimpleNamespace

                async with session_factory() as read_session:
                    task = await read_session.get(Task, task_id)
                    assert task is not None

                    task_data = SimpleNamespace(
                        id=task.id,
                        lease_token=task.lease_token,
                        name=task.name,
                        payload=task.payload,
                    )

                await worker.execute_task(task_data)

    # Verify persisted task and attempt state.
    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.SUCCEEDED
        assert task.result == {"result": 30}
        assert task.completed_at is not None
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.SUCCEEDED
        assert attempt.result == {"result": 30}
        assert attempt.finished_at is not None

@pytest.mark.asyncio
async def test_task_fails_after_max_attempts(session_factory):
    # Create a task whose maximum number of attempts is one.
    async with session_factory() as session:
        task = Task(
            name="exhausted_retry_test",
            queue_name="default",
            payload={"message": "always fails"},
            status=TaskStatus.PENDING,
            scheduled_at=datetime.now(timezone.utc),
            attempts=0,
            max_attempts=1,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    # Claim the task. Its attempt count becomes 1.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )
        claimed_task = await worker.claim_task(
            worker_id="exhausted-retry-worker"
        )

        assert claimed_task is not None
        assert claimed_task.id == task_id
        assert claimed_task.attempts == 1
        lease_token = claimed_task.lease_token

    assert lease_token is not None

    # Record the failure of the final permitted attempt.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )

        recorded = await worker.fail_task(
            task_id=task_id,
            lease_token=lease_token,
            error="RuntimeError: final attempt failed",
        )

        assert recorded is True

    # Verify that the task is permanently failed.
    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.attempts == 1
        assert task.completed_at is not None
        assert task.last_error == "RuntimeError: final attempt failed"
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.FAILED
        assert attempt.error == "RuntimeError: final attempt failed"
        assert attempt.finished_at is not None


@pytest.mark.asyncio
async def test_expired_lease_is_recovered(session_factory):
    now = datetime.now(timezone.utc)

    # Create a task that is already running with an expired lease.
    async with session_factory() as session:
        task = Task(
            name="expired_lease_test",
            queue_name="default",
            payload={"message": "recover me"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="dead-worker",
            locked_until=now - timedelta(seconds=10),
            lease_token=__import__("uuid").uuid4(),
            started_at=now - timedelta(minutes=2),
        )
        session.add(task)
        await session.flush()

        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=1,
            status=TaskStatus.RUNNING,
            worker_id="dead-worker",
            started_at=now - timedelta(minutes=2),
        )
        session.add(attempt)

        task_id = task.id
        await session.commit()

    # Recover tasks whose leases have expired.
    async with session_factory() as session:
        worker = WorkerService(
            db=session,
            session_factory=session_factory,
        )

        await worker.recover_expired_tasks()

    # Verify the task and attempt were updated.
    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RETRYING
        assert task.attempts == 1
        assert task.last_error == "Worker lease expired"
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.FAILED
        assert attempt.error == "Worker lease expired"
        assert attempt.finished_at is not None


@pytest.mark.asyncio
async def test_expired_lease_on_final_attempt_marks_task_failed(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="final_attempt_expired",
            queue_name="default",
            payload={"message": "this should not retry"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=1,
            locked_by="dead-worker",
            locked_until=now - timedelta(seconds=10),
            lease_token=uuid4(),
            started_at=now - timedelta(minutes=2),
        )
        session.add(task)
        await session.flush()

        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=1,
            status=TaskStatus.RUNNING,
            worker_id="dead-worker",
            started_at=now - timedelta(minutes=2),
        )
        session.add(attempt)

        task_id = task.id
        await session.commit()

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)
        await worker.recover_expired_tasks()

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.FAILED
        assert task.attempts == 1
        assert task.last_error == "Worker lease expired"
        assert task.completed_at is not None

        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.FAILED
        assert attempt.error == "Worker lease expired"
        assert attempt.finished_at is not None


@pytest.mark.asyncio
async def test_renew_lease_extends_task_lease(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="lease_renewal_test",
            queue_name="default",
            payload={"message": "keep me alive"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=now + timedelta(seconds=10),
            lease_token=uuid4(),
            started_at=now - timedelta(minutes=1),
        )
        session.add(task)
        await session.commit()
        task_id = task.id
        lease_token = task.lease_token
        original_lease = task.locked_until

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        renewed = await worker.renew_lease(
            task_id=task_id,
            lease_token=lease_token,
            lease_seconds=60,
        )

        assert renewed is True

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.locked_until > original_lease
        assert task.locked_until > datetime.now(timezone.utc)
        assert task.status == TaskStatus.RUNNING
        assert task.lease_token == lease_token


@pytest.mark.asyncio
async def test_renew_lease_rejects_invalid_token(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="invalid_token_test",
            queue_name="default",
            payload={"message": "protect this lease"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=now + timedelta(seconds=30),
            lease_token=uuid4(),
            started_at=now - timedelta(minutes=1),
        )
        session.add(task)
        await session.commit()

        task_id = task.id
        original_token = task.lease_token
        original_lease = task.locked_until

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        renewed = await worker.renew_lease(
            task_id=task_id,
            lease_token=uuid4(),  # Deliberately incorrect token
            lease_seconds=60,
        )

        assert renewed is False

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RUNNING
        assert task.lease_token == original_token
        assert task.locked_until == original_lease


@pytest.mark.asyncio
async def test_renew_lease_rejects_expired_lease(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="expired_lease_renewal_test",
            queue_name="default",
            payload={"message": "lease already expired"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=2),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=now - timedelta(seconds=10),
            lease_token=uuid4(),
            started_at=now - timedelta(minutes=2),
        )
        session.add(task)
        await session.commit()

        task_id = task.id
        original_token = task.lease_token
        original_lease = task.locked_until

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        renewed = await worker.renew_lease(
            task_id=task_id,
            lease_token=original_token,
            lease_seconds=60,
        )

        assert renewed is False

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RUNNING
        assert task.lease_token == original_token
        assert task.locked_until == original_lease

@pytest.mark.asyncio
async def test_execute_task_cancels_handler_when_lease_is_lost(session_factory):
    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        task_data = SimpleNamespace(
            id=uuid4(),
            lease_token=uuid4(),
            name="lease_lost_test",
            payload={"message": "this handler should stop"},
        )

        handler_started = asyncio.Event()
        handler_cancelled = asyncio.Event()

        async def long_running_handler(*args, **kwargs):
            handler_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        async def heartbeat_loses_lease(*args, **kwargs):
            await handler_started.wait()
            raise RuntimeError("Lease lost")

        with patch.object(
            worker, "heartbeat", new_callable=AsyncMock
        ) as heartbeat:
            heartbeat.side_effect = heartbeat_loses_lease

            with patch.object(
                worker, "_run_handler", new_callable=AsyncMock
            ) as handler:
                handler.side_effect = long_running_handler

                with pytest.raises(RuntimeError, match="Could not record failure"):
                    await worker.execute_task(task_data)

        assert handler_started.is_set()
        assert handler_cancelled.is_set()


@pytest.mark.asyncio
async def test_lease_loss_does_not_mark_task_succeeded(session_factory):
    async with session_factory() as session:
        task = Task(
            name="lease_lost_state_test",
            queue_name="default",
            payload={"message": "do not mark successful"},
            status=TaskStatus.RUNNING,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=datetime.now(timezone.utc) + timedelta(seconds=60),
            lease_token=uuid4(),
            started_at=datetime.now(timezone.utc),
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        task_data = SimpleNamespace(
            id=task_id,
            lease_token=uuid4(),  # Simulate a stale worker with the wrong token
            name="lease_lost_state_test",
            payload={"message": "do not mark successful"},
        )

        async def heartbeat_loses_lease(*args, **kwargs):
            raise RuntimeError("Lease lost")

        with patch.object(
            worker, "heartbeat", new_callable=AsyncMock
        ) as heartbeat:
            heartbeat.side_effect = heartbeat_loses_lease

            with patch.object(
                worker, "_run_handler", new_callable=AsyncMock
            ) as handler:
                handler.return_value = {"result": "should not be saved"}

                with pytest.raises(RuntimeError):
                    await worker.execute_task(task_data)

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.RUNNING
        assert task.result is None
        assert task.lease_token is not None


@pytest.mark.asyncio
async def test_worker_dispatches_task_to_registered_handler(session_factory):
    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        result = await worker._run_handler(
            "add_numbers",
            {"a": 10, "b": 20},
        )

    assert result == {"sum": 30}



@pytest.mark.asyncio
async def test_cancel_running_task_clears_lease(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="cancel_running_test",
            queue_name="default",
            payload={"message": "cancel me"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=now + timedelta(seconds=60),
            lease_token=uuid4(),
            started_at=now - timedelta(seconds=30),
            cancel_requested=True
        )
        session.add(task)
        await session.flush()

        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=1,
            status=TaskStatus.RUNNING,
            worker_id="worker-1",
            started_at=now - timedelta(seconds=30),
        )
        session.add(attempt)

        task_id = task.id
        lease_token = task.lease_token
        await session.commit()

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        cancelled = await worker.cancel_running_task(
            task_id=task_id,
            lease_token=lease_token,
        )

        assert cancelled is True

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.CANCELLED
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None
        assert task.completed_at is not None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.CANCELLED
        assert attempt.finished_at is not None


@pytest.mark.asyncio
async def test_complete_task_cancels_when_cancellation_requested(session_factory):
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        task = Task(
            name="cancel_before_completion",
            queue_name="default",
            payload={"message": "cancel before success"},
            status=TaskStatus.RUNNING,
            scheduled_at=now - timedelta(minutes=1),
            attempts=1,
            max_attempts=3,
            locked_by="worker-1",
            locked_until=now + timedelta(seconds=60),
            lease_token=uuid4(),
            started_at=now - timedelta(seconds=30),
            cancel_requested=True,
        )
        session.add(task)
        await session.flush()

        attempt = TaskAttempt(
            task_id=task.id,
            attempt_number=1,
            status=TaskStatus.RUNNING,
            worker_id="worker-1",
            started_at=now - timedelta(seconds=30),
        )
        session.add(attempt)

        task_id = task.id
        lease_token = task.lease_token
        await session.commit()

    async with session_factory() as session:
        worker = WorkerService(db=session, session_factory=session_factory)

        await worker.complete_task(
            task_id=task_id,
            lease_token=lease_token,
            result={"sum": 30},
        )

    async with session_factory() as session:
        task = await session.get(Task, task_id)

        assert task is not None
        assert task.status == TaskStatus.CANCELLED
        assert task.result is None
        assert task.completed_at is not None
        assert task.locked_by is None
        assert task.locked_until is None
        assert task.lease_token is None

        attempt = await session.scalar(
            select(TaskAttempt).where(
                TaskAttempt.task_id == task_id,
                TaskAttempt.attempt_number == 1,
            )
        )

        assert attempt is not None
        assert attempt.status == TaskStatus.CANCELLED
        assert attempt.finished_at is not None
