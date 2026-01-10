"""
Stateful Redis mock for testing that simulates real Redis behavior
"""

import json
import time
from typing import Any
from unittest.mock import AsyncMock


class StatefulRedisMock:
    """A stateful mock Redis client that simulates Redis operations"""

    def __init__(self):
        self.store: dict[str, Any] = {}
        self.ttl_store: dict[str, float] = {}  # Store expiration times

        # Create async mock methods that call our stateful implementations
        self.ping = AsyncMock(side_effect=self._ping)
        self.get = AsyncMock(side_effect=self._get)
        self.set = AsyncMock(side_effect=self._set)
        self.setex = AsyncMock(side_effect=self._setex)
        self.delete = AsyncMock(side_effect=self._delete)
        self.exists = AsyncMock(side_effect=self._exists)
        self.ttl = AsyncMock(side_effect=self._ttl)
        self.keys = AsyncMock(side_effect=self._keys)
        self.close = AsyncMock()
        self.flushdb = AsyncMock(side_effect=self._flushdb)
        self.expire = AsyncMock(side_effect=self._expire)
        self.mget = AsyncMock(side_effect=self._mget)
        self.mset = AsyncMock(side_effect=self._mset)
        # Redis set operations
        self.sadd = AsyncMock(side_effect=self._sadd)
        self.smembers = AsyncMock(side_effect=self._smembers)
        self.srem = AsyncMock(side_effect=self._srem)
        self.sismember = AsyncMock(side_effect=self._sismember)
        self.scard = AsyncMock(side_effect=self._scard)
        # Redis sorted set operations
        self.zadd = AsyncMock(side_effect=self._zadd)
        self.zcard = AsyncMock(side_effect=self._zcard)
        self.zrem = AsyncMock(side_effect=self._zrem)
        self.zremrangebyscore = AsyncMock(side_effect=self._zremrangebyscore)
        self.zrange = AsyncMock(side_effect=self._zrange)
        self.zscore = AsyncMock(side_effect=self._zscore)
        # Redis list operations
        self.lpush = AsyncMock(side_effect=self._lpush)
        self.rpush = AsyncMock(side_effect=self._rpush)
        self.lrange = AsyncMock(side_effect=self._lrange)
        self.llen = AsyncMock(side_effect=self._llen)
        # Redis hash operations
        self.hset = AsyncMock(side_effect=self._hset)
        self.hget = AsyncMock(side_effect=self._hget)
        self.hgetall = AsyncMock(side_effect=self._hgetall)
        self.hincrby = AsyncMock(side_effect=self._hincrby)
        # Redis counter operations
        self.incrby = AsyncMock(side_effect=self._incrby)
        self.incr = AsyncMock(side_effect=self._incr)
        # Pipeline support
        self.pipeline = self._pipeline

    async def _ping(self) -> bool:
        """Simulate Redis ping"""
        return True

    async def _get(self, key: str) -> Any | None:
        """Get a value from the store"""
        # Check if key has expired
        if key in self.ttl_store and time.time() > self.ttl_store[key]:
            # Key has expired, remove it
            del self.store[key]
            del self.ttl_store[key]
            return None

        value = self.store.get(key)

        # If value is a dict or list, return it as JSON string (like Redis does)
        if isinstance(value, dict | list):
            return json.dumps(value)

        return value

    async def _set(
        self, key: str, value: Any, ttl: int | None = None, ex: int | None = None
    ) -> bool:
        """Set a value in the store with optional TTL"""
        # Handle JSON serialization for complex types
        if isinstance(value, dict | list):
            value = json.dumps(value)

        self.store[key] = value

        # Handle TTL (time to live in seconds)
        ttl_seconds = ttl or ex
        if ttl_seconds:
            self.ttl_store[key] = time.time() + ttl_seconds
        elif key in self.ttl_store:
            # Remove TTL if setting without TTL
            del self.ttl_store[key]

        return True

    async def _setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set a value with expiration time in seconds"""
        return await self._set(key, value, ttl=seconds)

    async def _delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        count = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                if key in self.ttl_store:
                    del self.ttl_store[key]
                count += 1
        return count

    async def _exists(self, *keys: str) -> int:
        """Check if one or more keys exist"""
        count = 0
        for key in keys:
            # Check expiration
            if key in self.ttl_store and time.time() > self.ttl_store[key]:
                # Key has expired, remove it
                if key in self.store:
                    del self.store[key]
                    del self.ttl_store[key]
                continue

            if key in self.store:
                count += 1

        return count

    async def _ttl(self, key: str) -> int:
        """Get the TTL of a key in seconds"""
        if key not in self.store:
            return -2  # Key doesn't exist

        if key not in self.ttl_store:
            return -1  # Key exists but has no TTL

        ttl_remaining = int(self.ttl_store[key] - time.time())

        if ttl_remaining <= 0:
            # Key has expired
            del self.store[key]
            del self.ttl_store[key]
            return -2  # Key doesn't exist anymore

        return ttl_remaining

    async def _keys(self, pattern: str = "*") -> list:
        """Get all keys matching pattern"""
        # Simple pattern matching (only supports * wildcard)
        import re

        # Clean up expired keys first
        current_time = time.time()
        expired_keys = [key for key, expiry in self.ttl_store.items() if current_time > expiry]
        for key in expired_keys:
            if key in self.store:
                del self.store[key]
            del self.ttl_store[key]

        if pattern == "*":
            return list(self.store.keys())

        # Convert Redis pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"

        matching_keys = []
        for key in self.store:
            if re.match(regex_pattern, key):
                matching_keys.append(key)

        return matching_keys

    async def _flushdb(self) -> None:
        """Clear all data from the store"""
        self.store.clear()
        self.ttl_store.clear()

    async def _expire(self, key: str, seconds: int) -> int:
        """Set TTL on existing key"""
        if key not in self.store:
            return 0  # Key doesn't exist

        self.ttl_store[key] = time.time() + seconds
        return 1  # TTL was set

    async def _mget(self, *keys: str) -> list:
        """Get multiple values"""
        values = []
        for key in keys:
            value = await self._get(key)
            values.append(value)
        return values

    async def _mset(self, mapping: dict) -> bool:
        """Set multiple key-value pairs"""
        for key, value in mapping.items():
            await self._set(key, value)
        return True

    async def _sadd(self, key: str, *members: Any) -> int:
        """Add members to a Redis set"""
        if key not in self.store:
            self.store[key] = set()
        elif not isinstance(self.store[key], set):
            # Key exists but is not a set, raise error (Redis behavior)
            raise TypeError(f"Key {key} is not a set")

        # Convert to set if not already
        if not isinstance(self.store[key], set):
            self.store[key] = set()

        added = 0
        for member in members:
            # Convert member to string (Redis stores everything as strings)
            member_str = str(member) if not isinstance(member, str) else member
            if member_str not in self.store[key]:
                self.store[key].add(member_str)
                added += 1

        return added

    async def _smembers(self, key: str) -> set:
        """Get all members of a Redis set"""
        if key not in self.store:
            return set()

        if not isinstance(self.store[key], set):
            raise TypeError(f"Key {key} is not a set")

        return self.store[key].copy()

    async def _srem(self, key: str, *members: Any) -> int:
        """Remove members from a Redis set"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], set):
            raise TypeError(f"Key {key} is not a set")

        removed = 0
        for member in members:
            member_str = str(member) if not isinstance(member, str) else member
            if member_str in self.store[key]:
                self.store[key].remove(member_str)
                removed += 1

        # Remove key if set is empty
        if not self.store[key]:
            del self.store[key]

        return removed

    async def _sismember(self, key: str, member: Any) -> int:
        """Check if member is in a Redis set"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], set):
            raise TypeError(f"Key {key} is not a set")

        member_str = str(member) if not isinstance(member, str) else member
        return 1 if member_str in self.store[key] else 0

    async def _scard(self, key: str) -> int:
        """Get the number of members in a Redis set"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], set):
            raise TypeError(f"Key {key} is not a set")

        return len(self.store[key])

    async def _zadd(
        self, key: str, mapping: dict[Any, float], nx: bool = False, xx: bool = False
    ) -> int:
        """Add members to a sorted set with scores"""
        if key not in self.store:
            self.store[key] = {}
        elif not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        added = 0
        for member, score in mapping.items():
            member_str = str(member) if not isinstance(member, str) else member

            # nx: only add new elements, don't update existing
            if nx and member_str in self.store[key]:
                continue

            # xx: only update existing elements, don't add new
            if xx and member_str not in self.store[key]:
                continue

            # Add or update
            if member_str not in self.store[key]:
                added += 1

            self.store[key][member_str] = float(score)

        return added

    async def _zcard(self, key: str) -> int:
        """Get the number of members in a sorted set"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        return len(self.store[key])

    async def _zrem(self, key: str, *members: str) -> int:
        """Remove members from a sorted set"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        removed = 0
        for member in members:
            if member in self.store[key]:
                del self.store[key][member]
                removed += 1

        # Remove key if sorted set is empty
        if not self.store[key]:
            del self.store[key]
            if key in self.ttl_store:
                del self.ttl_store[key]

        return removed

    async def _zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        """Remove members from a sorted set within a score range"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        removed = 0
        members_to_remove = []

        for member, score in self.store[key].items():
            if min_score <= score <= max_score:
                members_to_remove.append(member)
                removed += 1

        for member in members_to_remove:
            del self.store[key][member]

        # Remove key if sorted set is empty
        if not self.store[key]:
            del self.store[key]
            if key in self.ttl_store:
                del self.ttl_store[key]

        return removed

    async def _zrange(self, key: str, start: int, stop: int, withscores: bool = False) -> list:
        """Get members from a sorted set by index range"""
        if key not in self.store:
            return []

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        # Sort by score
        sorted_items = sorted(self.store[key].items(), key=lambda x: x[1])

        # Handle negative indices
        length = len(sorted_items)
        if start < 0:
            start = max(0, length + start)
        stop = length + stop if stop < 0 else min(stop, length - 1)

        # Get the range
        result_items = sorted_items[start : stop + 1]

        if withscores:
            # Return list of tuples (member, score)
            return list(result_items)
        # Return just members
        return [member for member, _ in result_items]

    async def _zscore(self, key: str, member: Any) -> float | None:
        """Get the score of a member in a sorted set"""
        if key not in self.store:
            return None

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a sorted set")

        member_str = str(member) if not isinstance(member, str) else member
        return self.store[key].get(member_str)

    async def _lpush(self, key: str, *values: Any) -> int:
        """Push values onto the head of a list"""
        if key not in self.store:
            self.store[key] = []

        if not isinstance(self.store[key], list):
            raise TypeError(f"Key {key} is not a list")

        for value in reversed(values):
            self.store[key].insert(0, value)

        return len(self.store[key])

    async def _rpush(self, key: str, *values: Any) -> int:
        """Push values onto the tail of a list"""
        if key not in self.store:
            self.store[key] = []

        if not isinstance(self.store[key], list):
            raise TypeError(f"Key {key} is not a list")

        for value in values:
            self.store[key].append(value)

        return len(self.store[key])

    async def _lrange(self, key: str, start: int, stop: int) -> list:
        """Get a range of elements from a list"""
        if key not in self.store:
            return []

        if not isinstance(self.store[key], list):
            raise TypeError(f"Key {key} is not a list")

        lst = self.store[key]
        length = len(lst)

        if start < 0:
            start = max(0, length + start)
        if stop < 0:
            stop = length + stop

        return lst[start : stop + 1]

    async def _llen(self, key: str) -> int:
        """Get the length of a list"""
        if key not in self.store:
            return 0

        if not isinstance(self.store[key], list):
            raise TypeError(f"Key {key} is not a list")

        return len(self.store[key])

    async def _hset(
        self,
        key: str,
        field: str | None = None,
        value: Any = None,
        mapping: dict[str, Any] | None = None,
    ) -> int:
        """Set field(s) in a hash. Supports both single field/value and mapping."""
        if key not in self.store:
            self.store[key] = {}

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a hash")

        added = 0
        # Handle mapping (bulk set)
        if mapping:
            for f, v in mapping.items():
                is_new = f not in self.store[key]
                self.store[key][f] = str(v)
                if is_new:
                    added += 1
        # Handle single field/value
        elif field is not None:
            is_new = field not in self.store[key]
            self.store[key][field] = str(value)
            added = 1 if is_new else 0

        return added

    async def _hget(self, key: str, field: str) -> str | None:
        """Get a field from a hash"""
        if key not in self.store:
            return None

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a hash")

        return self.store[key].get(field)

    async def _hgetall(self, key: str) -> dict[str, str]:
        """Get all fields and values from a hash"""
        if key not in self.store:
            return {}

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a hash")

        return self.store[key].copy()

    async def _hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """Increment a hash field by the given amount"""
        if key not in self.store:
            self.store[key] = {}

        if not isinstance(self.store[key], dict):
            raise TypeError(f"Key {key} is not a hash")

        current = int(self.store[key].get(field, 0))
        new_value = current + amount
        self.store[key][field] = str(new_value)
        return new_value

    async def _incrby(self, key: str, amount: int = 1) -> int:
        """Increment a key by the given amount"""
        current = int(self.store.get(key, 0))
        new_value = current + amount
        self.store[key] = str(new_value)
        return new_value

    async def _incr(self, key: str) -> int:
        """Increment a key by 1"""
        return await self._incrby(key, 1)

    def _pipeline(self, transaction: bool = True):
        """Create a pipeline for batched operations"""
        return RedisPipelineMock(self, transaction)


class RedisPipelineMock:
    """Mock Redis pipeline for batched operations"""

    def __init__(self, redis_mock: StatefulRedisMock, transaction: bool):
        self.redis_mock = redis_mock
        self.transaction = transaction
        self.commands: list = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    def set(self, key: str, value: Any, ex: int | None = None, **kwargs):
        """Queue set command"""
        self.commands.append(("set", key, value, ex, kwargs))
        return self

    def get(self, key: str):
        """Queue get command"""
        self.commands.append(("get", key))
        return self

    def delete(self, *keys: str):
        """Queue delete command"""
        self.commands.append(("delete", *keys))
        return self

    def sadd(self, key: str, *members: Any):
        """Queue sadd command"""
        self.commands.append(("sadd", key, *members))
        return self

    def srem(self, key: str, *members: Any):
        """Queue srem command"""
        self.commands.append(("srem", key, *members))
        return self

    def smembers(self, key: str):
        """Queue smembers command"""
        self.commands.append(("smembers", key))
        return self

    def zadd(self, key: str, mapping: dict[Any, float], **kwargs):
        """Queue zadd command"""
        self.commands.append(("zadd", key, mapping, kwargs))
        return self

    def zcard(self, key: str):
        """Queue zcard command"""
        self.commands.append(("zcard", key))
        return self

    def zrem(self, key: str, *members: str):
        """Queue zrem command"""
        self.commands.append(("zrem", key, *members))
        return self

    def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        """Queue zremrangebyscore command"""
        self.commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def expire(self, key: str, seconds: int):
        """Queue expire command"""
        self.commands.append(("expire", key, seconds))
        return self

    async def execute(self) -> list:
        """Execute all queued commands"""
        results = []

        for command in self.commands:
            cmd_name = command[0]
            result: Any = None

            if cmd_name == "set":
                _, key, value, ex, kwargs = command
                result = await self.redis_mock._set(key, value, ex=ex)
            elif cmd_name == "get":
                _, key = command
                result = await self.redis_mock._get(key)
            elif cmd_name == "delete":
                keys = command[1:]
                result = await self.redis_mock._delete(*keys)
            elif cmd_name == "sadd":
                key = command[1]
                members = command[2:]
                result = await self.redis_mock._sadd(key, *members)
            elif cmd_name == "srem":
                key = command[1]
                members = command[2:]
                result = await self.redis_mock._srem(key, *members)
            elif cmd_name == "smembers":
                _, key = command
                result = await self.redis_mock._smembers(key)
            elif cmd_name == "zadd":
                _, key, mapping, kwargs = command
                result = await self.redis_mock._zadd(key, mapping, **kwargs)
            elif cmd_name == "zcard":
                _, key = command
                result = await self.redis_mock._zcard(key)
            elif cmd_name == "zrem":
                key = command[1]
                members = command[2:]
                result = await self.redis_mock._zrem(key, *members)
            elif cmd_name == "zremrangebyscore":
                _, key, min_score, max_score = command
                result = await self.redis_mock._zremrangebyscore(key, min_score, max_score)
            elif cmd_name == "expire":
                _, key, seconds = command
                result = await self.redis_mock._expire(key, seconds)
            else:
                result = None

            results.append(result)

        # Clear commands after execution
        self.commands.clear()

        return results


def create_stateful_redis_mock() -> StatefulRedisMock:
    """Factory function to create a new stateful Redis mock"""
    return StatefulRedisMock()
