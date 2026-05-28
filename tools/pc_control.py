"""Windows PC automation tool."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time
import json
import tempfile
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional in scaffold tests
    psutil = None

try:
    import pyautogui

    pyautogui.FAILSAFE = True
except Exception:  # pragma: no cover - optional in scaffold tests
    class _PyAutoGui:
        FAILSAFE = True

    pyautogui = _PyAutoGui()

from core.config import DATA_DIR, config_value, reload_config

AUDITED_ACTIONS = {
    "open_app",
    "close_app",
    "open_path",
    "list_files",
    "read_file",
    "run_command",
    "mouse_position",
    "screen_size",
    "set_brightness",
    "get_brightness",
    "adjust_brightness",
    "move_mouse",
    "click",
    "double_click",
    "right_click",
    "drag_mouse",
    "scroll",
    "type_text",
    "press_key",
    "hotkey",
    "set_volume",
    "get_volume",
    "adjust_volume",
    "mute_volume",
    "screenshot",
    "focus_window",
    "active_window",
    "pc_awareness_snapshot",
    "list_running_apps",
    "list_installed_apps",
    "list_desktop_apps",
    "find_app",
    "inspect_screen",
    "screen_step",
    "inspect_browser",
    "playwright_inspect",
    "playwright_open",
    "playwright_run",
    "inspect_accessibility",
    "open_browser_debug",
    "visual_monitor_start",
    "visual_monitor_stop",
    "visual_monitor_status",
    "visual_capture_once",
    "desktop_task",
    "desktop_task_pause",
    "desktop_task_resume",
    "desktop_task_confirm",
    "desktop_task_cancel",
    "wait",
}


def _apps() -> dict[str, str]:
    apps = reload_config().get("allowed_apps", {})
    if isinstance(apps, dict):
        return {str(k).lower(): str(v) for k, v in apps.items()}
    return {str(name).lower(): str(name) for name in apps}


def _blocked_paths() -> list[str]:
    return [str(p) for p in config_value("blocked_paths", [])]


ALLOWED_APPS = _apps()
BLOCKED_PATHS = _blocked_paths()


def execute(inputs: dict[str, Any]) -> str:
    action = inputs.get("action")
    target = str(inputs.get("target", ""))
    permission_reply = _permission_reply(inputs)
    if permission_reply:
        return permission_reply
    if action == "open_app":
        return _open_app(target)
    if action == "close_app":
        return _close_app(target)
    if action == "open_path":
        return _open_path(target)
    if action == "list_files":
        return _list_files(target)
    if action == "read_file":
        return _read_file(target)
    if action == "run_command":
        return _run_command(target)
    if action == "mouse_position":
        return _mouse_position()
    if action == "screen_size":
        return _screen_size_message()
    if action == "set_brightness":
        return _set_brightness(inputs)
    if action == "get_brightness":
        return _get_brightness()
    if action == "adjust_brightness":
        return _adjust_brightness(inputs)
    if action == "move_mouse":
        return _move_mouse(inputs)
    if action == "click":
        return _click(inputs)
    if action == "double_click":
        merged = dict(inputs)
        merged["clicks"] = 2
        return _click(merged)
    if action == "right_click":
        merged = dict(inputs)
        merged["button"] = "right"
        return _click(merged)
    if action == "drag_mouse":
        return _drag_mouse(inputs)
    if action == "scroll":
        return _scroll(inputs)
    if action == "type_text":
        return _type_text(inputs)
    if action == "press_key":
        return _press_key(inputs)
    if action == "hotkey":
        return _hotkey(inputs)
    if action == "set_volume":
        return _set_volume(inputs)
    if action == "get_volume":
        return _get_volume()
    if action == "adjust_volume":
        return _adjust_volume(inputs)
    if action == "mute_volume":
        return _mute_volume(inputs)
    if action == "screenshot":
        return _screenshot(target)
    if action == "focus_window":
        return _focus_window(target)
    if action == "active_window":
        return _active_window()
    if action == "pc_awareness_snapshot":
        return _pc_awareness_snapshot(inputs)
    if action == "list_running_apps":
        return _list_running_apps(inputs)
    if action == "list_installed_apps":
        return _list_installed_apps(inputs)
    if action == "list_desktop_apps":
        return _list_desktop_apps(inputs)
    if action == "find_app":
        return _find_app(inputs)
    if action == "inspect_screen":
        return _inspect_screen(inputs, act=False)
    if action == "screen_step":
        return _inspect_screen(inputs, act=True)
    if action == "inspect_browser":
        return _inspect_browser(inputs)
    if action == "playwright_inspect":
        return _playwright_inspect(inputs)
    if action == "playwright_open":
        return _playwright_open(inputs)
    if action == "playwright_run":
        return _playwright_run(inputs)
    if action == "inspect_accessibility":
        return _inspect_accessibility(inputs)
    if action == "open_browser_debug":
        return _open_browser_debug(inputs)
    if action == "visual_monitor_start":
        return _visual_monitor_start(inputs)
    if action == "visual_monitor_stop":
        return _visual_monitor_stop(inputs)
    if action == "visual_monitor_status":
        return _visual_monitor_status(inputs)
    if action == "visual_capture_once":
        return _visual_capture_once(inputs)
    if action == "desktop_task":
        return _desktop_task(inputs)
    if action == "desktop_task_pause":
        return _desktop_task_control(inputs, "pause")
    if action == "desktop_task_resume":
        return _desktop_task_control(inputs, "resume")
    if action == "desktop_task_confirm":
        return _desktop_task_control(inputs, "confirm")
    if action == "desktop_task_cancel":
        return _desktop_task_control(inputs, "cancel")
    if action == "wait":
        return _wait(inputs)
    return "Unknown action."


def _permission_reply(inputs: dict[str, Any]) -> str:
    try:
        from core import permissions

        decision = permissions.evaluate("pc_control", inputs)
        if decision["blocked"]:
            return f"Permission blocked: {decision['label']} is set to block."
        if decision["requires_confirmation"] and not inputs.get("_permission_confirmed"):
            return f"Permission required: {decision['label']} is set to ask first."
    except Exception:
        return ""
    return ""


def _open_app(name: str) -> str:
    name = name.lower().strip()
    path = _apps().get(name)
    if not path:
        if not _full_access_enabled("pc_allow_arbitrary_apps"):
            return f"App {name} is not in the allowed list."
        path = _resolve_app_target(name)
    if not path:
        return f"I could not find an app matching {name}."
    if _should_use_debug_chrome(name, path):
        debug_result = _launch_debug_chrome_for_app(name, path)
        if "opened" in debug_result.lower():
            _log("SUCCESS", f"[PC] action=open_app target={name} path={path} result=ok debug_chrome=true")
            return debug_result
    try:
        os.startfile(path)
    except OSError as exc:
        _log("ERROR", f"[PC] action=open_app target={name} path={path} result=error detail={exc}")
        return f"I could not open {name.title()}."
    _log("SUCCESS", f"[PC] action=open_app target={name} path={path} result=ok")
    return f"{name.title()} opened successfully."


def _should_use_debug_chrome(name: str, path: str) -> bool:
    if not bool(config_value("browser_dom_launch_chrome_debug", True)):
        return False
    lowered = f"{name} {path}".lower()
    return name in {"chrome", "gmail", "browser"} or "chrome.exe" in lowered or "mail.google.com" in lowered


def _launch_debug_chrome_for_app(name: str, path: str) -> str:
    url = path if _looks_like_uri(path) else ""
    if name == "gmail" and not url:
        url = "https://mail.google.com/"
    try:
        from core import browser_dom

        return browser_dom.launch_debug_chrome(url)
    except Exception as exc:
        return f"Could not launch Chrome debug mode: {exc}"


def _open_path(path: str) -> str:
    target = _normalize_target_path(path)
    if not target:
        return "Tell me what file or folder to open."
    if _looks_like_uri(target):
        return _start_target(target, label=target)
    if not _is_safe_path(target):
        _log("WARNING", f"[PC] blocked open_path target={target}")
        return "Access denied: path is blocked."
    resolved = Path(target).expanduser()
    if not resolved.exists():
        return f"Path not found: {target}"
    return _start_target(str(resolved), label=resolved.name or str(resolved))


def _close_app(name: str) -> str:
    if psutil is None:
        return "Process control is unavailable because psutil is not installed."
    name = name.lower().strip()
    killed: list[str] = []
    for proc in psutil.process_iter(["name", "pid"]):
        proc_name = str(proc.info.get("name") or "")
        if name and name in proc_name.lower():
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            killed.append(proc_name)
    if not killed:
        return f"No running process found matching {name}."
    return "Closed: " + ", ".join(killed)


def _list_files(path: str) -> str:
    target = Path(path or Path.home())
    if not _is_safe_path(str(target)):
        _log("WARNING", f"[PC] blocked list_files target={target}")
        return "Access denied: path is blocked."
    if not target.exists() or not target.is_dir():
        return f"Folder not found: {target}"
    entries = sorted(p.name for p in target.iterdir())
    _log("SUCCESS", f"[PC] action=list_files target={target} result=ok")
    return "\n".join(entries[:100]) or "Folder is empty."


def _read_file(path: str) -> str:
    if not _is_safe_path(path):
        _log("WARNING", f"[PC] blocked read_file target={path}")
        return "Access denied: path is blocked."
    target = Path(path)
    if not target.exists() or not target.is_file():
        return f"File not found: {path}"
    text = target.read_text(encoding="utf-8", errors="ignore")
    _log("SUCCESS", f"[PC] action=read_file target={target} result=ok")
    if len(text) > 3000:
        size_kb = max(1, target.stat().st_size // 1024)
        return text[:3000] + f"\n... [truncated, file is {size_kb} KB]"
    return text


def _run_command(command: str) -> str:
    if not _full_access_enabled("pc_allow_shell_commands"):
        return "Shell commands are disabled in config."
    command = str(command or "").strip()
    if not command:
        return "Tell me which command to run."
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=float(config_value("pc_shell_timeout_seconds", 20)),
        )
    except subprocess.TimeoutExpired:
        _log("ERROR", f"[PC] action=run_command result=timeout")
        return "Command timed out."
    except Exception as exc:
        _log("ERROR", f"[PC] action=run_command result=error detail={exc}")
        return f"Command failed: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        _log("ERROR", f"[PC] action=run_command result=error code={completed.returncode}")
        return f"Command exited with code {completed.returncode}: {output[:500]}"
    _log("SUCCESS", f"[PC] action=run_command result=ok")
    return output[:1000] or "Command completed."


def _mouse_position() -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    x, y = pyautogui.position()
    _log("SUCCESS", f"[PC] action=mouse_position x={int(x)} y={int(y)} result=ok")
    return f"Mouse is at {int(x)}, {int(y)}."


def _screen_size_message() -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    width, height = _screen_size()
    _log("SUCCESS", f"[PC] action=screen_size width={width} height={height} result=ok")
    return f"Screen size is {width} by {height}."


def _set_brightness(inputs: dict[str, Any]) -> str:
    target = str(inputs.get("target") or "").strip().lower()
    percent = _percent_from_text(target)
    if percent is None:
        return "Tell me what brightness level to set."
    exact = _set_system_brightness_windows(percent)
    if exact is None:
        return "I could not set screen brightness on this display."
    _log("SUCCESS", f"[PC] action=set_brightness target={percent} result=ok verified={exact['brightness']}")
    return f"Screen brightness set to {exact['brightness']}%."


def _get_brightness() -> str:
    exact = _get_system_brightness_windows()
    if exact is None:
        return "I could not read screen brightness on this display."
    _log("SUCCESS", f"[PC] action=get_brightness result=ok brightness={exact['brightness']}")
    return f"Current screen brightness: {exact['brightness']}%."


def _adjust_brightness(inputs: dict[str, Any]) -> str:
    direction = str(inputs.get("direction") or inputs.get("target") or "").strip().lower()
    current = _get_system_brightness_windows()
    if current is None:
        return "I could not read or adjust screen brightness on this display."
    step = max(1, min(50, _int_input(inputs, "step", int(config_value("desktop_brightness_step", 15)))))
    level = int(current["brightness"])
    if direction in {"up", "increase", "raise", "higher", "brighter", "brighten"}:
        target = min(100, level + step)
    elif direction in {"down", "decrease", "lower", "reduce", "reduced", "dim", "dimmer", "darker"}:
        target = max(0, level - step)
    else:
        return "Tell me whether to raise or lower the brightness."
    exact = _set_system_brightness_windows(target)
    if exact is None:
        return "I could not adjust screen brightness on this display."
    _log("SUCCESS", f"[PC] action=adjust_brightness direction={direction} from={level} target={target} result=ok verified={exact['brightness']}")
    return f"Screen brightness set to {exact['brightness']}%."


def _move_mouse(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    try:
        point = _point_from_inputs(inputs, required=True)
    except ValueError as exc:
        return str(exc)
    if point is None:
        return "Tell me the screen coordinates to move the mouse to."
    x, y = point
    duration = _float_input(inputs, "duration", _desktop_duration())
    pyautogui.moveTo(x, y, duration=max(0.0, duration))
    _log("SUCCESS", f"[PC] action=move_mouse x={x} y={y} result=ok")
    return f"Moved mouse to {x}, {y}."


def _click(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    try:
        point = _point_from_inputs(inputs, required=False)
    except ValueError as exc:
        return str(exc)
    button = _button_from_inputs(inputs)
    clicks = max(1, min(5, _int_input(inputs, "clicks", 1)))
    interval = max(0.0, _float_input(inputs, "interval", 0.05))
    if point is None:
        pyautogui.click(button=button, clicks=clicks, interval=interval)
        x, y = pyautogui.position()
    else:
        x, y = point
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
    label = "Right clicked" if button == "right" else "Clicked"
    if clicks == 2 and button == "left":
        label = "Double clicked"
    _log("SUCCESS", f"[PC] action=click x={int(x)} y={int(y)} button={button} clicks={clicks} result=ok")
    return f"{label} at {int(x)}, {int(y)}."


def _drag_mouse(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    try:
        point = _point_from_inputs(inputs, required=True)
    except ValueError as exc:
        return str(exc)
    if point is None:
        return "Tell me the screen coordinates to drag the mouse to."
    x, y = point
    duration = _float_input(inputs, "duration", _desktop_duration())
    button = _button_from_inputs(inputs)
    pyautogui.dragTo(x, y, duration=max(0.0, duration), button=button)
    _log("SUCCESS", f"[PC] action=drag_mouse x={x} y={y} button={button} result=ok")
    return f"Dragged mouse to {x}, {y}."


def _scroll(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    amount = _scroll_amount(inputs)
    pyautogui.scroll(amount)
    direction = "up" if amount > 0 else "down"
    _log("SUCCESS", f"[PC] action=scroll amount={amount} result=ok")
    return f"Scrolled {direction}."


def _type_text(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    text = str(inputs.get("text") or inputs.get("target") or "")
    if not text:
        return "Tell me what text to type."
    max_chars = max(1, int(config_value("desktop_max_type_chars", 1000)))
    if len(text) > max_chars:
        return f"Text is too long to type in one command. Limit is {max_chars} characters."
    interval = max(0.0, _float_input(inputs, "interval", float(config_value("desktop_type_interval_seconds", 0.01))))
    pyautogui.write(text, interval=interval)
    _log("SUCCESS", f"[PC] action=type_text chars={len(text)} result=ok")
    return "Typed the text."


def _press_key(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    key = _key_name(str(inputs.get("key") or inputs.get("target") or ""))
    if not key:
        return "Tell me which key to press."
    presses = max(1, min(20, _int_input(inputs, "presses", 1)))
    pyautogui.press(key, presses=presses)
    _log("SUCCESS", f"[PC] action=press_key key={key} presses={presses} result=ok")
    return f"Pressed {key}."


def _hotkey(inputs: dict[str, Any]) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    keys = _keys_from_inputs(inputs)
    if len(keys) < 2:
        return "Tell me the key combination to press."
    pyautogui.hotkey(*keys)
    combo = "+".join(keys)
    _log("SUCCESS", f"[PC] action=hotkey keys={combo} result=ok")
    return f"Pressed {combo}."


def _set_volume(inputs: dict[str, Any]) -> str:
    target = str(inputs.get("target") or "").strip().lower()
    percent = _volume_percent(target)
    if percent is None:
        return "Tell me what volume level to set."
    exact = _set_system_volume_windows(percent)
    if exact is not None:
        _log("SUCCESS", f"[PC] action=set_volume target={percent} result=ok verified={exact['volume']}")
        return f"Volume set to {exact['volume']}%."
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    if percent <= 0:
        _press_media_key("volumedown", presses=50)
        _log("SUCCESS", f"[PC] action=set_volume target=0 result=sent_unverified")
        return "I sent volume-down keys, but I could not verify the exact volume."
    if percent >= 100:
        _press_media_key("volumeup", presses=50)
        _log("SUCCESS", f"[PC] action=set_volume target=100 result=sent_unverified")
        return "I sent volume-up keys, but I could not verify the exact volume."
    _press_media_key("volumedown", presses=50)
    _press_media_key("volumeup", presses=max(1, round(percent / 2)))
    _log("SUCCESS", f"[PC] action=set_volume target={percent} result=sent_unverified")
    return "I sent volume key presses, but I could not verify the exact volume."


def _get_volume() -> str:
    exact = _get_system_volume_windows()
    if exact is not None:
        muted = " and muted" if exact["muted"] else ""
        _log("SUCCESS", f"[PC] action=get_volume result=ok volume={exact['volume']} muted={exact['muted']}")
        return f"Current volume: {exact['volume']}%{muted}."
    return "I could not read the current PC volume."


def _adjust_volume(inputs: dict[str, Any]) -> str:
    direction = str(inputs.get("direction") or inputs.get("target") or "").strip().lower()
    presses = max(1, min(50, _int_input(inputs, "presses", 5)))
    exact = _get_system_volume_windows()
    if exact is not None:
        level = int(exact["volume"])
        step = _volume_adjust_step(inputs, presses)
        if direction in {"up", "increase", "raise", "higher", "louder"}:
            target = min(100, level + step)
        elif direction in {"down", "decrease", "lower", "reduce", "reduced", "quieter"}:
            target = max(0, level - step)
        else:
            return "Tell me whether to raise or lower the volume."
        result = _set_system_volume_windows(target)
        if result is not None:
            _log("SUCCESS", f"[PC] action=adjust_volume direction={direction} from={level} target={target} result=ok verified={result['volume']}")
            return f"Volume set to {result['volume']}%."
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    if direction in {"up", "increase", "raise", "higher", "louder"}:
        _press_media_key("volumeup", presses=presses)
        _log("SUCCESS", f"[PC] action=adjust_volume direction=up presses={presses} result=ok")
        return "Volume increased."
    if direction in {"down", "decrease", "lower", "reduce", "reduced", "quieter"}:
        _press_media_key("volumedown", presses=presses)
        _log("SUCCESS", f"[PC] action=adjust_volume direction=down presses={presses} result=ok")
        return "Volume decreased."
    return "Tell me whether to raise or lower the volume."


def _mute_volume(inputs: dict[str, Any] | None = None) -> str:
    target = str((inputs or {}).get("target") or "").strip().lower()
    muted = False if target in {"off", "false", "unmute", "unmuted"} else True
    exact = _set_system_mute_windows(muted)
    if exact is not None:
        _log("SUCCESS", f"[PC] action=mute_volume result=ok volume={exact['volume']} muted={exact['muted']}")
        return "Volume muted." if exact["muted"] else "Volume unmuted."
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    _press_media_key("volumemute")
    _log("SUCCESS", f"[PC] action=mute_volume result=sent_unverified")
    return "I sent the mute key, but I could not verify the mute state."


def _press_media_key(key: str, presses: int = 1) -> None:
    presses = max(1, min(100, int(presses)))
    if _press_media_key_windows(key, presses):
        return
    pyautogui.press(key, presses=presses)


def _press_media_key_windows(key: str, presses: int) -> bool:
    virtual_keys = {
        "volumemute": 0xAD,
        "volumedown": 0xAE,
        "volumeup": 0xAF,
    }
    vk = virtual_keys.get(str(key or "").lower())
    if vk is None or os.name != "nt":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        keyeventf_keyup = 0x0002
        for _ in range(presses):
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, keyeventf_keyup, 0)
            time.sleep(0.01)
        return True
    except Exception:
        return False


def _volume_percent(target: str) -> int | None:
    return _percent_from_text(target)


def _volume_adjust_step(inputs: dict[str, Any], presses: int) -> int:
    if "step" in inputs:
        return max(1, min(50, _int_input(inputs, "step", int(config_value("desktop_volume_step", 10)))))
    return max(1, min(50, presses * 2))


def _percent_from_text(target: str) -> int | None:
    normalized = str(target or "").lower().strip()
    if normalized in {"max", "maximum", "full", "all the way up", "highest"}:
        return 100
    if normalized in {"min", "minimum", "zero", "off", "silent", "mute"}:
        return 0
    import re

    match = re.search(r"(\d{1,3})", normalized)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _set_system_brightness_windows(percent: int) -> dict[str, Any] | None:
    return _run_windows_brightness_action("set", level=max(0, min(100, int(percent))))


def _get_system_brightness_windows() -> dict[str, Any] | None:
    return _run_windows_brightness_action("get")


def _run_windows_brightness_action(action: str, *, level: int | None = None) -> dict[str, Any] | None:
    if os.name != "nt":
        return None
    script = r'''
param([string]$Action, [int]$Level)
$ErrorActionPreference = "Stop"
if ($Action -eq "set") {
    $methods = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop)
    if ($methods.Count -eq 0) {
        throw "No brightness control endpoint found."
    }
    $brightness = [Math]::Max(0, [Math]::Min(100, $Level))
    foreach ($method in $methods) {
        Invoke-CimMethod -InputObject $method -MethodName WmiSetBrightness -Arguments @{ Timeout = 1; Brightness = [byte]$brightness } | Out-Null
    }
    Start-Sleep -Milliseconds 200
}
$monitors = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop)
if ($monitors.Count -eq 0) {
    throw "No brightness status endpoint found."
}
$values = @($monitors | ForEach-Object { [int]$_.CurrentBrightness })
$avg = [int][Math]::Round(($values | Measure-Object -Average).Average)
@{ brightness = $avg; displays = $values.Count } | ConvertTo-Json -Compress
'''
    with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8") as fh:
        script_path = Path(fh.name)
        fh.write(script)
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        str(action),
        str(int(level or 0)),
    ]
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=8.0)
    except Exception as exc:
        _log("WARNING", f"[PC] brightness_wmi_failed detail={exc}")
        return None
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        _log("WARNING", f"[PC] brightness_wmi_failed detail={detail[-1] if detail else completed.returncode}")
        return None
    try:
        parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        _log("WARNING", f"[PC] brightness_wmi_parse_failed detail={exc}")
        return None
    try:
        return {
            "brightness": max(0, min(100, int(parsed.get("brightness", 0)))),
            "displays": max(0, int(parsed.get("displays", 0))),
        }
    except Exception:
        return None


def _set_system_volume_windows(percent: int) -> dict[str, Any] | None:
    return _run_windows_volume_action("set", level=max(0, min(100, int(percent))))


def _get_system_volume_windows() -> dict[str, Any] | None:
    return _run_windows_volume_action("get")


def _set_system_mute_windows(muted: bool) -> dict[str, Any] | None:
    return _run_windows_volume_action("mute", muted=muted)


def _run_windows_volume_action(action: str, *, level: int | None = None, muted: bool | None = None) -> dict[str, Any] | None:
    if os.name != "nt":
        return None
    script = r'''
param([string]$Action, [double]$Level, [string]$Muted)
$ErrorActionPreference = "Stop"
$code = @"
using System;
using System.Runtime.InteropServices;

namespace FridayCoreAudio {
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    public class MMDeviceEnumeratorComObject {}

    public enum EDataFlow { eRender = 0, eCapture = 1, eAll = 2 }
    public enum ERole { eConsole = 0, eMultimedia = 1, eCommunications = 2 }

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(EDataFlow dataFlow, int dwStateMask, IntPtr ppDevices);
        int GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role, out IMMDevice ppDevice);
    }

    [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDevice {
        int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, out IAudioEndpointVolume ppInterface);
    }

    [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioEndpointVolume {
        int RegisterControlChangeNotify(IntPtr pNotify);
        int UnregisterControlChangeNotify(IntPtr pNotify);
        int GetChannelCount(out uint pnChannelCount);
        int SetMasterVolumeLevel(float fLevelDB, Guid pguidEventContext);
        int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
        int GetMasterVolumeLevel(out float pfLevelDB);
        int GetMasterVolumeLevelScalar(out float pfLevel);
        int SetChannelVolumeLevel(uint nChannel, float fLevelDB, Guid pguidEventContext);
        int SetChannelVolumeLevelScalar(uint nChannel, float fLevel, Guid pguidEventContext);
        int GetChannelVolumeLevel(uint nChannel, out float pfLevelDB);
        int GetChannelVolumeLevelScalar(uint nChannel, out float pfLevel);
        int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
        int GetMute(out bool pbMute);
        int GetVolumeStepInfo(out uint pnStep, out uint pnStepCount);
        int VolumeStepUp(Guid pguidEventContext);
        int VolumeStepDown(Guid pguidEventContext);
        int QueryHardwareSupport(out uint pdwHardwareSupportMask);
        int GetVolumeRange(out float pflVolumeMindB, out float pflVolumeMaxdB, out float pflVolumeIncrementdB);
    }

    public class Audio {
        public static IAudioEndpointVolume Endpoint() {
            var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
            IMMDevice device;
            Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia, out device));
            Guid iid = typeof(IAudioEndpointVolume).GUID;
            IAudioEndpointVolume endpoint;
            Marshal.ThrowExceptionForHR(device.Activate(ref iid, 23, IntPtr.Zero, out endpoint));
            return endpoint;
        }

        public static void SetVolume(double level) {
            var endpoint = Endpoint();
            Guid context = Guid.Empty;
            Marshal.ThrowExceptionForHR(endpoint.SetMasterVolumeLevelScalar((float)level, context));
            if (level > 0.0) {
                Marshal.ThrowExceptionForHR(endpoint.SetMute(false, context));
            }
        }

        public static void SetMute(bool muted) {
            var endpoint = Endpoint();
            Guid context = Guid.Empty;
            Marshal.ThrowExceptionForHR(endpoint.SetMute(muted, context));
        }

        public static float GetVolume() {
            var endpoint = Endpoint();
            float level;
            Marshal.ThrowExceptionForHR(endpoint.GetMasterVolumeLevelScalar(out level));
            return level;
        }

        public static bool GetMute() {
            var endpoint = Endpoint();
            bool muted;
            Marshal.ThrowExceptionForHR(endpoint.GetMute(out muted));
            return muted;
        }
    }
}
"@
Add-Type -TypeDefinition $code
if ($Action -eq "set") {
    [FridayCoreAudio.Audio]::SetVolume([Math]::Max(0, [Math]::Min(100, $Level)) / 100.0)
} elseif ($Action -eq "mute") {
    [FridayCoreAudio.Audio]::SetMute($Muted -eq "true")
}
$volume = [int][Math]::Round([FridayCoreAudio.Audio]::GetVolume() * 100)
$isMuted = [FridayCoreAudio.Audio]::GetMute()
@{ volume = $volume; muted = $isMuted } | ConvertTo-Json -Compress
'''
    with tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8") as fh:
        script_path = Path(fh.name)
        fh.write(script)
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        str(action),
        str(float(level or 0)),
        "true" if muted else "false",
    ]
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=8.0)
    except Exception as exc:
        _log("WARNING", f"[PC] volume_core_audio_failed detail={exc}")
        return None
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        _log("WARNING", f"[PC] volume_core_audio_failed detail={detail[-1] if detail else completed.returncode}")
        return None
    try:
        parsed = json.loads((completed.stdout or "").strip().splitlines()[-1])
    except Exception as exc:
        _log("WARNING", f"[PC] volume_core_audio_parse_failed detail={exc}")
        return None
    try:
        return {"volume": max(0, min(100, int(parsed.get("volume", 0)))), "muted": bool(parsed.get("muted", False))}
    except Exception:
        return None


def _screenshot(path: str = "") -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    raw_target = str(path or "").strip().strip('"')
    if raw_target:
        target = Path(raw_target).expanduser()
        if target.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            target = target / _screenshot_filename()
    else:
        target = _screenshot_dir() / _screenshot_filename()
    if not _is_safe_path(str(target)):
        _log("WARNING", f"[PC] blocked screenshot target={target}")
        return "Access denied: screenshot path is blocked."
    target.parent.mkdir(parents=True, exist_ok=True)
    image = pyautogui.screenshot()
    image.save(str(target))
    _log("SUCCESS", f"[PC] action=screenshot target={target} result=ok")
    return f"Screenshot saved to {target}."


def _focus_window(title: str) -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    target = str(title or "").strip()
    if not target:
        return "Tell me which window to focus."
    finder = getattr(pyautogui, "getWindowsWithTitle", None)
    if not callable(finder):
        return "Window focusing is unavailable on this system."
    windows = [window for window in finder(target) if window]
    if not windows:
        return f"I could not find a window matching {target}."
    window = windows[0]
    try:
        if getattr(window, "isMinimized", False):
            window.restore()
        window.activate()
    except Exception as exc:
        return f"I could not focus {target}: {exc}"
    _log("SUCCESS", f"[PC] action=focus_window target={target} result=ok")
    return f"Focused {target}."


def _active_window() -> str:
    unavailable = _desktop_unavailable()
    if unavailable:
        return unavailable
    getter = getattr(pyautogui, "getActiveWindow", None)
    if not callable(getter):
        return "Active window lookup is unavailable on this system."
    window = getter()
    if not window:
        return "No active window found."
    title = str(getattr(window, "title", "") or "Untitled")
    left = int(getattr(window, "left", 0) or 0)
    top = int(getattr(window, "top", 0) or 0)
    width = int(getattr(window, "width", 0) or 0)
    height = int(getattr(window, "height", 0) or 0)
    _log("SUCCESS", f"[PC] action=active_window target={title} result=ok")
    return f"Active window: {title} at {left}, {top}, size {width} by {height}."


def _pc_awareness_snapshot(inputs: dict[str, Any]) -> str:
    try:
        from core import pc_awareness

        payload = pc_awareness.snapshot(force_refresh=_bool_input(inputs.get("force_refresh", False)))
    except Exception as exc:
        _log("ERROR", f"[PC] action=pc_awareness_snapshot result=error detail={exc}")
        return f"PC awareness failed: {exc}"
    _log("SUCCESS", "[PC] action=pc_awareness_snapshot result=ok")
    summary = str(payload.get("summary") or "PC awareness snapshot ready.")
    stats = payload.get("stats") or {}
    return (
        f"{summary}\n"
        f"Stats: running={stats.get('running_apps', 0)}, installed={stats.get('installed_apps', 0)}, "
        f"desktop={stats.get('desktop_apps', 0)}, shortcuts={stats.get('shortcuts', 0)}."
    )


def _list_running_apps(inputs: dict[str, Any]) -> str:
    try:
        from core import pc_awareness

        items = pc_awareness.running_apps(limit=_int_input(inputs, "limit", 20))
    except Exception as exc:
        _log("ERROR", f"[PC] action=list_running_apps result=error detail={exc}")
        return f"Could not list running apps: {exc}"
    names = [str(item.get("name") or "") for item in items if item.get("name")]
    _log("SUCCESS", f"[PC] action=list_running_apps count={len(items)} result=ok")
    return f"Running apps: {len(items)}. Top: {', '.join(names[:12]) or 'none'}."


def _list_installed_apps(inputs: dict[str, Any]) -> str:
    try:
        from core import pc_awareness

        items = pc_awareness.installed_apps(limit=_int_input(inputs, "limit", 40))
    except Exception as exc:
        _log("ERROR", f"[PC] action=list_installed_apps result=error detail={exc}")
        return f"Could not list installed apps: {exc}"
    names = [str(item.get("name") or "") for item in items if item.get("name")]
    _log("SUCCESS", f"[PC] action=list_installed_apps count={len(items)} result=ok")
    return f"Installed apps in inventory: {len(items)}. Examples: {', '.join(names[:15]) or 'none'}."


def _list_desktop_apps(inputs: dict[str, Any]) -> str:
    try:
        from core import pc_awareness

        items = pc_awareness.desktop_apps(limit=_int_input(inputs, "limit", 40))
    except Exception as exc:
        _log("ERROR", f"[PC] action=list_desktop_apps result=error detail={exc}")
        return f"Could not list Desktop apps: {exc}"
    names = [str(item.get("name") or "") for item in items if item.get("name")]
    _log("SUCCESS", f"[PC] action=list_desktop_apps count={len(items)} result=ok")
    return f"Desktop/Home-screen apps: {len(items)}. Items: {', '.join(names[:15]) or 'none'}."


def _find_app(inputs: dict[str, Any]) -> str:
    query = str(inputs.get("query") or inputs.get("target") or "").strip()
    if not query:
        return "Tell me which app to find."
    try:
        from core import pc_awareness

        result = pc_awareness.find_app(query)
    except Exception as exc:
        _log("ERROR", f"[PC] action=find_app target={query} result=error detail={exc}")
        return f"App lookup failed: {exc}"
    if not result.get("found"):
        _log("INFO", f"[PC] action=find_app target={query} result=not_found")
        return f"I could not find {query} in the PC awareness inventory."
    _log("SUCCESS", f"[PC] action=find_app target={query} result=ok source={result.get('source')}")
    return f"Found {result.get('name')} from {result.get('source')}; launch target: {result.get('launch_target')}."


def _wait(inputs: dict[str, Any]) -> str:
    seconds = min(30.0, max(0.1, _float_input(inputs, "seconds", _float_input(inputs, "target", 1.0))))
    time.sleep(seconds)
    _log("SUCCESS", f"[PC] action=wait seconds={seconds:g} result=ok")
    return f"Waited {seconds:g} seconds."


def _inspect_screen(inputs: dict[str, Any], *, act: bool) -> str:
    instruction = str(inputs.get("instruction") or inputs.get("target") or "")
    try:
        from core import desktop_vision

        result = desktop_vision.inspect_screen(instruction, act=act or bool(inputs.get("act")))
    except Exception as exc:
        _log("ERROR", f"[PC] action={'screen_step' if act else 'inspect_screen'} result=error detail={exc}")
        return f"Screen inspection failed: {exc}"
    _log("SUCCESS", f"[PC] action={'screen_step' if act else 'inspect_screen'} result=ok")
    return result


def _desktop_task(inputs: dict[str, Any]) -> str:
    instruction = str(inputs.get("instruction") or inputs.get("target") or "")
    try:
        from core import desktop_vision

        result = desktop_vision.run_desktop_task(instruction, max_steps=_int_input(inputs, "max_steps", 0) or None)
    except Exception as exc:
        _log("ERROR", f"[PC] action=desktop_task result=error detail={exc}")
        return f"Desktop task failed: {exc}"
    _log("SUCCESS", f"[PC] action=desktop_task result=ok")
    return result


def _inspect_browser(inputs: dict[str, Any]) -> str:
    try:
        from core import browser_dom

        payload = browser_dom.context_summary(limit=_int_input(inputs, "limit", 40))
    except Exception as exc:
        _log("ERROR", f"[PC] action=inspect_browser result=error detail={exc}")
        return f"Browser inspection failed: {exc}"
    _log("SUCCESS", "[PC] action=inspect_browser result=ok")
    return json.dumps(payload, ensure_ascii=True, indent=2)[:4000]


def _playwright_inspect(inputs: dict[str, Any]) -> str:
    url = str(inputs.get("url") or inputs.get("target") or "").strip()
    if not url:
        return "Tell me which website to inspect with Playwright."
    try:
        from core import browser_playwright

        payload = browser_playwright.inspect_url(url, limit=_int_input(inputs, "limit", 40))
    except Exception as exc:
        _log("ERROR", f"[PC] action=playwright_inspect result=error detail={exc}")
        return f"Playwright inspection failed: {exc}"
    _log("SUCCESS", "[PC] action=playwright_inspect result=ok")
    return json.dumps(payload, ensure_ascii=True, indent=2)[:4000]


def _playwright_open(inputs: dict[str, Any]) -> str:
    url = str(inputs.get("url") or inputs.get("target") or "").strip()
    if not url:
        return "Tell me which website to open with Playwright."
    try:
        from core import browser_playwright

        payload = browser_playwright.open_url(url)
    except Exception as exc:
        _log("ERROR", f"[PC] action=playwright_open result=error detail={exc}")
        return f"Playwright could not open that website: {exc}"
    if not payload.get("ok") and payload.get("available") is False:
        return f"Playwright unavailable: {payload.get('install_hint') or payload.get('reason')}"
    _log("SUCCESS", "[PC] action=playwright_open result=ok")
    return f"Playwright opened {url}."


def _playwright_run(inputs: dict[str, Any]) -> str:
    url = str(inputs.get("url") or inputs.get("target") or "").strip()
    steps = inputs.get("steps") or []
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except Exception:
            steps = []
    if not url:
        return "Tell me which website to control with Playwright."
    if not isinstance(steps, list):
        return "Playwright steps must be a list."
    try:
        from core import browser_playwright

        payload = browser_playwright.run_steps(url, steps)
    except Exception as exc:
        _log("ERROR", f"[PC] action=playwright_run result=error detail={exc}")
        return f"Playwright task failed: {exc}"
    if not payload.get("ok"):
        return f"Playwright could not finish: {payload.get('reason') or payload.get('detail') or 'step failed'}"
    _log("SUCCESS", "[PC] action=playwright_run result=ok")
    return f"Playwright completed {len(payload.get('steps') or [])} browser step(s)."


def _inspect_accessibility(inputs: dict[str, Any]) -> str:
    try:
        from core import app_accessibility

        payload = app_accessibility.context_summary(limit=_int_input(inputs, "limit", 40))
    except Exception as exc:
        _log("ERROR", f"[PC] action=inspect_accessibility result=error detail={exc}")
        return f"Accessibility inspection failed: {exc}"
    _log("SUCCESS", "[PC] action=inspect_accessibility result=ok")
    return json.dumps(payload, ensure_ascii=True, indent=2)[:4000]


def _open_browser_debug(inputs: dict[str, Any]) -> str:
    url = str(inputs.get("url") or inputs.get("target") or "").strip()
    try:
        from core import browser_dom

        result = browser_dom.launch_debug_chrome(url)
    except Exception as exc:
        _log("ERROR", f"[PC] action=open_browser_debug result=error detail={exc}")
        return f"Could not open browser debug mode: {exc}"
    _log("SUCCESS", "[PC] action=open_browser_debug result=ok")
    return result


def _visual_monitor_start(inputs: dict[str, Any]) -> str:
    source = _visual_source(inputs)
    try:
        from core import visual_monitor

        payload = visual_monitor.start_monitor(source)
    except Exception as exc:
        _log("ERROR", f"[PC] action=visual_monitor_start source={source} result=error detail={exc}")
        return f"Visual monitor could not start: {exc}"
    _log("SUCCESS", f"[PC] action=visual_monitor_start source={payload.get('source') or source} result=ok")
    return _visual_monitor_message("Visual monitor started", payload)


def _visual_monitor_stop(inputs: dict[str, Any]) -> str:
    try:
        from core import visual_monitor

        payload = visual_monitor.stop_monitor()
    except Exception as exc:
        _log("ERROR", f"[PC] action=visual_monitor_stop result=error detail={exc}")
        return f"Visual monitor could not stop: {exc}"
    _log("SUCCESS", "[PC] action=visual_monitor_stop result=ok")
    return _visual_monitor_message("Visual monitor stopped", payload)


def _visual_monitor_status(inputs: dict[str, Any]) -> str:
    try:
        from core import visual_monitor

        payload = visual_monitor.status()
    except Exception as exc:
        _log("ERROR", f"[PC] action=visual_monitor_status result=error detail={exc}")
        return f"Visual monitor status failed: {exc}"
    _log("SUCCESS", "[PC] action=visual_monitor_status result=ok")
    return _visual_monitor_message("Visual monitor status", payload)


def _visual_capture_once(inputs: dict[str, Any]) -> str:
    source = _visual_source(inputs)
    analyze_raw = inputs.get("analyze", None)
    analyze = None if analyze_raw is None else _bool_input(analyze_raw)
    try:
        from core import visual_monitor

        events = visual_monitor.capture_once(source, analyze=analyze)
    except Exception as exc:
        _log("ERROR", f"[PC] action=visual_capture_once source={source} result=error detail={exc}")
        return f"Visual capture failed: {exc}"
    _log("SUCCESS", f"[PC] action=visual_capture_once source={source} result=ok count={len(events)}")
    summaries = "; ".join(str(item.get("summary") or item.get("event_type") or "") for item in events)
    return f"Captured {len(events)} visual frame{'s' if len(events) != 1 else ''}. {summaries}".strip()


def _visual_monitor_message(prefix: str, payload: dict[str, Any]) -> str:
    running = "running" if payload.get("running") else "stopped"
    source = payload.get("source") or "screen"
    event_count = int(payload.get("event_count") or 0)
    latest = payload.get("latest_event") or {}
    latest_summary = str(latest.get("summary") or "").strip()
    suffix = f" Latest: {latest_summary}" if latest_summary else ""
    return f"{prefix}: {running}, source={source}, events={event_count}.{suffix}"


def _visual_source(inputs: dict[str, Any]) -> str:
    source = str(inputs.get("source") or inputs.get("target") or "screen").strip().lower()
    if source in {"screen", "camera", "both"}:
        return source
    if "camera" in source and "screen" in source:
        return "both"
    if "camera" in source or "webcam" in source:
        return "camera"
    return "screen"


def _bool_input(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "analyze"}


def _desktop_task_control(inputs: dict[str, Any], control: str) -> str:
    session_id = _int_input(inputs, "session_id", _int_input(inputs, "target", 0)) or None
    try:
        from core import desktop_vision

        if control == "pause":
            result = desktop_vision.pause_desktop_task(session_id)
        elif control == "resume":
            result = desktop_vision.resume_desktop_task(session_id)
        elif control == "confirm":
            result = desktop_vision.confirm_desktop_task(session_id)
        elif control == "cancel":
            result = desktop_vision.cancel_desktop_task(session_id)
        else:
            result = "Unknown desktop task control."
    except Exception as exc:
        _log("ERROR", f"[PC] action=desktop_task_{control} result=error detail={exc}")
        return f"Desktop task {control} failed: {exc}"
    _log("SUCCESS", f"[PC] action=desktop_task_{control} result=ok")
    return result


def _is_safe_path(path: str) -> bool:
    try:
        real = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        if not _full_access_enabled("pc_allow_arbitrary_paths") and not str(real).lower().startswith(str(home).lower()):
            return False
        for blocked in _blocked_paths():
            if str(real).lower().startswith(str(Path(blocked).resolve()).lower()):
                return False
        return True
    except Exception:
        return False


def _resolve_app_target(name: str) -> str:
    raw = str(name or "").strip().strip('"')
    normalized = " ".join(raw.lower().split())
    aliases = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "camera": "ms-camera:",
        "windows camera": "ms-camera:",
        "photos": "ms-photos:",
        "paint": "mspaint.exe",
        "notepad": "notepad.exe",
        "task manager": "taskmgr.exe",
        "control panel": "control.exe",
        "command prompt": "cmd.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
    }
    if normalized in aliases:
        return aliases[normalized]
    if _looks_like_uri(raw):
        return raw
    expanded = Path(raw).expanduser()
    if expanded.exists():
        return str(expanded)
    candidate = shutil.which(raw) or shutil.which(f"{raw}.exe")
    if candidate:
        return candidate
    try:
        from core import pc_awareness

        match = pc_awareness.find_app(normalized)
        target = str(match.get("launch_target") or "") if match.get("found") else ""
        if target:
            return target
    except Exception:
        pass
    shortcut = _find_start_menu_shortcut(normalized)
    return str(shortcut) if shortcut else ""


def _find_start_menu_shortcut(name: str) -> Path | None:
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    words = [word for word in re_split_words(name) if word]
    if not words:
        return None
    for root in roots:
        if not root.exists():
            continue
        matches = []
        for shortcut in root.rglob("*.lnk"):
            shortcut_name = shortcut.stem.lower()
            if all(word in shortcut_name for word in words):
                matches.append(shortcut)
        if matches:
            return sorted(matches, key=lambda item: (len(item.stem), str(item)))[0]
    return None


def re_split_words(text: str) -> list[str]:
    return [part.strip() for part in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()]


def _normalize_target_path(path: str) -> str:
    raw = str(path or "").strip().strip('"')
    lowered = raw.lower()
    home = Path.home()
    known = {
        "home": home,
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "pictures": home / "Pictures",
        "music": home / "Music",
        "videos": home / "Videos",
        "current folder": Path.cwd(),
        "current directory": Path.cwd(),
        "project": Path.cwd(),
        "workspace": Path.cwd(),
    }
    if lowered in known:
        return str(known[lowered])
    return raw


def _start_target(target: str, label: str) -> str:
    try:
        os.startfile(target)
    except OSError as exc:
        _log("ERROR", f"[PC] action=open_path target={target} result=error detail={exc}")
        return f"I could not open {label}."
    _log("SUCCESS", f"[PC] action=open_path target={target} result=ok")
    return f"Opened {label}."


def _looks_like_uri(value: str) -> bool:
    lowered = str(value or "").lower()
    return "://" in lowered or lowered.startswith(("ms-", "mailto:", "file:"))


def _full_access_enabled(flag: str) -> bool:
    return bool(config_value("pc_trusted_mode_enabled", False)) and bool(config_value(flag, False))


def _desktop_unavailable() -> str:
    if not _full_access_enabled("pc_allow_desktop_automation"):
        return "Desktop automation is disabled in config."
    required = ("position", "size", "moveTo", "click", "scroll", "write", "press", "hotkey", "screenshot")
    if not all(callable(getattr(pyautogui, name, None)) for name in required):
        return "Desktop automation is unavailable because PyAutoGUI is not installed correctly."
    return ""


def _screen_size() -> tuple[int, int]:
    size = pyautogui.size()
    if hasattr(size, "width") and hasattr(size, "height"):
        return int(size.width), int(size.height)
    return int(size[0]), int(size[1])


def _point_from_inputs(inputs: dict[str, Any], required: bool) -> tuple[int, int] | None:
    x_raw = inputs.get("x")
    y_raw = inputs.get("y")
    if x_raw is None or y_raw is None:
        parsed = _parse_point(str(inputs.get("target") or ""))
        if parsed is not None:
            x_raw, y_raw = parsed
    if x_raw is None or y_raw is None:
        return None if required or not str(inputs.get("target") or "").strip() else None
    try:
        x = int(round(float(x_raw)))
        y = int(round(float(y_raw)))
    except (TypeError, ValueError):
        return None
    width, height = _screen_size()
    if x < 0 or y < 0 or x >= width or y >= height:
        raise ValueError(f"Coordinates {x}, {y} are outside the screen size {width} by {height}.")
    return x, y


def _parse_point(text: str) -> tuple[int, int] | None:
    raw = str(text or "").lower()
    import re

    match = re.search(r"x\s*=?\s*(-?\d+)\D+y\s*=?\s*(-?\d+)", raw)
    if match:
        return int(match.group(1)), int(match.group(2))
    numbers = [int(value) for value in re.findall(r"-?\d+", raw)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    return None


def _button_from_inputs(inputs: dict[str, Any]) -> str:
    button = str(inputs.get("button") or "").lower().strip()
    if not button:
        target = str(inputs.get("target") or "").lower()
        if "right" in target:
            button = "right"
        elif "middle" in target:
            button = "middle"
        else:
            button = "left"
    return button if button in {"left", "right", "middle"} else "left"


def _scroll_amount(inputs: dict[str, Any]) -> int:
    raw_amount = inputs.get("amount")
    target = str(inputs.get("target") or "").lower()
    if raw_amount is not None:
        try:
            amount = int(raw_amount)
        except (TypeError, ValueError):
            amount = 0
    else:
        words = re_split_words(target)
        amount = next((int(word) for word in words if word.isdigit()), 5)
        if any(word in words for word in ["down", "lower"]):
            amount *= -1
        elif any(word in words for word in ["up", "upper"]):
            amount = abs(amount)
        else:
            amount *= -1
    if amount == 0:
        amount = -5
    return max(-50, min(50, amount))


def _keys_from_inputs(inputs: dict[str, Any]) -> list[str]:
    raw_keys = inputs.get("keys")
    if isinstance(raw_keys, list):
        return [_key_name(str(key)) for key in raw_keys if _key_name(str(key))]
    text = str(raw_keys or inputs.get("target") or "")
    parts = re_split_words(text.replace("+", " plus "))
    keys = [_key_name(part) for part in parts if part not in {"and", "plus", "then"}]
    return [key for key in keys if key]


def _key_name(key: str) -> str:
    normalized = " ".join(re_split_words(key))
    aliases = {
        "control": "ctrl",
        "ctrl": "ctrl",
        "command": "win",
        "windows": "win",
        "win": "win",
        "escape": "esc",
        "esc": "esc",
        "return": "enter",
        "enter": "enter",
        "space": "space",
        "spacebar": "space",
        "back space": "backspace",
        "backspace": "backspace",
        "delete": "delete",
        "del": "delete",
        "tab": "tab",
        "shift": "shift",
        "alt": "alt",
        "left": "left",
        "right": "right",
        "up": "up",
        "down": "down",
        "page up": "pageup",
        "page down": "pagedown",
        "home": "home",
        "end": "end",
        "caps lock": "capslock",
        "print screen": "printscreen",
    }
    if normalized in aliases:
        return aliases[normalized]
    compact = normalized.replace(" ", "")
    if len(compact) == 1 and compact.isalnum():
        return compact
    if compact.startswith("f") and compact[1:].isdigit() and 1 <= int(compact[1:]) <= 24:
        return compact
    return compact


def _int_input(inputs: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(inputs.get(key, default))
    except (TypeError, ValueError):
        return default


def _float_input(inputs: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(inputs.get(key, default))
    except (TypeError, ValueError):
        return default


def _desktop_duration() -> float:
    return float(config_value("desktop_mouse_duration_seconds", 0.12))


def _screenshot_dir() -> Path:
    configured = str(config_value("desktop_screenshot_dir", "") or "").strip()
    return Path(configured).expanduser() if configured else DATA_DIR / "screenshots"


def _screenshot_filename() -> str:
    import datetime as dt

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"screenshot_{stamp}.png"


def _log(level: str, message: str) -> None:
    if message.startswith("[PC]"):
        _audit_pc_log(level, message)
    try:
        from output.display import log

        log(level, message)
    except Exception:
        return


def _audit_pc_log(level: str, message: str) -> None:
    try:
        from core import audit_log

        fields = _parse_log_fields(message)
        action = fields.get("action") or ("blocked" if "blocked" in message else "pc_action")
        if action not in AUDITED_ACTIONS and action != "blocked":
            return
        target = fields.get("target") or fields.get("path") or fields.get("keys") or fields.get("key") or ""
        success = level.upper() == "SUCCESS" and fields.get("result", "ok") == "ok"
        audit_log.record(
            actor="friday",
            category="pc_control",
            action=action,
            target=target,
            success=success,
            details={"level": level, "message": message, "fields": fields},
        )
    except Exception:
        return


def _parse_log_fields(message: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in str(message).split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key.strip()] = value.strip().strip(",")
    return fields
