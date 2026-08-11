from __future__ import annotations

import os
from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop, prune_state_map

VIEW = "threads"
MIN_INTERVAL = 0.5


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    total_jiffies = procfs.read_total_jiffies(proc_root)
    cpu_count = os.cpu_count() or 1
    previous: dict[str, tuple[int, int]] = state.setdefault("thread_ticks", {})
    active: set[str] = set()
    processes: dict[str, Any] = {}

    for pid in pids:
        stat = procfs.read_stat(pid, proc_root)
        if stat is None:
            continue
        threads = []
        for tid in procfs.list_threads(pid, proc_root):
            thread_stat = procfs.read_thread_stat(pid, tid, proc_root)
            thread_status = procfs.read_thread_status(pid, tid, proc_root) or {}
            if thread_stat is None:
                continue
            key = f"{pid}:{tid}:{thread_stat['starttime']}"
            active.add(key)
            ticks = procfs.process_ticks(thread_stat)
            old = previous.get(key)
            cpu = procfs.calc_cpu_percent(
                old[0] if old else None,
                ticks,
                old[1] if old else None,
                total_jiffies,
                cpu_count,
            )
            previous[key] = (ticks, total_jiffies)
            threads.append(
                {
                    "tid": tid,
                    "nombre": procfs.read_thread_comm(pid, tid, proc_root) or thread_stat["comm"],
                    "estado": thread_stat["state"],
                    "cpu": cpu,
                    "utime": thread_stat["utime"],
                    "stime": thread_stat["stime"],
                    "voluntary_ctxt_switches": procfs.safe_int(
                        thread_status.get("voluntary_ctxt_switches")
                    ),
                    "nonvoluntary_ctxt_switches": procfs.safe_int(
                        thread_status.get("nonvoluntary_ctxt_switches")
                    ),
                }
            )
        processes[str(pid)] = {"pid": pid, "comm": stat["comm"], "threads": threads, "total": len(threads)}

    prune_state_map(previous, active)
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
