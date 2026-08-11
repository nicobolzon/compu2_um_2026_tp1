from __future__ import annotations

from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop

VIEW = "scheduling"
MIN_INTERVAL = 5.0


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
            "nice": stat["nice"],
            "priority": stat["priority"],
            "policy": procfs.policy_name(stat["policy"]),
            "policy_raw": stat["policy"],
            "rt_priority": stat["rt_priority"],
            "cpu_affinity": status.get("Cpus_allowed_list", ""),
            "voluntary_ctxt_switches": procfs.safe_int(status.get("voluntary_ctxt_switches")),
            "nonvoluntary_ctxt_switches": procfs.safe_int(status.get("nonvoluntary_ctxt_switches")),
            "utime": stat["utime"],
            "stime": stat["stime"],
            "sid": stat["sid"],
            "pgid": stat["pgid"],
        }
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
