"""Redis Streams event bridge and durable heartbeat index."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from agentue.runner.types import RunnerOptions


class AsyncRedisCommands(Protocol):
    """The Redis command subset used by Runner."""

    def delete(self, *names: str) -> Awaitable[Any]: ...

    def expire(self, name: str, seconds: int) -> Awaitable[Any]: ...

    def hget(self, name: str, key: str) -> Awaitable[Any]: ...

    def hset(self, name: str, *args: Any, **kwargs: Any) -> Awaitable[Any]: ...

    def set(self, name: str, value: str, **kwargs: Any) -> Awaitable[Any]: ...

    def xadd(self, name: str, fields: Mapping[str, str]) -> Awaitable[Any]: ...

    def xread(self, streams: Mapping[str, str], **kwargs: Any) -> Awaitable[Any]: ...

    def zadd(self, name: str, mapping: Mapping[str, float]) -> Awaitable[Any]: ...

    def zrangebyscore(self, name: str, minimum: float | str, maximum: float | str) -> Awaitable[Any]: ...

    def zrem(self, name: str, *values: str) -> Awaitable[Any]: ...


@dataclass(frozen=True, slots=True)
class StoredEvent:
    cursor: str
    data: str


class RedisEventBridge:
    """Persist Runner events and liveness without owning the Redis client."""

    def __init__(
        self,
        redis: AsyncRedisCommands,
        options: RunnerOptions,
        *,
        wall_clock: Any = time.time,
    ) -> None:
        self._redis = redis
        self._options = options
        self._wall_clock = wall_clock

    async def initialize(self, task_id: str, initial_model: str) -> None:
        await self._redis.hset(
            self._state_key(task_id),
            mapping={"status": "running", "last_seq": "0", "initial_model": initial_model},
        )
        await self._redis.expire(self._state_key(task_id), self._options.task_ttl)
        await self.touch(task_id)

    async def publish(self, task_id: str, event_json: str, seq: int) -> str:
        event_id = await self._redis.xadd(self._stream_key(task_id), {"event": event_json})
        await self._redis.expire(self._stream_key(task_id), self._options.task_ttl)
        await self._redis.hset(self._state_key(task_id), mapping={"last_seq": str(seq)})
        return _text(event_id)

    async def read(self, task_id: str, cursor: str) -> list[StoredEvent]:
        response = await self._redis.xread(
            {self._stream_key(task_id): cursor},
            count=self._options.stream_read_count,
            block=self._options.stream_block_ms,
        )
        events: list[StoredEvent] = []
        for _, messages in response or []:
            for event_id, fields in messages:
                payload = fields.get("event") if isinstance(fields, dict) else None
                if payload is None and isinstance(fields, dict):
                    payload = fields.get(b"event")
                if payload is None:
                    continue
                events.append(StoredEvent(cursor=_text(event_id), data=_text(payload)))
        return events

    async def touch(self, task_id: str) -> None:
        await self._redis.zadd(self._heartbeat_key, {task_id: self._wall_clock()})

    async def expired_task_ids(self) -> list[str]:
        cutoff = self._wall_clock() - self._options.heartbeat_timeout
        values = await self._redis.zrangebyscore(self._heartbeat_key, "-inf", cutoff)
        return [_text(value) for value in values]

    async def claim_recovery(self, task_id: str) -> bool:
        claimed = await self._redis.set(
            self._claim_key(task_id),
            "1",
            nx=True,
            ex=self._options.recovery_claim_ttl,
        )
        return bool(claimed)

    async def release_recovery(self, task_id: str) -> None:
        await self._redis.delete(self._claim_key(task_id))

    async def status(self, task_id: str) -> str | None:
        value = await self._redis.hget(self._state_key(task_id), "status")
        return _text(value) if value is not None else None

    async def last_seq(self, task_id: str) -> int:
        value = await self._redis.hget(self._state_key(task_id), "last_seq")
        return int(_text(value)) if value is not None else 0

    async def initial_model(self, task_id: str) -> str | None:
        value = await self._redis.hget(self._state_key(task_id), "initial_model")
        return _text(value) if value is not None else None

    async def mark_terminal(self, task_id: str, status: str) -> None:
        await self._redis.hset(self._state_key(task_id), mapping={"status": status})
        await self._redis.expire(self._state_key(task_id), self._options.task_ttl)
        await self._redis.zrem(self._heartbeat_key, task_id)

    async def forget_heartbeat(self, task_id: str) -> None:
        await self._redis.zrem(self._heartbeat_key, task_id)

    @property
    def _heartbeat_key(self) -> str:
        return f"{self._options.key_prefix}:heartbeats"

    def _stream_key(self, task_id: str) -> str:
        return f"{self._options.key_prefix}:{task_id}:events"

    def _state_key(self, task_id: str) -> str:
        return f"{self._options.key_prefix}:{task_id}:state"

    def _claim_key(self, task_id: str) -> str:
        return f"{self._options.key_prefix}:{task_id}:recovery-claim"


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
