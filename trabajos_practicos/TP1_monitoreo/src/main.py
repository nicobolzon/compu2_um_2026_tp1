from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from src import agregador, recolector
from src.analizadores import fds, memoria, resumen, scheduling, senales as analizador_senales, sistema, threads
from src.senales import SIGNAL_INDEX, SIGNAL_NUMBERS, SIGNAL_ORDER, SignalRouter


ANALYZERS = {
    "resumen": resumen.run,
    "memoria": memoria.run,
    "fds": fds.run,
    "threads": threads.run,
    "senales": analizador_senales.run,
    "scheduling": scheduling.run,
    "sistema": sistema.run,
}
DEFAULT_INTERVALS = {
    "resumen": 2.0,
    "memoria": 3.0,
    "fds": 5.0,
    "threads": 2.0,
    "senales": 10.0,
    "scheduling": 10.0,
    "sistema": 2.0,
}
MIN_INTERVALS = {
    "resumen": 0.5,
    "memoria": 1.0,
    "fds": 2.0,
    "threads": 0.5,
    "senales": 5.0,
    "scheduling": 5.0,
    "sistema": 1.0,
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"intervalos": DEFAULT_INTERVALS.copy(), "filtros": {}, "orden": "cpu"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"intervalos": DEFAULT_INTERVALS.copy(), "filtros": {}, "orden": "cpu"}

    intervalos = DEFAULT_INTERVALS.copy()
    for view, value in raw.get("intervalos", {}).items():
        if view in intervalos:
            try:
                intervalos[view] = max(MIN_INTERVALS[view], float(value))
            except (TypeError, ValueError):
                pass
    return {
        "intervalos": intervalos,
        "filtros": raw.get("filtros", {}),
        "orden": raw.get("orden", "cpu"),
    }


def apply_intervals(config: dict[str, Any], interval_values: dict[str, Any]) -> None:
    for view, value in config.get("intervalos", {}).items():
        if view not in interval_values:
            continue
        value = max(MIN_INTERVALS[view], float(value))
        try:
            with interval_values[view].get_lock():
                interval_values[view].value = value
        except AttributeError:
            interval_values[view].value = value


def make_dump_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    return root / f"dump_{stamp}.json"


def send_control(control_send: Any, message: dict[str, Any]) -> None:
    try:
        control_send.send(message)
    except (BrokenPipeError, EOFError, OSError):
        pass


def bump_signal_count(signal_counts: Any, signum: int) -> None:
    index = SIGNAL_INDEX.get(signum)
    if index is None:
        return
    try:
        with signal_counts.get_lock():
            signal_counts[index] += 1
    except AttributeError:
        signal_counts[index] += 1


def toggle_verbose(verbose_value: Any) -> bool:
    try:
        with verbose_value.get_lock():
            verbose_value.value = not bool(verbose_value.value)
            return bool(verbose_value.value)
    except AttributeError:
        verbose_value.value = not bool(verbose_value.value)
        return bool(verbose_value.value)


def signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except ValueError:
        return f"SIG{signum}"


def build_signal_callback(
    router: SignalRouter,
    config_path: Path,
    runtime_config: dict[str, Any],
    interval_values: dict[str, Any],
    verbose_value: Any,
    signal_counts: Any,
    control_send: Any,
    stop_event: Any,
) -> Any:
    def callback() -> list[str]:
        names: list[str] = []
        for signum in router.drain():
            bump_signal_count(signal_counts, signum)
            name = signal_name(signum)
            names.append(name)

            if signum in (SIGNAL_NUMBERS.get("SIGINT"), SIGNAL_NUMBERS.get("SIGTERM")):
                stop_event.set()
                send_control(control_send, {"type": "event", "nombre": name, "detalle": "shutdown"})
            elif signum == SIGNAL_NUMBERS.get("SIGHUP"):
                config = load_config(config_path)
                apply_intervals(config, interval_values)
                runtime_config.clear()
                runtime_config.update(config)
                runtime_config["_reload_ts"] = time.time()
                send_control(control_send, {"type": "event", "nombre": name, "detalle": "config recargada"})
            elif signum == SIGNAL_NUMBERS.get("SIGUSR1"):
                path = make_dump_path(config_path.parent)
                send_control(control_send, {"type": "dump", "path": str(path)})
                send_control(control_send, {"type": "event", "nombre": name, "detalle": str(path.name)})
            elif signum == SIGNAL_NUMBERS.get("SIGUSR2"):
                verbose = toggle_verbose(verbose_value)
                send_control(control_send, {"type": "event", "nombre": name, "detalle": f"verbose={verbose}"})
            elif signum == SIGNAL_NUMBERS.get("SIGWINCH"):
                send_control(control_send, {"type": "event", "nombre": name, "detalle": "resize"})
        return names

    return callback


def start_processes(
    config: dict[str, Any],
    proc_root: str,
    snapshot: Any,
    snapshot_lock: Any,
    stop_event: Any,
    control_recv: Any,
) -> tuple[dict[str, Any], list[mp.Process], Any]:
    analyzer_queues = {view: mp.Queue(maxsize=2) for view in ANALYZERS}
    output_queue = mp.Queue(maxsize=100)
    interval_values = {
        view: mp.Value("d", config.get("intervalos", {}).get(view, DEFAULT_INTERVALS[view]))
        for view in ANALYZERS
    }
    processes: list[mp.Process] = []

    aggregator_process = mp.Process(
        name="agregador",
        target=agregador.run,
        args=(output_queue, snapshot, snapshot_lock, control_recv, stop_event),
    )
    processes.append(aggregator_process)

    collector_process = mp.Process(
        name="recolector",
        target=recolector.run,
        args=(analyzer_queues, stop_event, proc_root),
    )
    processes.append(collector_process)

    for view, target in ANALYZERS.items():
        process = mp.Process(
            name=f"analizador_{view}",
            target=target,
            args=(analyzer_queues[view], output_queue, interval_values[view], stop_event, proc_root),
        )
        processes.append(process)

    for process in processes:
        process.start()

    return interval_values, processes, output_queue


def shutdown(processes: list[mp.Process], stop_event: Any) -> None:
    stop_event.set()
    for process in processes:
        process.join(timeout=2.0)
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join(timeout=1.0)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor de procesos y threads usando /proc.")
    parser.add_argument("--config", default=str(project_root() / "config.json"), help="Ruta al config.json")
    parser.add_argument("--proc-root", default=os.environ.get("PROC_ROOT", "/proc"), help="Raiz de procfs")
    parser.add_argument("--once", action="store_true", help="Toma un snapshot y lo imprime como JSON")
    parser.add_argument("--seconds", type=float, default=3.0, help="Segundos de muestreo para --once")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    runtime_config = dict(config)
    runtime_config["_reload_ts"] = 0.0

    manager = mp.Manager()
    snapshot = manager.dict()
    snapshot_lock = manager.RLock()
    stop_event = mp.Event()
    verbose_value = mp.Value("b", False)
    signal_counts = mp.Array("i", [0 for _ in SIGNAL_ORDER])
    control_recv, control_send = mp.Pipe(duplex=False)
    processes: list[mp.Process] = []

    try:
        interval_values, processes, _ = start_processes(
            config,
            args.proc_root,
            snapshot,
            snapshot_lock,
            stop_event,
            control_recv,
        )
        apply_intervals(config, interval_values)

        with SignalRouter() as router:
            signal_callback = build_signal_callback(
                router,
                config_path,
                runtime_config,
                interval_values,
                verbose_value,
                signal_counts,
                control_send,
                stop_event,
            )
            if args.once:
                deadline = time.time() + max(0.5, args.seconds)
                while time.time() < deadline and not stop_event.is_set():
                    signal_callback()
                    time.sleep(0.1)
                with snapshot_lock:
                    data = {key: snapshot[key] for key in list(snapshot.keys())}
                print(json.dumps(data, indent=2, sort_keys=True, default=str))
            else:
                from src import display

                display.run(
                    snapshot,
                    snapshot_lock,
                    interval_values,
                    verbose_value,
                    signal_counts,
                    signal_callback,
                    stop_event,
                    runtime_config,
                )
    finally:
        send_control(control_send, {"type": "event", "nombre": "shutdown", "detalle": "fin del monitor"})
        shutdown(processes, stop_event)
        manager.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
