from types import SimpleNamespace
import threading

import main


class _Item:
    def __init__(self):
        self.checked = None

    def Check(self, value):
        self.checked = bool(value)


class _Event:
    def __init__(self, checked):
        self.checked = checked

    def IsChecked(self):
        return self.checked


def test_autostart_rolls_back_when_config_save_fails(monkeypatch):
    calls = []
    messages = []
    owner = SimpleNamespace(
        start_with_system=False,
        config={"start_with_system": False},
        start_with_system_item=_Item(),
        _startup_registration_lock=threading.Lock(),
    )

    monkeypatch.setattr(main.platform, "system", lambda: "Windows")
    monkeypatch.setattr(main.startup, "set_enabled", lambda enabled: calls.append(bool(enabled)))
    monkeypatch.setattr(main, "save_config", lambda _config: False)
    monkeypatch.setattr(main, "message_box", lambda *args, **kwargs: messages.append(args))

    main.IPTVClient.on_toggle_start_with_system(owner, _Event(True))

    assert calls == [True, False]
    assert owner.start_with_system is False
    assert owner.config["start_with_system"] is False
    assert owner.start_with_system_item.checked is False
    assert messages


def test_autostart_commits_after_config_save_succeeds(monkeypatch):
    calls = []
    owner = SimpleNamespace(
        start_with_system=False,
        config={"start_with_system": False},
        start_with_system_item=_Item(),
        _startup_registration_lock=threading.Lock(),
    )

    monkeypatch.setattr(main.platform, "system", lambda: "Windows")
    monkeypatch.setattr(main.startup, "set_enabled", lambda enabled: calls.append(bool(enabled)))
    monkeypatch.setattr(main, "save_config", lambda _config: True)

    main.IPTVClient.on_toggle_start_with_system(owner, _Event(True))

    assert calls == [True]
    assert owner.start_with_system is True
    assert owner.config["start_with_system"] is True


def test_deferred_startup_sync_does_not_reenable_after_preference_changed(monkeypatch):
    calls = []
    owner = SimpleNamespace(
        start_with_system=True,
        _startup_registration_lock=threading.Lock(),
    )
    monkeypatch.setattr(main.startup, "set_enabled", lambda enabled: calls.append(bool(enabled)))

    owner._startup_registration_lock.acquire()
    worker = threading.Thread(target=main.IPTVClient._sync_startup_registration, args=(owner,))
    worker.start()
    owner.start_with_system = False
    owner._startup_registration_lock.release()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert calls == []
