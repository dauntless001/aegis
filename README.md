Aegis is a lightweight background task-processing system inspired by Celery and QStash, using FastAPI, PostgreSQL, and SQLAlchemy's asynchronous APIs.

limitation
One limitation to keep in mind: Python can cancel a coroutine that cooperates with cancellation, but it cannot guarantee that an external side effect already started by a handler is undone.