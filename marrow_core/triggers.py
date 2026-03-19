"""Immediate trigger mailboxes and payload helpers."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TriggerRequest:
    reason: str = ""
    prompt: str = ""


class TriggerMailbox:
    """Collect one-shot trigger payloads for the next agent run."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._pending: deque[TriggerRequest] = deque()

    def trigger(self, reason: str = "", prompt: str = "") -> None:
        self._pending.append(TriggerRequest(reason=reason.strip(), prompt=prompt.strip()))
        self._event.set()

    def consume_pending(self) -> TriggerRequest | None:
        if not self._pending:
            return None
        pending = list(self._pending)
        self._pending.clear()
        self._event.clear()
        reason = pending[-1].reason
        prompt = "\n\n".join(item.prompt for item in pending if item.prompt).strip()
        return TriggerRequest(reason=reason, prompt=prompt)

    async def wait(self, timeout: int | float) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True
