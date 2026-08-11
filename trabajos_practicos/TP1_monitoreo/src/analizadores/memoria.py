from __future__ import annotations

from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop

VIEW = "memoria"
MIN_INTERVAL = 1.0


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    processes: dict[str, Any] = {}
    for pid in pids:
        status = procfs.read_status(pid, proc_root)
        stat = procfs.read_stat(pid, proc_root)
        if status is None or stat is None:
            continue
        processes[str(pid)] = {
            "pid": pid,
            "comm": stat["comm"],
            "memoria_kb": procfs.process_memory_from_status(status),
            "faults": {
                "minor": stat["minflt"],
                "children_minor": stat["cminflt"],
                "major": stat["majflt"],
                "children_major": stat["cmajflt"],
            },
            "segmentos_kb": procfs.read_memory_segments(pid, proc_root),
        }
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
