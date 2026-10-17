import asyncio
from typing import Any


async def add_numbers(payload: dict[str, Any]) -> dict[str, int]:
    a = payload["a"]
    b = payload["b"]

    await asyncio.sleep(1)

    return {"sum": a + b}