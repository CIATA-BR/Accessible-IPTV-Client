import os

import startup


class _Key:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.created = []

    def CreateKeyEx(self, root, path, reserved, access):
        self.created.append((root, path, reserved, access))
        return _Key()

    def SetValueEx(self, _key, name, reserved, kind, value):
        self.values[name] = (reserved, kind, value)

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_launch_argv_uses_only_frozen_executable(tmp_path):
    exe = tmp_path / "Accessible IPTV Client.exe"
    assert startup.launch_argv(executable=str(exe), argv0="ignored.py", frozen=True) == [
        os.path.abspath(exe)
    ]


def test_launch_argv_keeps_python_and_script_for_source(tmp_path):
    exe = tmp_path / "python.exe"
    script = tmp_path / "main.py"
    assert startup.launch_argv(executable=str(exe), argv0=str(script), frozen=False) == [
        os.path.abspath(exe), os.path.abspath(script)
    ]


def test_linux_autostart_writes_and_removes_desktop_entry(tmp_path):
    argv = ["/opt/Accessible IPTV/python", "/opt/Accessible IPTV/main.py"]
    startup.set_enabled(True, platform_name="linux", argv=argv, config_home=str(tmp_path))

    path = tmp_path / "autostart" / startup.LINUX_DESKTOP_FILE
    text = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text
    assert 'Exec="/opt/Accessible IPTV/python" "/opt/Accessible IPTV/main.py"' in text
    assert "Terminal=false" in text

    startup.set_enabled(False, platform_name="linux", argv=argv, config_home=str(tmp_path))
    assert not path.exists()


def test_linux_autostart_escapes_percent_field_codes(tmp_path):
    argv = ["/opt/Accessible%20IPTV/iptv"]
    startup.set_enabled(True, platform_name="linux", argv=argv, config_home=str(tmp_path))

    path = tmp_path / "autostart" / startup.LINUX_DESKTOP_FILE
    text = path.read_text(encoding="utf-8")
    assert 'Exec="/opt/Accessible%%20IPTV/iptv"' in text


def test_windows_autostart_uses_current_user_run_key():
    registry = _FakeWinreg()
    argv = [r"C:\Program Files\Accessible IPTV Client\iptv.exe"]

    startup.set_enabled(True, platform_name="win32", argv=argv, winreg_module=registry)

    assert registry.created
    assert registry.created[0][0] is registry.HKEY_CURRENT_USER
    assert registry.created[0][1] == r"Software\Microsoft\Windows\CurrentVersion\Run"
    saved = registry.values[startup.APP_RUN_VALUE][2]
    assert "Accessible IPTV Client" in saved

    startup.set_enabled(False, platform_name="win32", argv=argv, winreg_module=registry)
    assert startup.APP_RUN_VALUE not in registry.values


def test_unsupported_platform_is_rejected():
    try:
        startup.set_enabled(True, platform_name="darwin", argv=["app"])
    except OSError as error:
        assert "not supported" in str(error)
    else:
        raise AssertionError("unsupported platform must fail")
