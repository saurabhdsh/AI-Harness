"""Lightweight in-process event bus for audit/observability hooks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]

_handlers: list[EventHandler] = []


def subscribe(handler: EventHandler) -> None:
    _handlers.append(handler)


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    for handler in list(_handlers):
        result = handler(event_type, payload)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]
