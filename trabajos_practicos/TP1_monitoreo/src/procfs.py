from __future__ import annotations

import os
import signal
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import grp
    import pwd
except ImportError:  # pragma: no cover - el TP corre en Linux, pero permite tests en Windows.
    grp = None
    pwd = None


PROC_ROOT = Path(os.environ.get("PROC_ROOT", "/proc"))
STAT_CPU_KEYS = (
    "user",
    "nice",
    "system",
    "idle",
    "iowait",
    "irq",
    "softirq",
    "steal",
    "guest",
    "guest_nice",
)
MEMORY_KEYS = ("VmSize", "VmRSS", "VmData", "VmStk", "VmExe", "VmLib", "VmHWM", "VmSwap")
SCHED_POLICIES = {
    0: "OTHER",
    1: "FIFO",
    2: "RR",
    3: "BATCH",
    5: "IDLE",
    6: "DEADLINE",
}


def proc_path(proc_root: str | Path | None = None) -> Path:
    return Path(proc_root) if proc_root is not None else PROC_ROOT


def clock_ticks() -> int:
    try:
        return int(os.sysconf("SC_CLK_TCK"))
    except (AttributeError, OSError, ValueError):
        return 100


def page_size_kb() -> int:
    try:
        return max(1, int(os.sysconf("SC_PAGE_SIZE")) // 1024)
    except (AttributeError, OSError, ValueError):
        return 4


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_kb(value: str | None) -> int:
    if not value:
        return 0
    parts = value.split()
    return safe_int(parts[0])


def safe_read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None


def safe_read_bytes(path: str | Path) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return None


def list_pids(proc_root: str | Path | None = None) -> list[int]:
    root = proc_path(proc_root)
    try:
        return sorted(safe_int(entry.name) for entry in root.iterdir() if entry.name.isdigit())
    except (FileNotFoundError, PermissionError, OSError):
        return []


def parse_status_content(content: str) -> dict[str, str]:
    status: dict[str, str] = {}
    for line in content.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        status[key.strip()] = value.strip()
    return status


def read_status(pid: int, proc_root: str | Path | None = None) -> dict[str, str] | None:
    content = safe_read_text(proc_path(proc_root) / str(pid) / "status")
    if content is None:
        return None
    return parse_status_content(content)


def parse_stat_content(content: str) -> dict[str, Any]:
    left = content.find("(")
    right = content.rfind(")")
    if left == -1 or right == -1 or right < left:
        raise ValueError("formato invalido de /proc/<pid>/stat")

    pid = safe_int(content[:left].strip())
    comm = content[left + 1 : right]
    rest = content[right + 2 :].split()

    def field(number: int, default: int = 0) -> int:
        index = number - 3
        if index < 0 or index >= len(rest):
            return default
        return safe_int(rest[index], default)

    def text_field(number: int, default: str = "") -> str:
        index = number - 3
        if index < 0 or index >= len(rest):
            return default
        return rest[index]

    return {
        "pid": pid,
        "comm": comm,
        "state": text_field(3),
        "ppid": field(4),
        "pgid": field(5),
        "sid": field(6),
        "minflt": field(10),
        "cminflt": field(11),
        "majflt": field(12),
        "cmajflt": field(13),
        "utime": field(14),
        "stime": field(15),
        "priority": field(18),
        "nice": field(19),
        "num_threads": field(20),
        "starttime": field(22),
        "vsize": field(23),
        "rss_pages": field(24),
        "rt_priority": field(40),
        "policy": field(41),
    }


def read_stat(pid: int, proc_root: str | Path | None = None) -> dict[str, Any] | None:
    return read_stat_file(proc_path(proc_root) / str(pid) / "stat")


def read_thread_stat(
    pid: int,
    tid: int,
    proc_root: str | Path | None = None,
) -> dict[str, Any] | None:
    return read_stat_file(proc_path(proc_root) / str(pid) / "task" / str(tid) / "stat")


def read_stat_file(path: str | Path) -> dict[str, Any] | None:
    content = safe_read_text(path)
    if content is None:
        return None
    try:
        return parse_stat_content(content)
    except ValueError:
        return None


def read_cmdline(pid: int, proc_root: str | Path | None = None) -> str:
    raw = safe_read_bytes(proc_path(proc_root) / str(pid) / "cmdline")
    if not raw:
        stat = read_stat(pid, proc_root)
        return f"[{stat['comm']}]" if stat else ""
    text = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    return text


def username_for_uid(uid: int) -> str:
    if pwd is None:
        return str(uid)
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def group_for_gid(gid: int) -> str:
    if grp is None:
        return str(gid)
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


def uid_gid_from_status(status: dict[str, str]) -> tuple[int, int, str, str]:
    uid = safe_int((status.get("Uid") or "0").split()[0])
    gid = safe_int((status.get("Gid") or "0").split()[0])
    return uid, gid, username_for_uid(uid), group_for_gid(gid)


def process_ticks(stat: dict[str, Any]) -> int:
    return safe_int(stat.get("utime")) + safe_int(stat.get("stime"))


def calc_cpu_percent(
    previous_ticks: int | None,
    current_ticks: int,
    previous_total: int | None,
    current_total: int,
    cpu_count: int | None = None,
) -> float:
    if previous_ticks is None or previous_total is None:
        return 0.0
    delta_proc = current_ticks - previous_ticks
    delta_total = current_total - previous_total
    if delta_proc < 0 or delta_total <= 0:
        return 0.0
    cores = cpu_count or os.cpu_count() or 1
    return round((delta_proc / delta_total) * 100.0 * cores, 2)


def read_total_jiffies(proc_root: str | Path | None = None) -> int:
    return sum(read_global_cpu_times(proc_root).values())


def read_global_cpu_times(proc_root: str | Path | None = None) -> dict[str, int]:
    content = safe_read_text(proc_path(proc_root) / "stat")
    if not content:
        return {key: 0 for key in STAT_CPU_KEYS}
    for line in content.splitlines():
        if line.startswith("cpu "):
            values = [safe_int(value) for value in line.split()[1:]]
            return {
                key: values[index] if index < len(values) else 0
                for index, key in enumerate(STAT_CPU_KEYS)
            }
    return {key: 0 for key in STAT_CPU_KEYS}


def cpu_delta_percentages(
    previous: dict[str, int] | None,
    current: dict[str, int],
) -> dict[str, float]:
    if previous is None:
        return {key: 0.0 for key in current}
    deltas = {key: max(0, current.get(key, 0) - previous.get(key, 0)) for key in current}
    total = sum(deltas.values())
    if total <= 0:
        return {key: 0.0 for key in current}
    return {key: round(value * 100.0 / total, 2) for key, value in deltas.items()}


def read_loadavg(proc_root: str | Path | None = None) -> dict[str, Any]:
    content = safe_read_text(proc_path(proc_root) / "loadavg")
    if not content:
        return {"1m": 0.0, "5m": 0.0, "15m": 0.0, "running": "0/0", "last_pid": 0}
    parts = content.split()
    return {
        "1m": float(parts[0]) if len(parts) > 0 else 0.0,
        "5m": float(parts[1]) if len(parts) > 1 else 0.0,
        "15m": float(parts[2]) if len(parts) > 2 else 0.0,
        "running": parts[3] if len(parts) > 3 else "0/0",
        "last_pid": safe_int(parts[4]) if len(parts) > 4 else 0,
    }


def parse_meminfo_content(content: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in content.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key] = parse_kb(value)
    return result


def read_meminfo(proc_root: str | Path | None = None) -> dict[str, int]:
    content = safe_read_text(proc_path(proc_root) / "meminfo")
    return parse_meminfo_content(content or "")


def read_uptime(proc_root: str | Path | None = None) -> dict[str, float]:
    content = safe_read_text(proc_path(proc_root) / "uptime")
    if not content:
        return {"uptime": 0.0, "idle": 0.0}
    parts = content.split()
    return {
        "uptime": float(parts[0]) if len(parts) > 0 else 0.0,
        "idle": float(parts[1]) if len(parts) > 1 else 0.0,
    }


def read_boot_time(proc_root: str | Path | None = None) -> int:
    content = safe_read_text(proc_path(proc_root) / "stat")
    if not content:
        return 0
    for line in content.splitlines():
        if line.startswith("btime "):
            return safe_int(line.split()[1])
    return 0


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def classify_fd_target(target: str) -> str:
    lowered = target.lower()
    if lowered.startswith("socket:"):
        return "socket"
    if lowered.startswith("pipe:"):
        return "pipe"
    if lowered.startswith("anon_inode:"):
        return "anon_inode"
    if lowered.startswith("/dev/pts") or lowered.startswith("/dev/tty"):
        return "tty"
    if lowered.startswith("memfd:"):
        return "memfd"
    if target.startswith("/"):
        return "file"
    return "other"


def read_fds(pid: int, proc_root: str | Path | None = None) -> dict[str, Any]:
    fd_dir = proc_path(proc_root) / str(pid) / "fd"
    entries: list[dict[str, Any]] = []
    try:
        names = sorted(fd_dir.iterdir(), key=lambda item: safe_int(item.name, 999999))
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError) as exc:
        return {"items": entries, "error": type(exc).__name__}

    for entry in names:
        try:
            target = os.readlink(entry)
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError) as exc:
            target = f"<{type(exc).__name__}>"
        entries.append(
            {
                "fd": safe_int(entry.name),
                "target": target,
                "type": classify_fd_target(target),
            }
        )
    return {"items": entries, "error": None}


def list_threads(pid: int, proc_root: str | Path | None = None) -> list[int]:
    task_dir = proc_path(proc_root) / str(pid) / "task"
    try:
        return sorted(safe_int(entry.name) for entry in task_dir.iterdir() if entry.name.isdigit())
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return []


def read_thread_comm(pid: int, tid: int, proc_root: str | Path | None = None) -> str:
    content = safe_read_text(proc_path(proc_root) / str(pid) / "task" / str(tid) / "comm")
    return (content or "").strip()


def read_thread_status(
    pid: int,
    tid: int,
    proc_root: str | Path | None = None,
) -> dict[str, str] | None:
    content = safe_read_text(proc_path(proc_root) / str(pid) / "task" / str(tid) / "status")
    if content is None:
        return None
    return parse_status_content(content)


def maps_category(perms: str, pathname: str) -> str:
    if pathname.startswith("[heap]"):
        return "heap"
    if pathname.startswith("[stack"):
        return "stack"
    if "s" in perms:
        return "shared"
    if "x" in perms:
        return "text"
    if perms.startswith("rw"):
        return "data"
    return "other"


def read_memory_segments(pid: int, proc_root: str | Path | None = None) -> dict[str, int]:
    content = safe_read_text(proc_path(proc_root) / str(pid) / "maps")
    totals = {"text": 0, "data": 0, "heap": 0, "stack": 0, "shared": 0, "other": 0}
    if content is None:
        return totals
    for line in content.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) < 2 or "-" not in parts[0]:
            continue
        start_hex, end_hex = parts[0].split("-", 1)
        perms = parts[1]
        pathname = parts[5] if len(parts) > 5 else ""
        try:
            size_kb = (int(end_hex, 16) - int(start_hex, 16)) // 1024
        except ValueError:
            continue
        totals[maps_category(perms, pathname)] += max(0, size_kb)
    return totals


def signal_names_from_mask(mask_hex: str | None) -> list[str]:
    if not mask_hex:
        return []
    try:
        mask = int(mask_hex.strip(), 16)
    except ValueError:
        return []
    names: list[str] = []
    for signum in range(1, 65):
        if not mask & (1 << (signum - 1)):
            continue
        try:
            names.append(signal.Signals(signum).name)
        except ValueError:
            names.append(f"SIG{signum}")
    return names


def process_memory_from_status(status: dict[str, str]) -> dict[str, int]:
    return {key: parse_kb(status.get(key)) for key in MEMORY_KEYS}


def process_identity(pid: int, proc_root: str | Path | None = None) -> dict[str, Any] | None:
    status = read_status(pid, proc_root)
    stat = read_stat(pid, proc_root)
    if status is None or stat is None:
        return None
    uid, gid, user, group = uid_gid_from_status(status)
    return {
        "pid": pid,
        "ppid": safe_int(status.get("PPid"), stat["ppid"]),
        "uid": uid,
        "gid": gid,
        "usuario": user,
        "grupo": group,
        "estado": stat["state"],
        "comm": stat["comm"],
        "cmdline": read_cmdline(pid, proc_root),
        "threads": safe_int(status.get("Threads"), stat.get("num_threads", 0)),
        "rss_kb": parse_kb(status.get("VmRSS")),
        "starttime": stat["starttime"],
    }


def count_processes(
    pids: list[int],
    proc_root: str | Path | None = None,
) -> dict[str, Any]:
    states: Counter[str] = Counter()
    total_threads = 0
    for pid in pids:
        stat = read_stat(pid, proc_root)
        if stat is None:
            continue
        states[stat["state"]] += 1
        total_threads += safe_int(stat.get("num_threads"))
    return {
        "total": sum(states.values()),
        "por_estado": dict(states),
        "threads_total": total_threads,
        "zombies": states.get("Z", 0),
    }


def snapshot_timestamp() -> dict[str, Any]:
    now = time.time()
    return {"epoch": now, "iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))}


def policy_name(policy: int) -> str:
    return SCHED_POLICIES.get(policy, f"UNKNOWN({policy})")
