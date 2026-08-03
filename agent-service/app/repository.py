from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Conversation, Message, utcnow


class ConversationNotFoundError(LookupError):
    pass


class ConversationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    async def create(self, user_id: str) -> Conversation:
        def _create() -> Conversation:
            conversation = Conversation(id=str(uuid.uuid4()), user_id=user_id)
            with self.session_factory() as session:
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
            return conversation

        return await asyncio.to_thread(_create)

    async def get_owned(self, conversation_id: str, user_id: str) -> Conversation:
        def _get() -> Conversation:
            with self.session_factory() as session:
                result = session.execute(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                conversation = result.scalar_one_or_none()
                if conversation is None:
                    raise ConversationNotFoundError("Conversación no encontrada")
                return conversation

        return await asyncio.to_thread(_get)

    async def load_history(self, conversation_id: str, limit: int) -> list[dict[str, str]]:
        def _load() -> list[dict[str, str]]:
            with self.session_factory() as session:
                result = session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.id.desc())
                    .limit(limit)
                )
                rows = list(reversed(result.scalars().all()))
                return [{"role": row.role, "content": row.content} for row in rows]

        return await asyncio.to_thread(_load)

    async def add_exchange(self, conversation_id: str, user_message: str, assistant_message: str) -> None:
        def _add() -> None:
            with self.session_factory() as session:
                conversation = session.get(Conversation, conversation_id)
                if conversation is None:
                    raise ConversationNotFoundError("Conversación no encontrada")
                conversation.updated_at = utcnow()
                session.add_all(
                    [
                        Message(conversation_id=conversation_id, role="user", content=user_message),
                        Message(conversation_id=conversation_id, role="assistant", content=assistant_message),
                    ]
                )
                session.commit()

        await asyncio.to_thread(_add)

    async def list_messages(self, conversation_id: str, user_id: str, limit: int = 100) -> list[Message]:
        await self.get_owned(conversation_id, user_id)

        def _list() -> list[Message]:
            with self.session_factory() as session:
                result = session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.id.asc())
                    .limit(limit)
                )
                return list(result.scalars().all())

        return await asyncio.to_thread(_list)

    async def delete_owned(self, conversation_id: str, user_id: str) -> bool:
        await self.get_owned(conversation_id, user_id)

        def _delete() -> bool:
            with self.session_factory() as session:
                result = session.execute(
                    delete(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                session.commit()
                return bool(result.rowcount)

        return await asyncio.to_thread(_delete)
