### Aegis — Lightweight Background Task Processing System
Aegis is a lightweight background task-processing system inspired by Celery and QStash, using FastAPI, PostgreSQL, and SQLAlchemy's asynchronous APIs.
**Technologies:** Python, FastAPI, PostgreSQL, SQLAlchemy, asyncio, pytest

- Designed and developed a background task processing API supporting task submission, status tracking, delayed execution, retries, and idempotent requests.
- Implemented database-backed worker coordination using PostgreSQL transactions and row-level locking with `FOR UPDATE SKIP LOCKED` to prevent competing workers from claiming the same task.
- Built a lease-based task execution model with heartbeat-driven lease renewal and expired-lease recovery to handle interrupted worker execution.
- Implemented retry handling with exponential backoff, attempt tracking, and terminal failure states.
- Developed task cancellation and execution-result persistence, including safeguards against stale workers completing tasks after lease loss.
- Built an asynchronous task handler registry and automated tests covering worker coordination, retries, lease recovery, cancellation, handler dispatch, and idempotency.


limitation
One limitation to keep in mind: Python can cancel a coroutine that cooperates with cancellation, but it cannot guarantee that an external side effect already started by a handler is undone.