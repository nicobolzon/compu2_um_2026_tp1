from __future__ import annotations

from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop

VIEW = "fds"
MIN_INTERVAL = 2.0


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    processes: dict[str, Any] = {}
    for pid in pids:
        stat = procfs.read_stat(pid, proc_root)
        if stat is None:
            continue
        fds = procfs.read_fds(pid, proc_root)
        processes[str(pid)] = {
            "pid": pid,
            "comm": stat["comm"],
            "fds": fds["items"],
            "error": fds["error"],
            "total": len(fds["items"]),
        }
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
