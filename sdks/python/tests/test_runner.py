import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from agentue.runner import (
    CompletionSource,
    HeartbeatTimeoutError,
    RedisEventBridge,
    Runner,
    RunnerCallbacks,
    RunnerCompletion,
    RunnerContext,
    RunnerOptions,
)
from agentue.ui import BaseBlock, ModelMeta, PatchEmitter, UIModel


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.strings: dict[str, str] = {}
        self.changed = asyncio.Event()

    async def delete(self, *names: str) -> int:
        deleted = 0
        for name in names:
            deleted += int(self.strings.pop(name, None) is not None)
        return deleted

    async def expire(self, name: str, seconds: int) -> bool:
        return name in self.hashes or name in self.streams or name in self.strings

    async def hget(self, name: str, key: str) -> str | None:
        return self.hashes.get(name, {}).get(key)

    async def hset(self, name: str, *args: Any, **kwargs: Any) -> int:
        mapping = kwargs.get("mapping", {})
        self.hashes.setdefault(name, {}).update({str(key): str(value) for key, value in mapping.items()})
        return len(mapping)

    async def set(self, name: str, value: str, **kwargs: Any) -> bool:
        if kwargs.get("nx") and name in self.strings:
            return False
        self.strings[name] = value
        return True

    async def xadd(self, name: str, fields: Mapping[str, str]) -> str:
        stream = self.streams.setdefault(name, [])
        event_id = f"{len(stream) + 1}-0"
        stream.append((event_id, dict(fields)))
        self.changed.set()
        return event_id

    async def xread(self, streams: Mapping[str, str], **kwargs: Any) -> list[Any]:
        name, cursor = next(iter(streams.items()))
        entries = self._entries_after(name, cursor)
        if not entries:
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=kwargs.get("block", 1) / 1000)
            except TimeoutError:
                return []
            entries = self._entries_after(name, cursor)
        count = int(kwargs.get("count", len(entries)))
        return [(name, entries[:count])] if entries else []

    async def zadd(self, name: str, mapping: Mapping[str, float]) -> int:
        self.zsets.setdefault(name, {}).update(mapping)
        return len(mapping)

    async def zrangebyscore(self, name: str, minimum: float | str, maximum: float | str) -> list[str]:
        lower = float("-inf") if minimum == "-inf" else float(minimum)
        upper = float("inf") if maximum == "+inf" else float(maximum)
        return [member for member, score in self.zsets.get(name, {}).items() if lower <= score <= upper]

    async def zrem(self, name: str, *values: str) -> int:
        removed = 0
        for value in values:
            removed += int(self.zsets.get(name, {}).pop(value, None) is not None)
        return removed

    def _entries_after(self, name: str, cursor: str) -> list[tuple[str, dict[str, str]]]:
        cursor_number = int(cursor.split("-", 1)[0])
        return [entry for entry in self.streams.get(name, []) if int(entry[0].split("-", 1)[0]) > cursor_number]


def options() -> RunnerOptions:
    return RunnerOptions(
        stream_block_ms=10,
        heartbeat_interval=0.02,
        heartbeat_timeout=0.2,
        watchdog_check_interval=0.01,
        scan_interval=10.0,
    )


def model() -> UIModel:
    return UIModel(biz="test", meta=ModelMeta())


@pytest.mark.asyncio
async def test_runner_executes_four_phases_and_streams_terminal_end():
    calls: list[str] = []
    completion: RunnerCompletion[dict[str, str]] | None = None

    async def pre_start(context: RunnerContext[dict[str, str]]) -> None:
        calls.append("pre_start")

    async def prepare(context: RunnerContext[dict[str, str]]) -> None:
        calls.append("prepare")

    async def stream(context: RunnerContext[dict[str, str]]) -> AsyncIterator[str]:
        calls.append("stream")
        yield context.emitter.block_append(BaseBlock(id="answer", type="text", content="hello"))

    async def complete(result: RunnerCompletion[dict[str, str]]) -> None:
        nonlocal completion
        calls.append("complete")
        completion = result

    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=pre_start, prepare=prepare, stream=stream, complete=complete),
        options=options(),
    )
    events = [event async for event in runner.run(task_id="task-1", data={"input": "hi"}, model=model())]
    await runner.aclose()

    assert calls == ["pre_start", "prepare", "stream", "complete"]
    assert [json.loads(event.data)["op"] for event in events] == ["start", "append", "end"]
    assert completion is not None
    assert completion.source is CompletionSource.EXECUTE
    assert completion.error is None
    assert completion.snapshot is not None
    assert completion.snapshot["blocks"][0]["content"] == "hello"


@pytest.mark.asyncio
async def test_prepare_failure_is_reported_to_complete_before_error_and_end():
    completion: RunnerCompletion[None] | None = None

    async def phase(context: RunnerContext[None]) -> None:
        return None

    async def prepare(context: RunnerContext[None]) -> None:
        raise RuntimeError("prepare failed")

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def complete(result: RunnerCompletion[None]) -> None:
        nonlocal completion
        completion = result

    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=phase, prepare=prepare, stream=stream, complete=complete),
        options=options(),
    )
    events = [event async for event in runner.run(task_id="task-2", data=None, model=model())]
    await runner.aclose()

    assert completion is not None
    assert isinstance(completion.error, RuntimeError)
    assert [json.loads(event.data)["op"] for event in events] == ["start", "error", "end"]


@pytest.mark.asyncio
async def test_pre_start_failure_still_runs_complete_and_valid_control_sequence():
    phases: list[str] = []

    async def pre_start(context: RunnerContext[None]) -> None:
        phases.append("pre_start")
        raise RuntimeError("could not create task")

    async def prepare(context: RunnerContext[None]) -> None:
        phases.append("prepare")

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        phases.append("stream")
        if False:
            yield ""

    async def complete(result: RunnerCompletion[None]) -> None:
        phases.append("complete")

    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=pre_start, prepare=prepare, stream=stream, complete=complete),
        options=options(),
    )
    events = [event async for event in runner.run(task_id="task-3", data=None, model=model())]
    await runner.aclose()

    assert phases == ["pre_start", "complete"]
    assert [json.loads(event.data)["op"] for event in events] == ["start", "error", "end"]


@pytest.mark.asyncio
async def test_live_disconnect_does_not_cancel_execute():
    stream_started = asyncio.Event()
    release_stream = asyncio.Event()
    completed = asyncio.Event()

    async def phase(context: RunnerContext[None]) -> None:
        return None

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        stream_started.set()
        await release_stream.wait()
        yield context.emitter.block_append(BaseBlock(id="answer", type="text", content="done"))

    async def complete(result: RunnerCompletion[None]) -> None:
        completed.set()

    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=phase, prepare=phase, stream=stream, complete=complete),
        options=options(),
    )
    live = runner.run(task_id="task-4", data=None, model=model())
    first = await anext(live)
    assert json.loads(first.data)["op"] == "start"
    await stream_started.wait()
    await live.aclose()

    release_stream.set()
    await asyncio.wait_for(completed.wait(), timeout=1.0)
    await runner.aclose()


@pytest.mark.asyncio
async def test_timeout_recovery_uses_complete_without_in_memory_context():
    redis = FakeRedis()
    recovered: RunnerCompletion[None] | None = None

    async def phase(context: RunnerContext[None]) -> None:
        return None

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def complete(result: RunnerCompletion[None]) -> None:
        nonlocal recovered
        recovered = result

    runner_options = options()
    bridge = RedisEventBridge(redis, runner_options)
    initial_model = model()
    emitter = PatchEmitter()
    await bridge.initialize("expired-task", initial_model.model_dump_json())
    start = emitter.start(initial_model)
    await bridge.publish("expired-task", start, emitter.offset)
    redis.zsets[f"{runner_options.key_prefix}:heartbeats"]["expired-task"] = 0

    runner = Runner(
        redis,
        RunnerCallbacks(pre_start=phase, prepare=phase, stream=stream, complete=complete),
        options=runner_options,
    )
    assert await runner.recover_timeouts() == 1
    stored = await bridge.read("expired-task", "0-0")
    await runner.aclose()

    assert recovered is not None
    assert recovered.context is None
    assert recovered.source is CompletionSource.HEARTBEAT_TIMEOUT
    assert isinstance(recovered.error, HeartbeatTimeoutError)
    assert [json.loads(event.data)["op"] for event in stored] == ["start", "error", "end"]


@pytest.mark.asyncio
async def test_runner_close_cancels_execute_but_still_calls_complete():
    stream_started = asyncio.Event()
    never = asyncio.Event()
    completed = asyncio.Event()
    completion: RunnerCompletion[None] | None = None

    async def phase(context: RunnerContext[None]) -> None:
        return None

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        stream_started.set()
        await never.wait()
        if False:
            yield ""

    async def complete(result: RunnerCompletion[None]) -> None:
        nonlocal completion
        completion = result
        completed.set()

    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=phase, prepare=phase, stream=stream, complete=complete),
        options=options(),
    )
    live = runner.run(task_id="task-5", data=None, model=model())
    await anext(live)
    await stream_started.wait()

    await runner.aclose()
    await asyncio.wait_for(completed.wait(), timeout=1.0)
    await live.aclose()

    assert completion is not None
    assert completion.source is CompletionSource.SHUTDOWN
    assert isinstance(completion.error, asyncio.CancelledError)


@pytest.mark.asyncio
async def test_independent_watchdog_detects_a_stalled_execute_event_loop():
    completion: RunnerCompletion[None] | None = None

    async def phase(context: RunnerContext[None]) -> None:
        return None

    async def stream(context: RunnerContext[None]) -> AsyncIterator[str]:
        # time.sleep releases the GIL but blocks this event loop, allowing only
        # the watchdog's independent OS thread to observe the stale pulse.
        time.sleep(0.1)
        yield context.emitter.block_append(BaseBlock(id="answer", type="text", content="late"))

    async def complete(result: RunnerCompletion[None]) -> None:
        nonlocal completion
        completion = result

    stalled_options = RunnerOptions(
        stream_block_ms=10,
        heartbeat_interval=0.01,
        heartbeat_timeout=0.04,
        watchdog_check_interval=0.005,
        scan_interval=10.0,
    )
    runner = Runner(
        FakeRedis(),
        RunnerCallbacks(pre_start=phase, prepare=phase, stream=stream, complete=complete),
        options=stalled_options,
    )
    events = [event async for event in runner.run(task_id="task-6", data=None, model=model())]
    await runner.aclose()

    assert completion is not None
    assert completion.source is CompletionSource.HEARTBEAT_TIMEOUT
    assert [json.loads(event.data)["op"] for event in events][-2:] == ["error", "end"]
