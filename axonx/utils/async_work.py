"""Cancellation-safe ownership of blocking work and its temporary resources."""

import asyncio
from contextlib import suppress


async def run_blocking(function, *args):
    operation = asyncio.create_task(asyncio.to_thread(function, *args))
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
