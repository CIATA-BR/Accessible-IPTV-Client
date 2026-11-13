import copy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import wx

import accessible_tools_ui
import episode_continuation_ui
import named_bookmarks
import planning_ui
import recording_limits_ui
import session_tools_ui


@pytest.fixture
def owner():
    app = wx.GetApp() or wx.App(False)
    frame = wx.Frame(None)
    frame.config = {}
    frame.all_channels = []
    frame.recorder = SimpleNamespace(list_active=lambda: [])
    def save(key, operation):
        frame.config[key] = operation(copy.deepcopy(frame.config.get(key)))
    frame._save_tool_setting = save
    yield frame
    frame.Destroy()
    app.Yield()


def test_named_bookmark_dialog_uses_saved_positions_and_refuses_a_changed_player(owner, monkeypatch):
    key = 'a' * 64
    owner.config['named_playback_bookmarks'] = named_bookmarks.put({}, key, 'Próba', 20000)
    player = wx.Frame(owner)
    player._resume_key = key
    player._vlc_generation = 2
    player.player = SimpleNamespace(is_seekable=lambda: True)
    player._media_clock = lambda: (1000, 60000)
    dialog = session_tools_ui.BookmarksDialog(player)
    try:
        assert dialog.list.GetName() == 'Bookmarks for the current item:'
        assert dialog.list.GetString(0) == 'Próba — 00:00:20'
        messages = []
        monkeypatch.setattr(session_tools_ui, '_error', lambda parent, text: messages.append(text))
        player._vlc_generation = 3
        dialog.go(None)
        assert dialog.target is None and messages
        player._vlc_generation = 2
        result = []
        dialog.EndModal = result.append
        dialog.go(None)
        assert result == [wx.ID_OK] and dialog.target == 20000
    finally:
        dialog.Destroy()
        player.Destroy()


def test_notification_history_is_accessible_and_refreshes_without_mutating_it(owner):
    owner._notification_history = named_bookmarks.notification([], 'Felvétel', 'Elkészült.', now=1000)
    dialog = session_tools_ui.NotificationsDialog(owner)
    try:
        assert dialog.list.GetName() == 'Notifications from this session:'
        assert dialog.details.GetName() == 'Details'
        assert not dialog.details.IsEditable()
        assert dialog.details.GetValue() == 'Elkészült.'
        dialog.refresh()
        assert len(owner._notification_history) == 1
    finally:
        dialog.Destroy()


def test_failed_reminder_delivery_remains_eligible_for_retry(monkeypatch):
    row = {
        "id": "reminder-1",
        "start": 2_000_000_000,
        "end": 2_000_003_600,
        "lead": 5,
        "status": "ready",
        "title": "Programme",
        "channel": "Channel",
        "channel_key": "a" * 64,
    }

    class Store:
        def __init__(self):
            self.fail = True
            self.acknowledged = 0

        def due(self):
            return [dict(row)]

        def list(self):
            return [dict(row)]

        def acknowledge(self, key):
            self.acknowledged += 1
            assert key == row["id"]
            if self.fail:
                raise OSError("disk full")

    class Dialog:
        def SetYesNoLabels(self, *_args):
            pass

        def Destroy(self):
            pass

    store = Store()
    owner = SimpleNamespace(
        _reminders_stopped=False,
        _reminder_seen=set(),
        _reminder_errors_after=0,
        _reminder_error_reported=False,
        all_channels=[],
    )
    owner._ensure_reminders = lambda: store
    owner._modal_box_is_open = lambda: False
    owner._show_or_queue_message_box = lambda *_args, **_kwargs: None
    owner._play_live_channel = lambda _channel: None
    owner._reminder_modal_open = planning_ui.PlanningMixin._reminder_modal_open.__get__(owner)
    owner._poll_reminders = planning_ui.PlanningMixin._poll_reminders.__get__(owner)

    monkeypatch.setattr(planning_ui.wx, "GetTopLevelWindows", lambda: [])
    monkeypatch.setattr(planning_ui.wx, "MessageDialog", lambda *_args, **_kwargs: Dialog())
    monkeypatch.setattr(planning_ui, "show_modal", lambda _dialog: planning_ui.wx.ID_NO)

    owner._poll_reminders()
    assert row["id"] not in owner._reminder_seen
    assert store.acknowledged == 1

    store.fail = False
    owner._reminder_errors_after = 0
    owner._poll_reminders()
    assert row["id"] in owner._reminder_seen
    assert store.acknowledged == 2


def test_stale_natural_end_callback_cannot_use_the_new_episode():
    episode_continuation_ui.finished(SimpleNamespace(_vlc_generation=12, _destroyed=False), 11)
    episode_continuation_ui.finished(SimpleNamespace(_destroyed=True), 11)


def test_next_episode_waits_for_existing_modal(monkeypatch):
    state = {"open": True}
    owner = SimpleNamespace(_modal_box_is_open=lambda: state["open"])
    scheduled = []
    called = []
    monkeypatch.setattr(
        episode_continuation_ui.wx,
        "CallLater",
        lambda delay, callback, *args: scheduled.append((delay, callback, args)),
    )

    episode_continuation_ui._when_modal_clear(
        owner, lambda: True, lambda value: called.append(value), "episode"
    )

    assert called == []
    assert len(scheduled) == 1
    assert scheduled[0][0] == 250

    state["open"] = False
    _, callback, args = scheduled.pop()
    callback(*args)
    assert called == ["episode"]


def test_next_episode_modal_deferral_drops_stale_request(monkeypatch):
    owner = SimpleNamespace(_modal_box_is_open=lambda: True)
    scheduled = []
    monkeypatch.setattr(
        episode_continuation_ui.wx,
        "CallLater",
        lambda delay, callback, *args: scheduled.append((delay, callback, args)),
    )

    episode_continuation_ui._when_modal_clear(
        owner, lambda: False, lambda: pytest.fail("stale continuation ran")
    )

    assert scheduled == []


def test_next_episode_countdown_cancels_after_a_new_playback_request(owner):
    dialog = episode_continuation_ui.NextEpisodeDialog(owner, 'Episode', lambda: False)
    try:
        result = []
        dialog.IsModal = lambda: True
        dialog.EndModal = result.append
        dialog.tick(None)
        assert result == [wx.ID_CANCEL]
    finally:
        dialog.timer.Stop()
        dialog.Destroy()


def test_next_episode_modal_starts_on_cancel():
    # ShowModal dispatches process-wide events, including work queued by other
    # tests. Use one fresh wx.App so this native focus check neither drains the
    # suite's event queue nor inherits its windows, timers or wx.App lifetimes.
    # A child crash or hang must still fail this test, with captured diagnostics.
    probe = r'''
import wx
from episode_continuation_ui import NextEpisodeDialog

app = wx.App(False)
wx.Log.SetActiveTarget(wx.LogStderr())
owner = wx.Frame(None)
dialog = None
timer = None
observed = []
try:
    dialog = NextEpisodeDialog(owner, 'Episode', lambda: True)

    def inspect():
        try:
            focus = wx.Window.FindFocus()
            default = dialog.GetDefaultItem()
            observed.append((focus.GetId() if focus else None,
                             default.GetId() if default else None))
        finally:
            dialog.EndModal(wx.ID_CANCEL)

    timer = wx.CallLater(100, inspect)
    result = dialog.ShowModal()
    assert result == wx.ID_CANCEL, result
    assert observed == [(wx.ID_CANCEL, wx.ID_CANCEL)], observed
finally:
    if timer is not None:
        timer.Stop()
    if dialog is not None:
        dialog.timer.Stop()
        dialog.Destroy()
    owner.Destroy()
    app.Yield()
'''
    result = subprocess.run(
        [sys.executable, '-X', 'faulthandler', '-c', probe],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, errors='replace', timeout=30,
    )
    assert result.returncode == 0, (
        f'Native next-episode probe exited with {result.returncode}\n'
        f'{result.stdout}{result.stderr}'
    )


def test_recording_library_switches_between_restore_and_permanent_delete(owner, tmp_path, monkeypatch):
    monkeypatch.setattr(accessible_tools_ui.options, 'get_recordings_dir', lambda config: str(tmp_path))
    monkeypatch.setattr(accessible_tools_ui.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))
    dialog = accessible_tools_ui.RecordingLibraryDialog(owner)
    try:
        dialog.loaded([], '')
        dialog.deleted.SetValue(True)
        row = {'path': 'fixture', 'title': 'Deleted', 'channel': '', 'date': '', 'duration': None, 'status': 'unknown'}
        dialog.all_rows = [row]
        dialog.filter()
        assert dialog.restore.IsEnabled() and not dialog.play.IsEnabled()
        assert dialog.remove.GetLabel() == dialog.remove.GetName() == 'Delete Recording File...'
        dialog.deleted.SetValue(False)
        dialog.filter()
        assert dialog.play.IsEnabled() and not dialog.restore.IsEnabled()
        assert dialog.remove.GetLabel() == dialog.remove.GetName() == 'Move to Recording Trash...'
        assert not dialog.forget_folder.IsEnabled()
        dialog.closed = True
        dialog.operation_done(RuntimeError('late'))
    finally:
        dialog.Destroy()


def test_account_discovery_result_is_ignored_after_dialog_close(owner, monkeypatch):
    monkeypatch.setattr(recording_limits_ui.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))
    dialog = recording_limits_ui.RecordingLimitsDialog(owner)
    try:
        assert dialog.list.GetName() == 'Provider accounts'
        dialog.closed = True
        dialog.loaded([], 'late result')
        assert dialog.status.GetLabel() == 'Loading accounts...'
    finally:
        dialog.Destroy()
