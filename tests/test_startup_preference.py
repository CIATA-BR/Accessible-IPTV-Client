from types import SimpleNamespace

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
    )

    monkeypatch.setattr(main.platform, "system", lambda: "Windows")
    monkeypatch.setattr(main.startup, "set_enabled", lambda enabled: calls.append(bool(enabled)))
    monkeypatch.setattr(main, "save_config", lambda _config: True)

    main.IPTVClient.on_toggle_start_with_system(owner, _Event(True))

    assert calls == [True]
    assert owner.start_with_system is True
    assert owner.config["start_with_system"] is True
