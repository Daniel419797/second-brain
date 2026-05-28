"""Terminal display, session logging, and desktop notifications."""

from __future__ import annotations

import datetime as _dt
import queue
import threading
from pathlib import Path

try:
    import colorama
    from colorama import Fore, Style
except Exception:  # pragma: no cover - exercised when dependency is absent
    class _Blank:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET_ALL = ""
        BRIGHT = NORMAL = DIM = ""

    class _Colorama:
        @staticmethod
        def init(*args, **kwargs):
            return None

    colorama = _Colorama()
    Fore = Style = _Blank()

try:
    from plyer import notification
except Exception:  # pragma: no cover - exercised when dependency is absent
    notification = None

from core.config import LOG_DIR, config_value, ensure_runtime_dirs

colorama.init(autoreset=True)
ensure_runtime_dirs()

COLOURS = {
    "INFO": Fore.CYAN,
    "SUCCESS": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "DEBUG": Fore.MAGENTA,
    "YOU": Fore.WHITE + Style.BRIGHT,
    "JARVIS": Fore.BLUE + Style.BRIGHT,
    "FRIDAY": Fore.BLUE + Style.BRIGHT,
    "COMPUTER": Fore.BLUE + Style.BRIGHT,
}

_LOG_LOCK = threading.Lock()
_NOTIFY_QUEUE: "queue.Queue[tuple[str, str]]" = queue.Queue()
_SESSION_STAMP = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"session_{_SESSION_STAMP}.log"
_LOG_LEVEL = str(config_value("log_level", "INFO")).upper()


def set_log_level(level: str) -> None:
    global _LOG_LEVEL
    _LOG_LEVEL = (level or "INFO").upper()


def log(level: str, message: str) -> None:
    level = (level or "INFO").upper()
    if level == "DEBUG" and _LOG_LEVEL != "DEBUG":
        return
    ts = _dt.datetime.now().strftime("%H:%M:%S")
    colour = COLOURS.get(level, Fore.WHITE)
    line = f"[{ts}] [{level:<7s}] {message}"
    print(colour + line)
    _write_log(line)


def _write_log(line: str) -> None:
    ensure_runtime_dirs()
    with _LOG_LOCK:
        with Path(LOG_FILE).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def notify(title: str, message: str) -> None:
    try:
        _NOTIFY_QUEUE.put_nowait((title, message))
    except Exception:
        return


def _send_toast(title: str, message: str) -> None:
    if notification is None:
        return
    try:
        notification.notify(title=title, message=message, app_name=str(config_value("jarvis_name", "Friday")), timeout=5)
    except Exception:
        return


def _notification_worker() -> None:
    while True:
        title, message = _NOTIFY_QUEUE.get()
        try:
            _send_toast(title, message)
        finally:
            _NOTIFY_QUEUE.task_done()


def print_banner() -> None:
    assistant_name = str(config_value("jarvis_name", "Friday"))
    lines = [
        f"     {assistant_name}",
        "     Personal AI Agent",
    ]
    for line in lines:
        print(Fore.BLUE + Style.BRIGHT + line)


threading.Thread(target=_notification_worker, daemon=True).start()
