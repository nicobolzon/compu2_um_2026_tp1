from __future__ import annotations

import os
from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop, prune_state_map

VIEW = "sistema"
MIN_INTERVAL = 1.0


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    current_cpu = procfs.read_global_cpu_times(proc_root)
    previous_cpu = state.get("global_cpu")
    cpu_percentages = procfs.cpu_delta_percentages(previous_cpu, current_cpu)
    state["global_cpu"] = current_cpu

    total_jiffies = sum(current_cpu.values())
    cpu_count = os.cpu_count() or 1
    previous: dict[tuple[int, int], tuple[int, int]] = state.setdefault("pid_ticks", {})
    active: set[tuple[int, int]] = set()
    top_cpu = []
    top_mem = []

    for pid in pids:
        stat = procfs.read_stat(pid, proc_root)
        status = procfs.read_status(pid, proc_root)
        if stat is None or status is None:
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
        rss_kb = procfs.parse_kb(status.get("VmRSS"))
        row = {"pid": pid, "comm": stat["comm"], "cpu": cpu, "rss_kb": rss_kb}
        top_cpu.append(row)
        top_mem.append(row)

    prune_state_map(previous, active)
    top_cpu.sort(key=lambda item: (-item["cpu"], item["pid"]))
    top_mem.sort(key=lambda item: (-item["rss_kb"], item["pid"]))
    uptime = procfs.read_uptime(proc_root)

    return {
        "cpu": cpu_percentages,
        "loadavg": procfs.read_loadavg(proc_root),
        "meminfo_kb": procfs.read_meminfo(proc_root),
        "procesos": procfs.count_processes(pids, proc_root),
        "uptime": uptime,
        "uptime_humano": procfs.format_seconds(uptime["uptime"]),
        "boot_time": procfs.read_boot_time(proc_root),
        "top_cpu": top_cpu[:3],
        "top_mem": top_mem[:3],
    }


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
