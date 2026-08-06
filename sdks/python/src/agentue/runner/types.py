"""Public Runner lifecycle contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from agentue.apply import PatchInput
from agentue.emitter import PatchEmitter
from agentue.model import UIModel

TData = TypeVar("TData")


class CompletionSource(str, Enum):
    """Why Runner entered the guaranteed completion phase."""

    PRE_START = "pre_start"
    EXECUTE = "execute"
    CANCELLED = "cancelled"
    SHUTDOWN = "shutdown"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"


@dataclass
class RunnerContext(Generic[TData]):
    """Mutable state shared by the four application callbacks."""

    task_id: str
    data: TData
    model: UIModel
    emitter: PatchEmitter = field(default_factory=PatchEmitter)
    snapshot: dict[str, Any] = field(default_factory=dict)
    published_seq: int = 0


@dataclass(frozen=True)
class RunnerCompletion(Generic[TData]):
    """Facts passed to ``complete`` for normal, failed, and recovered runs.

    ``context`` is unavailable when a different process recovers an expired
    heartbeat. Completion code must therefore be idempotent and able to recover
    durable state by ``task_id``.
    """

    task_id: str
    source: CompletionSource
    context: RunnerContext[TData] | None
    error: BaseException | None
    snapshot: dict[str, Any] | None


RunnerPhase = Callable[[RunnerContext[TData]], Awaitable[None]]
RunnerStream = Callable[[RunnerContext[TData]], AsyncIterator[PatchInput]]
RunnerComplete = Callable[[RunnerCompletion[TData]], Awaitable[None]]


@dataclass(frozen=True)
class RunnerCallbacks(Generic[TData]):
    """The only four application-defined phases in a Runner lifecycle."""

    pre_start: RunnerPhase[TData]
    prepare: RunnerPhase[TData]
    stream: RunnerStream[TData]
    complete: RunnerComplete[TData]


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Infrastructure timing, capacity, and Redis key settings."""

    key_prefix: str = "agentue:runner"
    task_ttl: int = 86_400
    stream_read_count: int = 100
    stream_block_ms: int = 1_000
    heartbeat_interval: float = 5.0
    heartbeat_timeout: float = 30.0
    watchdog_check_interval: float = 1.0
    scan_interval: float = 5.0
    recovery_claim_ttl: int = 60

    def __post_init__(self) -> None:
        if not self.key_prefix:
            raise ValueError("key_prefix must not be empty")
        for name in ("task_ttl", "stream_read_count", "stream_block_ms", "recovery_claim_ttl"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("heartbeat_interval", "heartbeat_timeout", "watchdog_check_interval", "scan_interval"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.heartbeat_timeout <= self.heartbeat_interval:
            raise ValueError("heartbeat_timeout must be greater than heartbeat_interval")


@dataclass(frozen=True, slots=True)
class DeliveryEvent:
    """One event delivered to a live transport."""

    data: str
    cursor: str | None
    persisted: bool


class EventLoopStalledError(RuntimeError):
    """The execute event loop stopped advancing its watchdog pulse."""


class HeartbeatTimeoutError(TimeoutError):
    """A healthy Runner instance recovered an expired task heartbeat."""
