from __future__ import annotations

import json
import queue
import time
from pathlib import Path
from typing import Any


def plain_snapshot(snapshot: Any, snapshot_lock: Any) -> dict[str, Any]:
    with snapshot_lock:
        return {key: snapshot[key] for key in list(snapshot.keys())}


def write_dump(path: str | Path, snapshot: Any, snapshot_lock: Any) -> None:
    data = {
        "ts": time.time(),
        "snapshot": plain_snapshot(snapshot, snapshot_lock),
    }
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def handle_control(message: dict[str, Any], snapshot: Any, snapshot_lock: Any) -> None:
    action = message.get("type")
    if action == "dump":
        write_dump(message["path"], snapshot, snapshot_lock)
    elif action == "event":
        with snapshot_lock:
            snapshot["ultimo_evento"] = {
                "ts": time.time(),
                "nombre": message.get("nombre", "evento"),
                "detalle": message.get("detalle", ""),
            }


def run(output_queue: Any, snapshot: Any, snapshot_lock: Any, control_recv: Any, stop_event: Any) -> None:
    while not stop_event.is_set():
        while control_recv.poll():
            handle_control(control_recv.recv(), snapshot, snapshot_lock)

        try:
            message = output_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        view = message.get("view")
        if not view:
            continue
        with snapshot_lock:
            snapshot[view] = message

    while True:
        try:
            message = output_queue.get_nowait()
        except queue.Empty:
            break
        view = message.get("view")
        if view:
            with snapshot_lock:
                snapshot[view] = message
