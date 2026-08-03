from __future__ import annotations

import asyncio
from collections import defaultdict


class ConversationLockManager:
    """Evita que dos mensajes de la misma conversación se procesen al mismo tiempo.

    Es suficiente para una instancia. Con varias réplicas, sustituir por un bloqueo
    distribuido mediante Redis o PostgreSQL advisory locks.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get(self, conversation_id: str) -> asyncio.Lock:
        return self._locks[conversation_id]
