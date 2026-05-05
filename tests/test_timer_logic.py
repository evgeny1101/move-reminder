import importlib
import sys
import types


def _install_gi_stubs() -> None:
    gi = types.ModuleType("gi")
    repository = types.ModuleType("repository")

    class _DummyIndicator:
        @staticmethod
        def new(*_args, **_kwargs):
            return object()

    app_indicator = types.SimpleNamespace(
        Indicator=_DummyIndicator,
        IndicatorCategory=types.SimpleNamespace(APPLICATION_STATUS=1),
        IndicatorStatus=types.SimpleNamespace(ACTIVE=1),
    )

    repository.GLib = types.SimpleNamespace(timeout_add_seconds=lambda *_args, **_kwargs: 1)
    repository.Gtk = types.SimpleNamespace(Widget=object)
    repository.Notify = types.SimpleNamespace(
        Notification=types.SimpleNamespace(new=lambda *_args, **_kwargs: object()),
        Urgency=types.SimpleNamespace(NORMAL=1),
    )
    repository.AyatanaAppIndicator3 = app_indicator
    repository.AppIndicator3 = app_indicator

    gi.require_version = lambda *_args, **_kwargs: None
    gi.repository = repository

    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


_install_gi_stubs()
timer_tray = importlib.import_module("timer_tray")


class _MenuItem:
    def __init__(self):
        self.label = ""
        self.sensitive = None

    def set_label(self, value):
        self.label = value

    def set_sensitive(self, value):
        self.sensitive = value


class _Indicator:
    def __init__(self):
        self.icon_name = ""

    def set_icon_full(self, icon_name, _description):
        self.icon_name = icon_name


def _build_app():
    app = timer_tray.MoveReminderApp.__new__(timer_tray.MoveReminderApp)
    app.timer_seconds_left = 0
    app.timer_source_id = None
    app.selected_minutes = 45
    app.status_item = _MenuItem()
    app.start_item = _MenuItem()
    app.stop_item = _MenuItem()
    app.indicator = _Indicator()
    return app


def test_start_timer_clamps_lower_bound(monkeypatch):
    app = _build_app()

    timeout_calls = []

    def fake_timeout_add_seconds(interval, callback):
        timeout_calls.append((interval, callback))
        return 99

    monkeypatch.setattr(timer_tray.GLib, "timeout_add_seconds", fake_timeout_add_seconds)
    monkeypatch.setattr(timer_tray.MoveReminderApp, "stop_timer", lambda self: None)

    app.start_timer(0)

    assert app.timer_seconds_left == 60
    assert app.timer_source_id == 99
    assert timeout_calls and timeout_calls[0][0] == 1


def test_start_timer_clamps_upper_bound(monkeypatch):
    app = _build_app()

    monkeypatch.setattr(timer_tray.GLib, "timeout_add_seconds", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(timer_tray.MoveReminderApp, "stop_timer", lambda self: None)

    app.start_timer(10000)

    assert app.timer_seconds_left == 600 * 60
    assert app.timer_source_id == 7


def test_tick_ongoing_timer_updates_time():
    app = _build_app()
    app.timer_seconds_left = 5
    app.timer_source_id = 111

    notified = {"value": False}
    sounded = {"value": False}

    app._notify_done = lambda: notified.__setitem__("value", True)
    app._play_sound = lambda: sounded.__setitem__("value", True)

    keep_running = app._tick()

    assert keep_running is True
    assert app.timer_seconds_left == 4
    assert app.timer_source_id == 111
    assert notified["value"] is False
    assert sounded["value"] is False


def test_tick_at_zero_stops_and_notifies():
    app = _build_app()
    app.timer_seconds_left = 1
    app.timer_source_id = 222

    calls = []
    app._notify_done = lambda: calls.append("notify")
    app._play_sound = lambda: calls.append("sound")

    keep_running = app._tick()

    assert keep_running is False
    assert app.timer_seconds_left == 0
    assert app.timer_source_id is None
    assert calls == ["notify", "sound"]


def test_play_sound_stops_on_first_success(monkeypatch):
    app = _build_app()
    app.APP_NAME = "Move Reminder"

    commands = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            commands.append(command)

        def wait(self, timeout):
            assert timeout == 0.25
            return 0

    monkeypatch.setattr(timer_tray.subprocess, "Popen", FakeProcess)

    app._play_sound()

    assert len(commands) == 1
    assert commands[0][0] == "canberra-gtk-play"


def test_play_sound_tries_next_on_failures(monkeypatch):
    app = _build_app()
    app.APP_NAME = "Move Reminder"

    commands = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            commands.append(command)

        def wait(self, timeout):
            assert timeout == 0.25
            if commands[-1][0] == "paplay":
                return 0
            return 1

    monkeypatch.setattr(timer_tray.subprocess, "Popen", FakeProcess)

    app._play_sound()

    assert len(commands) == 2
    assert commands[0][0] == "canberra-gtk-play"
    assert commands[1][0] == "paplay"
