"""Cancellation-safe completion of owned async and blocking work."""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress


async def run_blocking(function, *args, **kwargs):
    return await complete_on_cancel(asyncio.to_thread(function, *args, **kwargs))


async def complete_on_cancel[T](awaitable: Awaitable[T]) -> T:
    """Finish owned work before propagating cancellation to its caller."""
    operation = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(operation)
    except asyncio.CancelledError:
        while not operation.done():
            try:
                await asyncio.shield(operation)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        with suppress(Exception):
            operation.result()
        raise
