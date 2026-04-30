"""Parallel tool dispatch with mid-flight interrupt support.

``Agent.run`` schedules every tool call for an iteration as a coroutine
and hands the bundle to :func:`gather_or_cancel`.  If no interrupt
event is supplied (or it never fires) this behaves exactly like
``asyncio.gather(..., return_exceptions=True)``.

When the interrupt fires mid-execution:

1. All still-pending tasks are cancelled.
2. Already-completed tasks keep their real results.
3. Cancelled tasks are reported as ``(tc, "Cancelled by user.")``
   so the caller can post a stub :class:`ToolMessage` and exit the
   loop cleanly.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.agent.schemas.chat import ToolCall


async def gather_or_cancel(
    coros: list,
    interrupt_event: asyncio.Event | None,
    tc_list: list[ToolCall],
    agent_name: str,
) -> list[tuple[ToolCall, str] | BaseException]:
    """Run *coros* in parallel; cancel unfinished ones on interrupt.

    Results preserve the order of *tc_list*.
    """
    if not coros:
        return []

    tasks = [asyncio.ensure_future(c) for c in coros]

    if interrupt_event is None:
        # No interrupt possible — plain gather behaviour
        return await asyncio.gather(*tasks, return_exceptions=True)

    # Create a waiter that fires when the interrupt event is set
    interrupt_waiter = asyncio.ensure_future(interrupt_event.wait())

    try:
        # Wait until either all tool tasks finish or the interrupt fires
        tool_set = set(tasks)
        done: set[asyncio.Future] = set()
        pending = tool_set.copy()

        while pending:
            # Wait for the first completed item among pending tools + interrupt
            wait_set = pending | {interrupt_waiter}
            newly_done, _ = await asyncio.wait(
                wait_set, return_when=asyncio.FIRST_COMPLETED
            )
            done |= newly_done & tool_set
            pending = tool_set - done

            if interrupt_waiter in newly_done:
                # Interrupt fired — cancel remaining tool tasks
                for t in pending:
                    t.cancel()
                # Wait for cancellation to propagate
                if pending:
                    await asyncio.wait(pending)
                break
    finally:
        interrupt_waiter.cancel()
        # Suppress the CancelledError from the waiter
        try:
            await interrupt_waiter
        except (asyncio.CancelledError, Exception):
            pass

    # Build results — preserve order matching tc_list
    results: list[tuple[ToolCall, str] | BaseException] = []
    for task, tc in zip(tasks, tc_list):
        if task.cancelled():
            results.append((tc, "Cancelled by user."))
            logger.info(
                "tool_cancelled agent={} tool={}",
                agent_name,
                tc.function.name,
            )
        elif task.exception() is not None:
            results.append(task.exception())  # type: ignore[arg-type]
        else:
            results.append(task.result())
    return results
