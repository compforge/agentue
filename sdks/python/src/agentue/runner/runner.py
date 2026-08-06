"""Live/execute Runner with Redis bridging and stall recovery."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Generic, cast

from python_stdx.asyncio import EventLoopWatchdog
from python_stdx.redis import RedisConnector

from agentue.apply import PatchInput, apply_patch
from agentue.emitter import PatchEmitter
from agentue.event import PatchEvent, PatchOp, extract_patch_op
from agentue.model import UIModel
from agentue.runner.redis_bridge import AsyncRedisCommands, RedisEventBridge
from agentue.runner.types import (
    CompletionSource,
    DeliveryEvent,
    EventLoopStalledError,
    HeartbeatTimeoutError,
    RunnerCallbacks,
    RunnerCompletion,
    RunnerContext,
    RunnerOptions,
    TData,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TerminalEvent:
    data: str
    persisted: bool


@dataclass(frozen=True, slots=True)
class _ExecutionResult:
    terminal_events: tuple[_TerminalEvent, ...]


class Runner(Generic[TData]):
    """Own live delivery and background execution around four callbacks.

    ``pre_start`` runs in the live coroutine. ``prepare``, ``stream``, and
    ``complete`` run in the execute coroutine, which outlives a disconnected
    live consumer. Redis bridges both coroutines and lets another Runner
    instance recover a task whose execute event loop stops pulsing.
    """

    def __init__(
        self,
        redis: AsyncRedisCommands | RedisConnector,
        callbacks: RunnerCallbacks[TData],
        *,
        options: RunnerOptions | None = None,
    ) -> None:
        self._redis_source = redis
        self._callbacks = callbacks
        self._options = options or RunnerOptions()
        self._bridge: RedisEventBridge | None = None
        self._bridge_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._execute_tasks: set[asyncio.Task[_ExecutionResult]] = set()
        self._scanner_task: asyncio.Task[None] | None = None
        self._watchdog: EventLoopWatchdog | None = None
        self._pulse_task: asyncio.Task[None] | None = None
        self._loop_stalled = threading.Event()
        self._closing = False

    async def start(self) -> None:
        """Start the shared event-loop monitor and timeout scanner.

        ``run()`` calls this lazily. Applications should also call it during
        process startup so an otherwise idle instance can recover remote tasks.
        """
        async with self._start_lock:
            if self._closing:
                raise RuntimeError("Runner is closed")
            if self._loop_stalled.is_set():
                raise EventLoopStalledError("Runner event loop previously exceeded its stall timeout")
            await self._get_bridge()
            if self._watchdog is None:
                self._watchdog = EventLoopWatchdog(
                    timeout=self._options.heartbeat_timeout,
                    check_interval=self._options.watchdog_check_interval,
                    on_stall=lambda _: self._loop_stalled.set(),
                    thread_name="agentue-execute-watchdog",
                )
                self._watchdog.start()
                self._pulse_task = asyncio.create_task(self._pulse_loop(), name="agentue-loop-pulse")
            self._ensure_scanner()

    async def run(
        self,
        *,
        task_id: str,
        data: TData,
        model: UIModel,
        cursor: str = "0-0",
    ) -> AsyncIterator[DeliveryEvent]:
        """Start one task and yield transport-neutral live events.

        Closing this async generator only closes live delivery; the execute
        coroutine remains owned by Runner until it completes or Runner closes.
        """
        context = RunnerContext(task_id=task_id, data=data, model=model)
        try:
            await self.start()
            bridge = await self._get_bridge()
            await bridge.initialize(task_id, model.model_dump_json(exclude_none=True, serialize_as_any=True))
        except BaseException as error:
            await self._invoke_complete(
                RunnerCompletion(
                    task_id=task_id,
                    source=CompletionSource.PRE_START,
                    context=context,
                    error=error,
                    snapshot=None,
                )
            )
            raise

        try:
            await self._callbacks.pre_start(context)
            await self._publish_start(context)
        except BaseException as error:
            if context.published_seq == 0:
                await self._publish_start_best_effort(context)
            result = await self._finalize(context, CompletionSource.PRE_START, error)
            if isinstance(error, asyncio.CancelledError):
                raise
            execution = asyncio.get_running_loop().create_future()
            execution.set_result(result)
        else:
            execution = self._spawn_execute(context)

        async for event in self._stream_live(context, execution, cursor):
            yield event

    async def recover_timeouts(self) -> int:
        """Recover every expired heartbeat claimed by this Runner instance."""
        bridge = await self._get_bridge()
        recovered = 0
        for task_id in await bridge.expired_task_ids():
            if not await bridge.claim_recovery(task_id):
                continue
            try:
                if await bridge.status(task_id) != "running":
                    await bridge.forget_heartbeat(task_id)
                    continue
                await self._recover_task(task_id)
                recovered += 1
            finally:
                await bridge.release_recovery(task_id)
        return recovered

    async def aclose(self) -> None:
        """Stop recovery scanning and cancel owned execute tasks gracefully."""
        self._closing = True
        scanner, self._scanner_task = self._scanner_task, None
        if scanner is not None:
            scanner.cancel()
        tasks = list(self._execute_tasks)
        for task in tasks:
            task.cancel()
        if scanner is not None:
            await asyncio.gather(scanner, return_exceptions=True)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        pulse, self._pulse_task = self._pulse_task, None
        if pulse is not None:
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
        watchdog, self._watchdog = self._watchdog, None
        if watchdog is not None:
            watchdog.stop(join_timeout=self._options.watchdog_check_interval * 2)
        if isinstance(self._redis_source, RedisConnector):
            await self._redis_source.aclose()
        self._bridge = None

    async def _get_bridge(self) -> RedisEventBridge:
        async with self._bridge_lock:
            if self._bridge is not None:
                return self._bridge
            if isinstance(self._redis_source, RedisConnector):
                redis = cast(AsyncRedisCommands, await self._redis_source.connect())
            else:
                redis = self._redis_source
            self._bridge = RedisEventBridge(redis, self._options)
            return self._bridge

    def _ensure_scanner(self) -> None:
        if self._scanner_task is None or self._scanner_task.done():
            self._scanner_task = asyncio.create_task(self._scan_forever(), name="agentue-timeout-scanner")

    def _spawn_execute(self, context: RunnerContext[TData]) -> asyncio.Task[_ExecutionResult]:
        task = asyncio.create_task(self._execute(context), name=f"agentue-execute-{context.task_id}")
        self._execute_tasks.add(task)
        task.add_done_callback(self._execute_tasks.discard)
        return task

    async def _execute(self, context: RunnerContext[TData]) -> _ExecutionResult:
        pulse_task = self._pulse_task
        if pulse_task is None:
            raise RuntimeError("Runner must be started before execute")
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(context.task_id))
        business_task = asyncio.create_task(self._run_business(context))

        error: BaseException | None = None
        source = CompletionSource.EXECUTE
        try:
            done, _ = await asyncio.wait(
                {business_task, pulse_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._loop_stalled.is_set():
                error = EventLoopStalledError("execute event loop stopped advancing")
                source = CompletionSource.HEARTBEAT_TIMEOUT
            elif pulse_task in done:
                error = (
                    EventLoopStalledError("execute pulse stopped")
                    if pulse_task.cancelled()
                    else pulse_task.exception() or EventLoopStalledError("execute pulse stopped")
                )
                source = CompletionSource.HEARTBEAT_TIMEOUT
            elif heartbeat_task in done:
                error = heartbeat_task.exception() or RuntimeError("Redis heartbeat stopped")
            else:
                error = business_task.exception()
        except asyncio.CancelledError as cancelled:
            error = cancelled
            source = CompletionSource.SHUTDOWN if self._closing else CompletionSource.CANCELLED
        except BaseException as unexpected:
            error = unexpected
        finally:
            if not business_task.done():
                business_task.cancel()
                await asyncio.gather(business_task, return_exceptions=True)

        try:
            return await self._finalize(context, source, error)
        finally:
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _run_business(self, context: RunnerContext[TData]) -> None:
        await self._callbacks.prepare(context)
        async for patch in self._callbacks.stream(context):
            event = _coerce_patch(patch)
            if event.op not in {PatchOp.SET, PatchOp.APPEND}:
                raise ValueError("stream callback may only yield set and append operations")
            if event.seq <= context.published_seq:
                raise ValueError("stream event seq must increase")
            event_json = event.to_json()
            context.snapshot = apply_patch(context.snapshot, event)
            await (await self._get_bridge()).publish(context.task_id, event_json, event.seq)
            context.published_seq = event.seq

    async def _pulse_loop(self) -> None:
        watchdog = self._watchdog
        if watchdog is None:
            raise RuntimeError("Runner watchdog is not initialized")
        interval = min(self._options.heartbeat_interval, self._options.heartbeat_timeout / 3)
        while True:
            if self._loop_stalled.is_set():
                raise EventLoopStalledError("execute event loop recovered after exceeding its stall timeout")
            watchdog.pulse()
            await asyncio.sleep(interval)

    async def _heartbeat_loop(self, task_id: str) -> None:
        bridge = await self._get_bridge()
        while True:
            if self._loop_stalled.is_set():
                raise EventLoopStalledError("execute event loop heartbeat expired")
            await bridge.touch(task_id)
            await asyncio.sleep(self._options.heartbeat_interval)

    async def _publish_start(self, context: RunnerContext[TData]) -> None:
        event_json = context.emitter.start(context.model)
        event = PatchEvent.model_validate_json(event_json)
        context.snapshot = apply_patch(context.snapshot, event)
        await (await self._get_bridge()).publish(context.task_id, event_json, event.seq)
        context.published_seq = event.seq

    async def _publish_start_best_effort(self, context: RunnerContext[TData]) -> None:
        try:
            await self._publish_start(context)
        except Exception:
            logger.exception("failed to persist start event: task_id=%s", context.task_id)

    async def _finalize(
        self,
        context: RunnerContext[TData],
        source: CompletionSource,
        error: BaseException | None,
    ) -> _ExecutionResult:
        completion_error = await self._invoke_complete(
            RunnerCompletion(
                task_id=context.task_id,
                source=source,
                context=context,
                error=error,
                snapshot=context.snapshot,
            )
        )
        effective_error = error or completion_error
        terminal_events: list[_TerminalEvent] = []

        if effective_error is not None:
            error_json = context.emitter.error(
                _error_code(effective_error, source),
                _error_message(effective_error, source),
            )
            persisted = await self._publish_terminal(context, error_json)
            terminal_events.append(_TerminalEvent(error_json, persisted))
        else:
            persisted = True

        end_json = context.emitter.end()
        end_persisted = await self._publish_terminal(context, end_json) if persisted else False
        terminal_events.append(_TerminalEvent(end_json, end_persisted))

        try:
            await (await self._get_bridge()).mark_terminal(
                context.task_id,
                "failed" if effective_error is not None else "completed",
            )
        except Exception:
            logger.exception("failed to persist terminal task status: task_id=%s", context.task_id)
        return _ExecutionResult(tuple(terminal_events))

    async def _publish_terminal(self, context: RunnerContext[TData], event_json: str) -> bool:
        try:
            event = PatchEvent.model_validate_json(event_json)
            await (await self._get_bridge()).publish(context.task_id, event_json, event.seq)
            context.published_seq = event.seq
            return True
        except Exception:
            logger.exception("failed to persist terminal event: task_id=%s", context.task_id)
            return False

    async def _invoke_complete(self, completion: RunnerCompletion[TData]) -> BaseException | None:
        try:
            await self._callbacks.complete(completion)
        except BaseException as error:
            logger.exception("Runner complete callback failed: task_id=%s", completion.task_id)
            return error
        return None

    async def _stream_live(
        self,
        context: RunnerContext[TData],
        execution: asyncio.Future[_ExecutionResult],
        cursor: str,
    ) -> AsyncIterator[DeliveryEvent]:
        bridge = await self._get_bridge()
        delivered_control_ops: set[str] = set()
        current_cursor = cursor
        while True:
            stored = await bridge.read(context.task_id, current_cursor)
            if stored:
                for item in stored:
                    current_cursor = item.cursor
                    op = extract_patch_op(item.data)
                    if op in {PatchOp.START.value, PatchOp.ERROR.value, PatchOp.END.value}:
                        delivered_control_ops.add(op)
                    yield DeliveryEvent(data=item.data, cursor=item.cursor, persisted=True)
                    if op == PatchOp.END.value:
                        return
                continue

            if execution.done():
                result = execution.result()
                for terminal in result.terminal_events:
                    op = extract_patch_op(terminal.data)
                    if not terminal.persisted and op not in delivered_control_ops:
                        yield DeliveryEvent(data=terminal.data, cursor=None, persisted=False)
                return

            yield DeliveryEvent(data=context.emitter.ping(), cursor=None, persisted=False)

    async def _recover_task(self, task_id: str) -> None:
        bridge = await self._get_bridge()
        error = HeartbeatTimeoutError("execute event loop heartbeat expired")
        completion = RunnerCompletion[TData](
            task_id=task_id,
            source=CompletionSource.HEARTBEAT_TIMEOUT,
            context=None,
            error=error,
            snapshot=None,
        )
        await self._invoke_complete(completion)

        emitter_offset = await bridge.last_seq(task_id)
        emitter = PatchEmitter(emitter_offset)
        if emitter_offset == 0:
            initial_model = await bridge.initial_model(task_id)
            if initial_model is not None:
                start_json = emitter.start(UIModel.model_validate_json(initial_model))
                await bridge.publish(task_id, start_json, emitter.offset)
        error_json = emitter.error("heartbeat_timeout", str(error))
        await bridge.publish(task_id, error_json, emitter.offset)
        end_json = emitter.end()
        await bridge.publish(task_id, end_json, emitter.offset)
        await bridge.mark_terminal(task_id, "failed")

    async def _scan_forever(self) -> None:
        while True:
            try:
                await self.recover_timeouts()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Runner timeout scan failed")
            await asyncio.sleep(self._options.scan_interval)


def _coerce_patch(patch: PatchInput) -> PatchEvent:
    if isinstance(patch, PatchEvent):
        return patch
    if isinstance(patch, str):
        return PatchEvent.model_validate_json(patch)
    return PatchEvent.model_validate(dict(patch))


def _error_code(error: BaseException, source: CompletionSource) -> str:
    if source is CompletionSource.HEARTBEAT_TIMEOUT:
        return "heartbeat_timeout"
    if isinstance(error, asyncio.CancelledError):
        return "cancelled"
    return type(error).__name__.removesuffix("Error").lower() or "failed"


def _error_message(error: BaseException, source: CompletionSource) -> str:
    message = str(error).strip()
    if message:
        return message
    if source is CompletionSource.SHUTDOWN:
        return "Runner shut down before the task completed."
    if isinstance(error, asyncio.CancelledError):
        return "Task execution was cancelled."
    return "Task execution failed."
