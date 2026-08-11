from __future__ import annotations

import os
from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop, prune_state_map

VIEW = "resumen"
MIN_INTERVAL = 0.5


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    total_jiffies = procfs.read_total_jiffies(proc_root)
    cpu_count = os.cpu_count() or 1
    previous: dict[tuple[int, int], tuple[int, int]] = state.setdefault("pid_ticks", {})
    active: set[tuple[int, int]] = set()
    processes = []

    for pid in pids:
        identity = procfs.process_identity(pid, proc_root)
        stat = procfs.read_stat(pid, proc_root)
        if identity is None or stat is None:
            continue
        ticks = procfs.process_ticks(stat)
        key = (pid, stat["starttime"])
        active.add(key)
        old = previous.get(key)
        cpu = procfs.calc_cpu_percent(
            old[0] if old else None,
            ticks,
            old[1] if old else None,
            total_jiffies,
            cpu_count,
        )
        previous[key] = (ticks, total_jiffies)
        identity.update(
            {
                "cpu": cpu,
                "utime": stat["utime"],
                "stime": stat["stime"],
                "nice": stat["nice"],
                "priority": stat["priority"],
            }
        )
        processes.append(identity)

    prune_state_map(previous, active)
    processes.sort(key=lambda item: (-item["cpu"], -item["rss_kb"], item["pid"]))
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
