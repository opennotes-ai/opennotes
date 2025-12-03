import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.cache.models import SessionData
from src.cache.redis_client import redis_client
from src.config import settings

if TYPE_CHECKING:
    from src.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, redis_client: "RedisClient") -> None:
        self.redis = redis_client
        self.session_prefix = "session"

    def _generate_session_id(self) -> str:
        return secrets.token_urlsafe(32)

    def _get_session_key(self, session_id: str) -> str:
        return f"{self.session_prefix}:{session_id}"

    def _get_user_sessions_key(self, user_id: int) -> str:
        return f"{self.session_prefix}:user:{user_id}:sessions"

    async def create_session(
        self,
        user_id: int,
        username: str,
        device_id: str | None = None,
        ttl: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> SessionData:
        session_id = self._generate_session_id()
        ttl_seconds = ttl or settings.SESSION_TTL

        session_data = SessionData(
            session_id=session_id,
            user_id=user_id,
            username=username,
            device_id=device_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            metadata=metadata or {},
        )

        session_key = self._get_session_key(session_id)
        serialized = session_data.model_dump_json()
        user_sessions_key = self._get_user_sessions_key(user_id)

        if not self.redis.client:
            raise RuntimeError("Redis client not connected")

        try:
            async with self.redis.client.pipeline(transaction=True) as pipe:
                pipe.set(session_key, serialized.encode("utf-8"), ex=ttl_seconds)
                pipe.sadd(user_sessions_key, session_id)
                pipe.expire(user_sessions_key, ttl_seconds)
                await pipe.execute()

            logger.info(f"Created session {session_id} for user {user_id}")
            return session_data
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {e}")
            try:
                await self.redis.delete(session_key)
                await self.redis.delete(user_sessions_key)
                logger.debug(f"Cleaned up partial session state for user {user_id}")
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to clean up partial session state for user {user_id}: {cleanup_error}"
                )
            raise RuntimeError(f"Failed to create session for user {user_id}") from e

    async def get_session(self, session_id: str) -> SessionData | None:
        session_key = self._get_session_key(session_id)
        cached = await self.redis.get(session_key)

        if not cached:
            return None

        try:
            session_data = SessionData.model_validate_json(cached)

            if session_data.is_expired():
                await self.delete_session(session_id)
                return None

            return session_data
        except Exception as e:
            logger.error(f"Failed to deserialize session {session_id}: {e}")
            return None

    async def refresh_session(
        self,
        session_id: str,
        ttl: int | None = None,
    ) -> SessionData | None:
        session_data = await self.get_session(session_id)
        if not session_data:
            return None

        ttl_seconds = ttl or settings.SESSION_TTL
        session_data.refresh(ttl_seconds)

        session_key = self._get_session_key(session_id)
        serialized = session_data.model_dump_json()

        success = await self.redis.set(session_key, serialized, ttl=ttl_seconds)
        if not success:
            logger.error(f"Failed to refresh session {session_id}")
            return None

        logger.debug(f"Refreshed session {session_id}")
        return session_data

    async def delete_session(self, session_id: str) -> bool:
        session_data = await self.get_session(session_id)
        if not session_data:
            return False

        if not self.redis.client:
            return False

        session_key = self._get_session_key(session_id)
        user_sessions_key = self._get_user_sessions_key(session_data.user_id)

        try:
            async with self.redis.client.pipeline(transaction=True) as pipe:
                pipe.delete(session_key)
                pipe.srem(user_sessions_key, session_id)
                await pipe.execute()

            logger.info(f"Deleted session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    async def get_user_sessions(self, user_id: int) -> list[SessionData]:
        user_sessions_key = self._get_user_sessions_key(user_id)

        if not self.redis.client:
            return []

        try:
            session_ids = await self.redis.client.smembers(user_sessions_key)  # type: ignore[misc]
            if not session_ids:
                return []

            # Batch get all sessions using pipeline
            session_keys = [self._get_session_key(sid) for sid in session_ids]
            async with self.redis.client.pipeline(transaction=False) as pipe:
                for key in session_keys:
                    pipe.get(key)
                values = await pipe.execute()

            sessions = []
            for value in values:
                if value:
                    try:
                        session_data = SessionData.model_validate_json(value)
                        if not session_data.is_expired():
                            sessions.append(session_data)
                    except Exception as e:
                        logger.warning(f"Failed to deserialize session data: {e}")
                        continue

            return sessions
        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            return []

    async def delete_user_sessions(self, user_id: int) -> int:
        sessions = await self.get_user_sessions(user_id)
        count = 0

        for session in sessions:
            if await self.delete_session(session.session_id):
                count += 1

        user_sessions_key = self._get_user_sessions_key(user_id)
        await self.redis.delete(user_sessions_key)

        logger.info(f"Deleted {count} sessions for user {user_id}")
        return count

    async def delete_device_session(self, user_id: int, device_id: str) -> bool:
        sessions = await self.get_user_sessions(user_id)

        for session in sessions:
            if session.device_id == device_id:
                return await self.delete_session(session.session_id)

        return False


def get_session_manager() -> SessionManager:
    """
    Dependency injection factory for SessionManager.

    Returns:
        SessionManager: Initialized session manager with Redis client

    Example:
        from typing import Annotated
        from fastapi import Depends

        async def some_endpoint(
            session_mgr: Annotated[SessionManager, Depends(get_session_manager)]
        ):
            await session_mgr.create_session(...)
    """
    return SessionManager(redis_client)
