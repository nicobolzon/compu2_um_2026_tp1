from __future__ import annotations

import collections
import os
import signal
from typing import Deque


SIGNAL_ORDER = ("SIGINT", "SIGTERM", "SIGHUP", "SIGUSR1", "SIGUSR2", "SIGWINCH")
SIGNAL_NUMBERS = {
    name: getattr(signal, name)
    for name in SIGNAL_ORDER
    if hasattr(signal, name)
}
SIGNAL_INDEX = {number: index for index, number in enumerate(SIGNAL_NUMBERS.values())}


class SignalRouter:
    def __init__(self) -> None:
        self.read_fd: int | None = None
        self.write_fd: int | None = None
        self.old_wakeup_fd: int = -1
        self.old_handlers: dict[int, signal.Handlers | int | None] = {}
        self.fallback: Deque[int] = collections.deque()
        self.using_wakeup_fd = False

    def __enter__(self) -> "SignalRouter":
        self.install()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def install(self) -> None:
        try:
            self.read_fd, self.write_fd = os.pipe()
            os.set_blocking(self.read_fd, False)
            os.set_blocking(self.write_fd, False)
            self.old_wakeup_fd = signal.set_wakeup_fd(self.write_fd)
            self.using_wakeup_fd = True
        except (AttributeError, OSError, ValueError):
            self.close_pipe_only()
            self.using_wakeup_fd = False

        for signum in SIGNAL_NUMBERS.values():
            self.old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handler)

    def _handler(self, signum: int, frame) -> None:
        if not self.using_wakeup_fd:
            self.fallback.append(signum)

    def drain(self) -> list[int]:
        signals: list[int] = []
        if self.using_wakeup_fd and self.read_fd is not None:
            while True:
                try:
                    chunk = os.read(self.read_fd, 1024)
                except BlockingIOError:
                    break
                except OSError:
                    break
                if not chunk:
                    break
                signals.extend(chunk)

        while self.fallback:
            signals.append(self.fallback.popleft())

        return [signum for signum in signals if signum in SIGNAL_INDEX]

    def close_pipe_only(self) -> None:
        for fd in (self.read_fd, self.write_fd):
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError:
                pass
        self.read_fd = None
        self.write_fd = None

    def close(self) -> None:
        if self.using_wakeup_fd:
            try:
                signal.set_wakeup_fd(self.old_wakeup_fd)
            except (OSError, ValueError):
                pass
        for signum, old_handler in self.old_handlers.items():
            try:
                signal.signal(signum, old_handler)
            except (OSError, ValueError):
                pass
        self.old_handlers.clear()
        self.close_pipe_only()
        self.using_wakeup_fd = False
