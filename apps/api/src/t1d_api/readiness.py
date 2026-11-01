"""Readiness for enabled capabilities only; external stores are not enabled yet."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Probe = Callable[[], Awaitable[bool]]


@dataclass
class Runtime:
    started: bool = False
    probes: tuple[Probe, ...] = ()

    async def is_ready(self, deadline_seconds: float) -> bool:
        if not self.started:
            return False
        try:
            async with asyncio.timeout(deadline_seconds):
                # Adding an enabled dependency requires an explicit probe registration.
                return all(await asyncio.gather(*(probe() for probe in self.probes)))
        except Exception:
            # Do not disclose dependency errors, addresses, or secrets.
            return False
