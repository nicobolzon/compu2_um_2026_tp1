from __future__ import annotations

import curses
import time
from dataclasses import dataclass
from typing import Any

from src import procfs


VIEWS = ("resumen", "memoria", "fds", "threads", "senales", "scheduling", "sistema")
VIEW_LABELS = {
    "resumen": "Resumen",
    "memoria": "Memoria",
    "fds": "File descriptors",
    "threads": "Threads",
    "senales": "Senales",
    "scheduling": "Scheduling",
    "sistema": "Sistema",
}
VIEW_KEYS = {
    ord("1"): "resumen",
    ord("r"): "resumen",
    ord("2"): "memoria",
    ord("m"): "memoria",
    ord("3"): "fds",
    ord("f"): "fds",
    ord("4"): "threads",
    ord("t"): "threads",
    ord("5"): "senales",
    ord("s"): "senales",
    ord("6"): "scheduling",
    ord("p"): "scheduling",
    ord("7"): "sistema",
    ord("g"): "sistema",
}
ORDER_MODES = ("cpu", "rss", "pid")
MIN_INTERVALS = {
    "resumen": 0.5,
    "memoria": 1.0,
    "fds": 2.0,
    "threads": 0.5,
    "senales": 5.0,
    "scheduling": 5.0,
    "sistema": 1.0,
}
SIGNAL_LABELS = ("SIGINT", "SIGTERM", "SIGHUP", "SIGUSR1", "SIGUSR2", "SIGWINCH")


@dataclass
class DisplayState:
    active_view: str = "resumen"
    selected_index: int = 0
    pinned_pid: int | None = None
    command_filter: str = ""
    user_filter: str = ""
    order_mode: str = "cpu"
    show_help: bool = False
    message: str = ""


def format_kb(kb: int | float | None) -> str:
    value = float(kb or 0)
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f}G"
    if value >= 1024:
        return f"{value / 1024:.1f}M"
    return f"{value:.0f}K"


def safe_addstr(stdscr: Any, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return
    available = max(0, width - x - 1)
    if available <= 0:
        return
    try:
        stdscr.addstr(y, x, str(text)[:available], attr)
    except curses.error:
        pass


def read_value(value: Any) -> float:
    try:
        with value.get_lock():
            return float(value.value)
    except AttributeError:
        return float(value.value)


def set_value(value: Any, new_value: float) -> None:
    try:
        with value.get_lock():
            value.value = new_value
    except AttributeError:
        value.value = new_value


def read_bool(value: Any) -> bool:
    try:
        with value.get_lock():
            return bool(value.value)
    except AttributeError:
        return bool(value.value)


def read_array(values: Any) -> list[int]:
    try:
        with values.get_lock():
            return list(values)
    except AttributeError:
        return list(values)


def snapshot_copy(snapshot: Any, snapshot_lock: Any) -> dict[str, Any]:
    with snapshot_lock:
        return {key: snapshot[key] for key in list(snapshot.keys())}


def prompt_string(stdscr: Any, prompt: str) -> str:
    height, width = stdscr.getmaxyx()
    curses.echo()
    stdscr.nodelay(False)
    stdscr.move(height - 1, 0)
    stdscr.clrtoeol()
    safe_addstr(stdscr, height - 1, 0, prompt)
    try:
        raw = stdscr.getstr(height - 1, min(len(prompt), width - 2), max(1, width - len(prompt) - 2))
    except curses.error:
        raw = b""
    curses.noecho()
    stdscr.nodelay(True)
    return raw.decode("utf-8", errors="replace").strip()


def filter_and_sort(processes: list[dict[str, Any]], state: DisplayState) -> list[dict[str, Any]]:
    command_filter = state.command_filter.lower()
    user_filter = state.user_filter.lower()
    filtered = []
    for proc in processes:
        command = f"{proc.get('cmdline', '')} {proc.get('comm', '')}".lower()
        user = str(proc.get("usuario", "")).lower()
        if command_filter and command_filter not in command:
            continue
        if user_filter and user_filter not in user:
            continue
        filtered.append(proc)

    if state.order_mode == "rss":
        filtered.sort(key=lambda item: (-int(item.get("rss_kb", 0)), item.get("pid", 0)))
    elif state.order_mode == "pid":
        filtered.sort(key=lambda item: int(item.get("pid", 0)))
    else:
        filtered.sort(key=lambda item: (-float(item.get("cpu", 0.0)), -int(item.get("rss_kb", 0)), item.get("pid", 0)))
    return filtered


def selected_pid(processes: list[dict[str, Any]], state: DisplayState) -> int | None:
    if not processes:
        state.selected_index = 0
        return state.pinned_pid
    if state.pinned_pid is not None:
        for index, proc in enumerate(processes):
            if proc.get("pid") == state.pinned_pid:
                state.selected_index = index
                return state.pinned_pid
    state.selected_index = max(0, min(state.selected_index, len(processes) - 1))
    return int(processes[state.selected_index]["pid"])


def render_header(
    stdscr: Any,
    state: DisplayState,
    intervals: dict[str, Any],
    verbose_value: Any,
    signal_counts: Any,
) -> None:
    active = VIEW_LABELS[state.active_view]
    interval = read_value(intervals[state.active_view])
    verbose = "on" if read_bool(verbose_value) else "off"
    counts = read_array(signal_counts)
    signal_text = " ".join(
        f"{name}:{counts[index]}" for index, name in enumerate(SIGNAL_LABELS) if index < len(counts) and counts[index]
    )
    filters = []
    if state.command_filter:
        filters.append(f"cmd={state.command_filter}")
    if state.user_filter:
        filters.append(f"user={state.user_filter}")
    filter_text = " ".join(filters) if filters else "sin filtros"
    pin_text = f"pin={state.pinned_pid}" if state.pinned_pid else "sin pin"

    safe_addstr(stdscr, 0, 0, "TP1 Monitor de Procesos y Threads", curses.A_BOLD)
    safe_addstr(
        stdscr,
        1,
        0,
        f"Vista {active} | int {interval:.1f}s | orden {state.order_mode} | {filter_text} | {pin_text} | verbose {verbose}",
    )
    safe_addstr(
        stdscr,
        2,
        0,
        "1-7 vistas | r/m/f/t/s/p/g | flechas | Enter pin | / cmd | u user | c orden | +/- int | h | q",
    )
    if signal_text:
        safe_addstr(stdscr, 3, 0, f"Senales recibidas: {signal_text}", curses.A_DIM)
    elif state.message:
        safe_addstr(stdscr, 3, 0, state.message, curses.A_DIM)


def render_process_table(
    stdscr: Any,
    processes: list[dict[str, Any]],
    state: DisplayState,
    start_y: int,
    rows: int,
) -> None:
    safe_addstr(stdscr, start_y, 0, "SEL     PID USER         ST   CPU      RSS  THR CMD", curses.A_BOLD)
    if processes:
        start_index = max(0, min(state.selected_index - rows // 2, max(0, len(processes) - rows)))
    else:
        start_index = 0
    for offset in range(rows):
        index = start_index + offset
        y = start_y + 1 + offset
        if index >= len(processes):
            safe_addstr(stdscr, y, 0, "~")
            continue
        proc = processes[index]
        marker = ">"
        if index != state.selected_index:
            marker = "* " if proc.get("pid") == state.pinned_pid else "  "
        cmd = proc.get("cmdline") or proc.get("comm") or ""
        line = (
            f"{marker} {proc.get('pid', 0):6} "
            f"{str(proc.get('usuario', ''))[:10]:10} "
            f"{proc.get('estado', '?'):>2} "
            f"{float(proc.get('cpu', 0.0)):6.1f}% "
            f"{format_kb(proc.get('rss_kb')):>8} "
            f"{int(proc.get('threads', 0)):4} "
            f"{cmd}"
        )
        attr = curses.A_REVERSE if index == state.selected_index else 0
        safe_addstr(stdscr, y, 0, line, attr)


def render_waiting(stdscr: Any, y: int, view: str) -> None:
    safe_addstr(stdscr, y, 0, f"Esperando datos de la vista {VIEW_LABELS[view]}...")


def view_payload(snapshot: dict[str, Any], view: str) -> dict[str, Any] | None:
    message = snapshot.get(view)
    if not isinstance(message, dict):
        return None
    data = message.get("data")
    return data if isinstance(data, dict) else None


def render_meta(stdscr: Any, y: int, snapshot: dict[str, Any], view: str) -> int:
    message = snapshot.get(view)
    if not isinstance(message, dict):
        return y
    age = max(0.0, time.time() - float(message.get("ts", time.time())))
    duration = message.get("duration_ms", 0)
    error = message.get("error")
    safe_addstr(stdscr, y, 0, f"Actualizado hace {age:.1f}s | analizador pid {message.get('pid')} | costo {duration} ms")
    y += 1
    if error:
        safe_addstr(stdscr, y, 0, f"Error del analizador: {error}", curses.A_BOLD)
        y += 1
    return y


def get_process_record(data: dict[str, Any] | None, pid: int | None) -> dict[str, Any] | None:
    if data is None or pid is None:
        return None
    processes = data.get("processes", {})
    if isinstance(processes, dict):
        record = processes.get(str(pid))
        return record if isinstance(record, dict) else None
    if isinstance(processes, list):
        for item in processes:
            if item.get("pid") == pid:
                return item
    return None


def render_resumen(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "resumen")
        return
    lines = [
        f"PID {record['pid']} | PPID {record['ppid']} | UID {record['uid']} ({record['usuario']}) | GID {record['gid']} ({record['grupo']})",
        f"Estado {record['estado']} | CPU {record['cpu']:.2f}% | RSS {format_kb(record['rss_kb'])} | Threads {record['threads']}",
        f"Nice {record['nice']} | Priority {record['priority']} | utime {record['utime']} | stime {record['stime']}",
        f"Comando: {record['cmdline']}",
    ]
    for index, line in enumerate(lines):
        safe_addstr(stdscr, y + index, 0, line)


def render_memoria(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "memoria")
        return
    safe_addstr(stdscr, y, 0, f"PID {pid} ({record.get('comm', '')})", curses.A_BOLD)
    y += 1
    memoria = record.get("memoria_kb", {})
    safe_addstr(
        stdscr,
        y,
        0,
        " | ".join(f"{key}={format_kb(memoria.get(key, 0))}" for key in procfs.MEMORY_KEYS),
    )
    y += 1
    faults = record.get("faults", {})
    safe_addstr(
        stdscr,
        y,
        0,
        f"Page faults minor={faults.get('minor', 0)} major={faults.get('major', 0)} "
        f"children_minor={faults.get('children_minor', 0)} children_major={faults.get('children_major', 0)}",
    )
    y += 1
    segmentos = record.get("segmentos_kb", {})
    safe_addstr(stdscr, y, 0, "Segmentos: " + " | ".join(f"{key}={format_kb(value)}" for key, value in segmentos.items()))


def render_fds(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None, verbose: bool) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "fds")
        return
    safe_addstr(stdscr, y, 0, f"PID {pid} ({record.get('comm', '')}) | total FDs {record.get('total', 0)}", curses.A_BOLD)
    y += 1
    if record.get("error"):
        safe_addstr(stdscr, y, 0, f"No se pudo leer fd/: {record['error']}")
        y += 1
    limit = 40 if verbose else 15
    for item in record.get("fds", [])[:limit]:
        safe_addstr(stdscr, y, 0, f"{item.get('fd'):>4} {item.get('type', ''):12} {item.get('target', '')}")
        y += 1


def render_threads(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None, verbose: bool) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "threads")
        return
    safe_addstr(stdscr, y, 0, f"PID {pid} ({record.get('comm', '')}) | threads {record.get('total', 0)}", curses.A_BOLD)
    y += 1
    safe_addstr(stdscr, y, 0, "   TID ST    CPU  VOL_CTX NONVOL_CTX NOMBRE", curses.A_BOLD)
    y += 1
    limit = 40 if verbose else 15
    for item in record.get("threads", [])[:limit]:
        safe_addstr(
            stdscr,
            y,
            0,
            f"{item.get('tid', 0):6} {item.get('estado', '?'):>2} "
            f"{float(item.get('cpu', 0.0)):6.1f}% "
            f"{int(item.get('voluntary_ctxt_switches', 0)):8} "
            f"{int(item.get('nonvoluntary_ctxt_switches', 0)):10} "
            f"{item.get('nombre', '')}",
        )
        y += 1


def render_senales(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "senales")
        return
    safe_addstr(stdscr, y, 0, f"PID {pid} ({record.get('comm', '')})", curses.A_BOLD)
    y += 1
    raw = record.get("raw", {})
    decoded = record.get("decoded", {})
    labels = {
        "SigBlk": "Bloqueadas",
        "SigIgn": "Ignoradas",
        "SigCgt": "Con handler",
        "SigPnd": "Pendientes proceso",
        "ShdPnd": "Pendientes grupo",
    }
    for key, label in labels.items():
        names = ", ".join(decoded.get(key, [])) or "-"
        safe_addstr(stdscr, y, 0, f"{label:20} {raw.get(key, '')}  {names}")
        y += 1


def render_scheduling(stdscr: Any, y: int, data: dict[str, Any] | None, pid: int | None) -> None:
    record = get_process_record(data, pid)
    if record is None:
        render_waiting(stdscr, y, "scheduling")
        return
    lines = [
        f"PID {pid} ({record.get('comm', '')})",
        f"Nice {record.get('nice')} | Priority {record.get('priority')} | Policy {record.get('policy')} | RT priority {record.get('rt_priority')}",
        f"CPU affinity {record.get('cpu_affinity')} | SID {record.get('sid')} | PGID {record.get('pgid')}",
        f"Context switches voluntarios {record.get('voluntary_ctxt_switches')} | involuntarios {record.get('nonvoluntary_ctxt_switches')}",
        f"utime {record.get('utime')} | stime {record.get('stime')}",
    ]
    for index, line in enumerate(lines):
        safe_addstr(stdscr, y + index, 0, line, curses.A_BOLD if index == 0 else 0)


def render_sistema(stdscr: Any, y: int, data: dict[str, Any] | None) -> None:
    if data is None:
        render_waiting(stdscr, y, "sistema")
        return
    cpu = data.get("cpu", {})
    load = data.get("loadavg", {})
    mem = data.get("meminfo_kb", {})
    procesos = data.get("procesos", {})
    safe_addstr(stdscr, y, 0, "CPU: " + " | ".join(f"{key}={value:.1f}%" for key, value in cpu.items()))
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"Load avg {load.get('1m', 0):.2f} {load.get('5m', 0):.2f} {load.get('15m', 0):.2f} | "
        f"running {load.get('running', '0/0')} | last_pid {load.get('last_pid', 0)}",
    )
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"Mem total {format_kb(mem.get('MemTotal'))} | libre {format_kb(mem.get('MemFree'))} | "
        f"buffers {format_kb(mem.get('Buffers'))} | cached {format_kb(mem.get('Cached'))} | swap {format_kb(mem.get('SwapTotal'))}",
    )
    y += 1
    safe_addstr(
        stdscr,
        y,
        0,
        f"Procesos {procesos.get('total', 0)} | threads {procesos.get('threads_total', 0)} | "
        f"zombies {procesos.get('zombies', 0)} | estados {procesos.get('por_estado', {})}",
    )
    y += 1
    safe_addstr(stdscr, y, 0, f"Uptime {data.get('uptime_humano', '00:00:00')} | boot_time {data.get('boot_time', 0)}")
    y += 2
    safe_addstr(stdscr, y, 0, "Top CPU", curses.A_BOLD)
    safe_addstr(stdscr, y, 34, "Top Memoria", curses.A_BOLD)
    y += 1
    for index in range(3):
        cpu_row = data.get("top_cpu", [{}])[index] if index < len(data.get("top_cpu", [])) else {}
        mem_row = data.get("top_mem", [{}])[index] if index < len(data.get("top_mem", [])) else {}
        safe_addstr(
            stdscr,
            y + index,
            0,
            f"{cpu_row.get('pid', ''):>6} {cpu_row.get('cpu', 0.0):>6.1f}% {cpu_row.get('comm', '')}",
        )
        safe_addstr(
            stdscr,
            y + index,
            34,
            f"{mem_row.get('pid', ''):>6} {format_kb(mem_row.get('rss_kb', 0)):>8} {mem_row.get('comm', '')}",
        )


def render_help(stdscr: Any, y: int) -> None:
    lines = [
        "Ayuda",
        "1-7 o r/m/f/t/s/p/g: cambia la vista activa.",
        "Flechas arriba/abajo: navegan la lista superior de procesos.",
        "Enter: fija o libera el proceso seleccionado.",
        "/: filtro por comando. u: filtro por usuario.",
        "c: alterna orden CPU, RSS o PID.",
        "+/-: ajusta el intervalo del analizador de la vista activa.",
        "SIGUSR1 genera dump_<timestamp>.json. SIGUSR2 alterna verbose.",
        "SIGHUP recarga config.json. SIGINT/SIGTERM salen limpiamente.",
    ]
    for index, line in enumerate(lines):
        safe_addstr(stdscr, y + index, 0, line, curses.A_BOLD if index == 0 else 0)


def render_detail(
    stdscr: Any,
    y: int,
    snapshot: dict[str, Any],
    state: DisplayState,
    pid: int | None,
    verbose_value: Any,
) -> None:
    view = state.active_view
    if state.show_help:
        render_help(stdscr, y)
        return
    y = render_meta(stdscr, y, snapshot, view)
    data = view_payload(snapshot, view)
    verbose = read_bool(verbose_value)
    if view == "resumen":
        render_resumen(stdscr, y, data, pid)
    elif view == "memoria":
        render_memoria(stdscr, y, data, pid)
    elif view == "fds":
        render_fds(stdscr, y, data, pid, verbose)
    elif view == "threads":
        render_threads(stdscr, y, data, pid, verbose)
    elif view == "senales":
        render_senales(stdscr, y, data, pid)
    elif view == "scheduling":
        render_scheduling(stdscr, y, data, pid)
    elif view == "sistema":
        render_sistema(stdscr, y, data)


def handle_key(
    key: int,
    stdscr: Any,
    state: DisplayState,
    processes: list[dict[str, Any]],
    intervals: dict[str, Any],
    stop_event: Any,
) -> None:
    if key == -1:
        return
    if key in VIEW_KEYS:
        state.active_view = VIEW_KEYS[key]
        state.show_help = False
        return
    if key in (ord("q"), ord("Q")):
        state.message = "Saliendo..."
        stop_event.set()
        return
    if key in (ord("h"), ord("?")):
        state.show_help = not state.show_help
        return
    if key == curses.KEY_UP:
        state.pinned_pid = None
        state.selected_index = max(0, state.selected_index - 1)
        return
    if key == curses.KEY_DOWN:
        state.pinned_pid = None
        state.selected_index = min(max(0, len(processes) - 1), state.selected_index + 1)
        return
    if key in (10, 13, curses.KEY_ENTER):
        pid = selected_pid(processes, state)
        state.pinned_pid = None if state.pinned_pid == pid else pid
        return
    if key == ord("/"):
        state.command_filter = prompt_string(stdscr, "Filtro comando (vacio limpia): ")
        state.selected_index = 0
        state.pinned_pid = None
        return
    if key == ord("u"):
        state.user_filter = prompt_string(stdscr, "Filtro usuario (vacio limpia): ")
        state.selected_index = 0
        state.pinned_pid = None
        return
    if key == ord("c"):
        index = ORDER_MODES.index(state.order_mode)
        state.order_mode = ORDER_MODES[(index + 1) % len(ORDER_MODES)]
        return
    if key in (ord("+"), ord("=")):
        value = read_value(intervals[state.active_view])
        set_value(intervals[state.active_view], value + 0.5)
        return
    if key in (ord("-"), ord("_")):
        value = read_value(intervals[state.active_view])
        set_value(intervals[state.active_view], max(MIN_INTERVALS[state.active_view], value - 0.5))


def run(
    snapshot: Any,
    snapshot_lock: Any,
    intervals: dict[str, Any],
    verbose_value: Any,
    signal_counts: Any,
    signal_callback: Any,
    stop_event: Any,
    config: dict[str, Any],
) -> None:
    def curses_main(stdscr: Any) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        try:
            curses.use_default_colors()
        except curses.error:
            pass

        filters = config.get("filtros", {})
        state = DisplayState(
            command_filter=str(filters.get("comando", "")),
            user_filter=str(filters.get("usuario", "")),
            order_mode=str(config.get("orden", "cpu")) if config.get("orden") in ORDER_MODES else "cpu",
        )
        last_reload_ts = float(config.get("_reload_ts", 0.0))

        while not stop_event.is_set():
            signal_names = signal_callback()
            if signal_names:
                state.message = "Seniales: " + ", ".join(signal_names)
            reload_ts = float(config.get("_reload_ts", 0.0))
            if reload_ts != last_reload_ts:
                filters = config.get("filtros", {})
                state.command_filter = str(filters.get("comando", ""))
                state.user_filter = str(filters.get("usuario", ""))
                state.order_mode = str(config.get("orden", "cpu")) if config.get("orden") in ORDER_MODES else "cpu"
                state.selected_index = 0
                state.pinned_pid = None
                state.message = "config.json recargado"
                last_reload_ts = reload_ts

            snap = snapshot_copy(snapshot, snapshot_lock)
            summary = view_payload(snap, "resumen") or {}
            processes = filter_and_sort(summary.get("processes", []), state)
            pid = selected_pid(processes, state)

            stdscr.erase()
            height, _ = stdscr.getmaxyx()
            process_rows = max(4, min(12, height // 2 - 4))
            detail_y = 5 + process_rows
            render_header(stdscr, state, intervals, verbose_value, signal_counts)
            render_process_table(stdscr, processes, state, 4, process_rows)
            safe_addstr(stdscr, detail_y - 1, 0, "-" * 200)
            render_detail(stdscr, detail_y, snap, state, pid, verbose_value)
            stdscr.refresh()

            while True:
                key = stdscr.getch()
                if key == -1:
                    break
                handle_key(key, stdscr, state, processes, intervals, stop_event)
            time.sleep(0.08)

    curses.wrapper(curses_main)
