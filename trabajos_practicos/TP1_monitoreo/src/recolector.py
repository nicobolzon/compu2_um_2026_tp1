from __future__ import annotations

import queue
import time
from typing import Any

from src import procfs


def offer_latest(target_queue: Any, message: dict[str, Any]) -> None:
    try:
        target_queue.put_nowait(message)
        return
    except queue.Full:
        pass

    try:
        target_queue.get_nowait()
    except queue.Empty:
        pass

    try:
        target_queue.put_nowait(message)
    except queue.Full:
        pass


def run(analyzer_queues: dict[str, Any], stop_event: Any, proc_root: str, interval: float = 0.5) -> None:
    while not stop_event.is_set():
        pids = procfs.list_pids(proc_root)
        message = {"type": "pids", "pids": pids, "ts": time.time()}
        for target_queue in analyzer_queues.values():
            offer_latest(target_queue, message)
        stop_event.wait(interval)
