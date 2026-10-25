import asyncio
from typing import Any


async def add_numbers(payload: dict[str, Any]) -> dict[str, int]:
    a = payload["a"]
    b = payload["b"]

    await asyncio.sleep(1)

    return {"sum": a + b}


async def slow_task(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(75)

    return {
        "message": "Slow task completed successfully",
        "waited_seconds": 75,
    }