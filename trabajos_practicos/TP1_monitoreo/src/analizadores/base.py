from __future__ import annotations

import os
import queue
import time
from multiprocessing.synchronize import Event as EventType
from typing import Any, Callable


Collector = Callable[[list[int], dict[str, Any], str], dict[str, Any]]


def drain_latest_pids(input_queue: Any, current: list[int]) -> list[int]:
    latest = current
    while True:
        try:
            message = input_queue.get_nowait()
        except queue.Empty:
            return latest
        if isinstance(message, dict) and message.get("type") == "pids":
            latest = list(message.get("pids", []))


def read_interval(interval_value: Any, minimum: float) -> float:
    try:
        with interval_value.get_lock():
            value = float(interval_value.value)
    except AttributeError:
        value = float(interval_value.value)
    return max(minimum, value)


def offer_message(output_queue: Any, message: dict[str, Any]) -> None:
    try:
        output_queue.put(message, timeout=0.2)
    except queue.Full:
        pass


def prune_state_map(state_map: dict[Any, Any], active_keys: set[Any]) -> None:
    for key in list(state_map):
        if key not in active_keys:
            state_map.pop(key, None)


def analyzer_loop(
    view: str,
    minimum_interval: float,
    input_queue: Any,
    output_queue: Any,
    interval_value: Any,
    stop_event: EventType,
    proc_root: str,
    collector: Collector,
) -> None:
    state: dict[str, Any] = {"pid_ticks": {}, "thread_ticks": {}, "cpu_total": None}
    pids: list[int] = []
    next_run = 0.0
    pid = os.getpid()

    while not stop_event.is_set():
        pids = drain_latest_pids(input_queue, pids)
        now = time.monotonic()
        if pids and now >= next_run:
            started = time.time()
            try:
                data = collector(pids, state, proc_root)
                error = None
            except Exception as exc:  # pragma: no cover - defensa ante /proc cambiante.
                data = {}
                error = f"{type(exc).__name__}: {exc}"

            interval = read_interval(interval_value, minimum_interval)
            offer_message(
                output_queue,
                {
                    "view": view,
                    "pid": pid,
                    "ts": started,
                    "interval": interval,
                    "duration_ms": round((time.time() - started) * 1000.0, 2),
                    "data": data,
                    "error": error,
                },
            )
            next_run = now + interval
        stop_event.wait(0.05)
