from __future__ import annotations

from typing import Any

from src import procfs
from src.analizadores.base import analyzer_loop

VIEW = "senales"
MIN_INTERVAL = 5.0
MASK_KEYS = ("SigBlk", "SigIgn", "SigCgt", "SigPnd", "ShdPnd")


def collect(pids: list[int], state: dict[str, Any], proc_root: str) -> dict[str, Any]:
    processes: dict[str, Any] = {}
    for pid in pids:
        status = procfs.read_status(pid, proc_root)
        stat = procfs.read_stat(pid, proc_root)
        if status is None or stat is None:
            continue
        raw = {key: status.get(key, "0" * 16) for key in MASK_KEYS}
        decoded = {key: procfs.signal_names_from_mask(value) for key, value in raw.items()}
        processes[str(pid)] = {"pid": pid, "comm": stat["comm"], "raw": raw, "decoded": decoded}
    return {"processes": processes, "total": len(processes)}


def run(input_queue: Any, output_queue: Any, interval_value: Any, stop_event: Any, proc_root: str) -> None:
    analyzer_loop(VIEW, MIN_INTERVAL, input_queue, output_queue, interval_value, stop_event, proc_root, collect)
