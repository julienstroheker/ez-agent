"""Conversation management for the agent runtime."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ez_agent.storage.base import ConversationData, IConversationStore

if TYPE_CHECKING:
    pass


class ConversationManager:
    """
    Manages conversations/sessions for an agent.

    A conversation is a session that can span multiple tasks.
    """

    def __init__(self, store: IConversationStore, agent_name: str) -> None:
        """
        Initialize the conversation manager.

        Args:
            store: Conversation storage implementation.
            agent_name: Name of the agent this manager is for.
        """
        self._store = store
        self._agent_name = agent_name

    async def create_conversation(
        self,
        conversation_id: str | None = None,
        metadata: dict | None = None,
    ) -> ConversationData:
        """
        Create a new conversation.

        Args:
            conversation_id: Optional custom ID. Generated if not provided.
            metadata: Optional metadata.

        Returns:
            The created conversation.
        """
        conv_id = conversation_id or str(uuid.uuid4())
        conversation = ConversationData(
            id=conv_id,
            agent_name=self._agent_name,
            metadata=metadata or {},
        )
        return await self._store.create(conversation)

    async def get_conversation(self, conversation_id: str) -> ConversationData | None:
        """
        Get a conversation by ID.

        Args:
            conversation_id: The conversation ID.

        Returns:
            The conversation, or None if not found.
        """
        return await self._store.get(conversation_id)

    async def get_or_create_conversation(
        self,
        conversation_id: str | None = None,
        metadata: dict | None = None,
    ) -> ConversationData:
        """
        Get an existing conversation or create a new one.

        Args:
            conversation_id: Optional conversation ID. If provided and exists, returns it.
            metadata: Metadata for new conversation.

        Returns:
            The conversation.
        """
        if conversation_id:
            existing = await self._store.get(conversation_id)
            if existing:
                return existing

        return await self.create_conversation(
            conversation_id=conversation_id,
            metadata=metadata,
        )

    async def add_task_to_conversation(
        self,
        conversation_id: str,
        task_id: str,
    ) -> ConversationData:
        """
        Add a task to a conversation.

        Args:
            conversation_id: The conversation ID.
            task_id: The task ID to add.

        Returns:
            The updated conversation.

        Raises:
            ValueError: If conversation not found.
        """
        conversation = await self._store.get(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation '{conversation_id}' not found")

        conversation.add_task(task_id)
        return await self._store.update(conversation)

    async def list_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConversationData]:
        """
        List conversations for this agent.

        Args:
            limit: Maximum results.
            offset: Results to skip.

        Returns:
            List of conversations.
        """
        return await self._store.list(
            agent_name=self._agent_name,
            limit=limit,
            offset=offset,
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: The conversation ID.

        Returns:
            True if deleted, False if not found.
        """
        return await self._store.delete(conversation_id)
