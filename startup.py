"""Per-user startup integration for Windows and freedesktop Linux."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

APP_RUN_VALUE = "Accessible IPTV Client"
LINUX_DESKTOP_FILE = "accessible-iptv-client.desktop"


def supported(platform_name: Optional[str] = None) -> bool:
    name = (platform_name or sys.platform).lower()
    return name.startswith("win") or name.startswith("linux")


def launch_argv(
    *,
    executable: Optional[str] = None,
    argv0: Optional[str] = None,
    frozen: Optional[bool] = None,
) -> list[str]:
    """Return the command that starts this exact installed/source application."""
    exe = executable or sys.executable
    is_frozen = getattr(sys, "frozen", False) if frozen is None else bool(frozen)
    if is_frozen:
        return [os.path.abspath(exe)]
    script = argv0 or (sys.argv[0] if sys.argv else "")
    return [os.path.abspath(exe), os.path.abspath(script)]


def _windows_command(argv: Iterable[str]) -> str:
    return subprocess.list2cmdline(list(argv))


def _desktop_exec(argv: Iterable[str]) -> str:
    # Desktop Entry Exec is not a shell command. Quote each path explicitly.
    def quote(value: str) -> str:
        value = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"' + value + '"'
    return " ".join(quote(str(arg)) for arg in argv)


def linux_autostart_path(*, config_home: Optional[str] = None) -> Path:
    base = config_home or os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart" / LINUX_DESKTOP_FILE


def _set_windows(enabled: bool, argv: list[str], *, winreg_module=None) -> None:
    if winreg_module is None:
        import winreg as winreg_module  # type: ignore

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    access = getattr(winreg_module, "KEY_SET_VALUE", 0)
    with winreg_module.CreateKeyEx(winreg_module.HKEY_CURRENT_USER, key_path, 0, access) as key:
        if enabled:
            winreg_module.SetValueEx(
                key, APP_RUN_VALUE, 0, winreg_module.REG_SZ, _windows_command(argv))
        else:
            try:
                winreg_module.DeleteValue(key, APP_RUN_VALUE)
            except FileNotFoundError:
                pass


def _set_linux(enabled: bool, argv: list[str], *, config_home: Optional[str] = None) -> None:
    path = linux_autostart_path(config_home=config_home)
    if not enabled:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Accessible IPTV Client\n"
        f"Exec={_desktop_exec(argv)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def set_enabled(
    enabled: bool,
    *,
    platform_name: Optional[str] = None,
    argv: Optional[list[str]] = None,
    config_home: Optional[str] = None,
    winreg_module=None,
) -> None:
    """Enable or disable per-user startup without administrator privileges."""
    name = (platform_name or sys.platform).lower()
    command = list(argv or launch_argv())
    if name.startswith("win"):
        _set_windows(bool(enabled), command, winreg_module=winreg_module)
        return
    if name.startswith("linux"):
        _set_linux(bool(enabled), command, config_home=config_home)
        return
    raise OSError("automatic startup is not supported on this platform")
