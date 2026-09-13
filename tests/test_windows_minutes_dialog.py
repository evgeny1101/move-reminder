import builtins
import importlib
import pathlib
import queue
import sys
import threading
import types

import pytest


def _install_windows_stubs() -> None:
    class _DummyIcon:
        def __init__(self, *_args, **_kwargs):
            self.menu = None

        def update_menu(self):
            return None

        def stop(self):
            return None

    pystray = types.SimpleNamespace(
        Icon=_DummyIcon,
        Menu=lambda *items: items,
        MenuItem=lambda *args, **kwargs: (args, kwargs),
    )
    pystray.Menu.SEPARATOR = object()

    image_module = types.SimpleNamespace(new=lambda *_args, **_kwargs: object())
    draw_module = types.SimpleNamespace(
        Draw=lambda *_args, **_kwargs: types.SimpleNamespace(
            ellipse=lambda *_a, **_k: None,
            rectangle=lambda *_a, **_k: None,
        )
    )

    pil_module = types.ModuleType("PIL")
    pil_module.Image = image_module
    pil_module.ImageDraw = draw_module

    sys.modules["pystray"] = pystray
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module
    sys.modules["PIL.ImageDraw"] = draw_module


def _install_tk_stubs(entry_value="45"):
    calls = {}
    entry_ref = [None]
    ok_command = [None]
    cancel_command = [None]

    class _Root:
        def withdraw(self):
            calls["withdrawn"] = True

        def destroy(self):
            calls["root_destroyed"] = True

    class _TopLevel:
        def __init__(self, parent):
            calls["top_created"] = True

        def title(self, t):
            calls["title"] = t

        def resizable(self, a, b):
            pass

        def attributes(self, *args):
            calls["topmost"] = True

        def protocol(self, name, handler):
            calls["close_handler"] = handler

        def pack(self, **kwargs):
            pass

        def grab_set(self):
            calls["grab_set"] = True

        def after(self, ms, func):
            func()

        def update_idletasks(self):
            calls["updated_idletasks"] = True

        def focus_force(self):
            calls["top_focused"] = True

        def lift(self):
            calls["lifted"] = True

        def destroy(self):
            calls["top_destroyed"] = True

    class _Frame:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, **kwargs):
            pass

    class _Label:
        def __init__(self, *args, **kwargs):
            pass

        def pack(self, **kwargs):
            pass

    class _Entry:
        def __init__(self, parent, **kwargs):
            self._value = ""
            self._focused = False
            entry_ref[0] = self

        def insert(self, pos, text):
            self._value = text

        def get(self):
            return entry_value

        def select_range(self, start, end):
            calls["entry_selected"] = True

        def pack(self, **kwargs):
            pass

        def bind(self, sequence, func):
            calls[f"bind_{sequence}"] = func

        def focus_set(self):
            self._focused = True
            calls["entry_focused"] = True

    class _Button:
        def __init__(self, parent, text="", command=None, **kwargs):
            if text == "OK":
                ok_command[0] = command
            elif text == "Отмена":
                cancel_command[0] = command

        def pack(self, **kwargs):
            pass

    tk_module = types.ModuleType("tkinter")
    tk_module.Tk = _Root
    tk_module.Toplevel = _TopLevel
    tk_module.Frame = _Frame
    tk_module.Label = _Label
    tk_module.Entry = _Entry
    tk_module.Button = _Button

    sys.modules["tkinter"] = tk_module
    return calls, entry_ref, ok_command, cancel_command


_install_windows_stubs()
windows_app = importlib.import_module("windows_app")


def _build_app():
    app = windows_app.MoveReminderWindowsApp.__new__(windows_app.MoveReminderWindowsApp)
    app._state_lock = threading.Lock()
    app._dialog_lock = threading.Lock()
    app.selected_minutes = 45
    app.timer_seconds_left = 0
    app._stop_event = threading.Event()
    app._commands = queue.Queue()
    app._tk_root = None
    app._icon = types.SimpleNamespace(update_menu=lambda: None, stop=lambda: None)
    return app


def test_edit_minutes_queues_command_only():
    app = _build_app()
    app.selected_minutes = 33

    app._on_edit_minutes_clicked()

    assert app._commands.get_nowait() == ("edit_minutes", 33)
    assert app.selected_minutes == 33


def test_poll_commands_dispatches_edit_minutes(monkeypatch):
    app = _build_app()
    rescheduled = []
    app._tk_root = types.SimpleNamespace(after=lambda ms, func: rescheduled.append(ms))
    opened = []
    monkeypatch.setattr(
        app, "_open_minutes_dialog", lambda minutes: opened.append(minutes)
    )
    app._commands.put(("edit_minutes", 25))

    app._poll_commands()

    assert opened == [25]
    assert rescheduled == [app.TRAY_POLL_MS]


def test_poll_commands_shuts_down():
    app = _build_app()
    destroyed = []
    app._tk_root = types.SimpleNamespace(
        after=lambda *args: None, destroy=lambda: destroyed.append(True)
    )
    app._commands.put(None)

    app._poll_commands()

    assert destroyed == [True]


def test_poll_commands_is_noop_without_root():
    app = _build_app()
    app._commands.put(("edit_minutes", 30))

    app._poll_commands()

    assert app._commands.get_nowait() == ("edit_minutes", 30)


def test_open_dialog_uses_topmost_and_activates_entry():
    app = _build_app()
    app._tk_root = object()
    calls, _entry_ref, _ok, _cancel = _install_tk_stubs()

    app._open_minutes_dialog(45)

    assert calls["top_created"] is True
    assert calls["topmost"] is True
    assert calls["updated_idletasks"] is True
    assert calls["lifted"] is True
    assert calls["top_focused"] is True
    assert calls["entry_focused"] is True
    assert calls["entry_selected"] is True
    assert calls["grab_set"] is True


def test_open_dialog_sets_initial_value_in_entry():
    app = _build_app()
    app._tk_root = object()
    _calls, entry_ref, _ok, _cancel = _install_tk_stubs()

    app._open_minutes_dialog(33)

    assert entry_ref[0] is not None
    assert entry_ref[0]._value == "33"


def test_open_dialog_ok_updates_value_and_menu(monkeypatch):
    app = _build_app()
    app._tk_root = object()
    calls, _ref, ok, _cancel = _install_tk_stubs(entry_value="60")
    menu_calls = []
    monkeypatch.setattr(app, "_safe_update_menu", lambda: menu_calls.append(True))

    app._open_minutes_dialog(45)
    ok[0]()

    assert app.selected_minutes == 60
    assert menu_calls == [True]
    assert calls["top_destroyed"] is True
    assert app._dialog_lock.acquire(blocking=False) is True
    app._dialog_lock.release()


def test_open_dialog_cancel_keeps_value(monkeypatch):
    app = _build_app()
    app._tk_root = object()
    calls, _ref, _ok, cancel = _install_tk_stubs()
    app.selected_minutes = 50
    menu_calls = []
    monkeypatch.setattr(app, "_safe_update_menu", lambda: menu_calls.append(True))

    app._open_minutes_dialog(50)
    cancel[0]()

    assert app.selected_minutes == 50
    assert menu_calls == []
    assert calls["top_destroyed"] is True


def test_open_dialog_binds_return_escape_and_close():
    app = _build_app()
    app._tk_root = object()
    calls, _ref, _ok, _cancel = _install_tk_stubs()

    app._open_minutes_dialog(45)

    assert calls["bind_<Return>"] is not None
    assert calls["bind_<Escape>"] is not None
    assert calls["close_handler"] is not None


@pytest.mark.parametrize(
    ("entry_value", "expected"),
    [
        ("0", 1),
        ("1000", 600),
        ("30", 30),
    ],
)
def test_open_dialog_clamps_input(entry_value, expected):
    app = _build_app()
    app._tk_root = object()
    _calls, _ref, ok, _cancel = _install_tk_stubs(entry_value=entry_value)

    app._open_minutes_dialog(45)
    ok[0]()

    assert app.selected_minutes == expected


def test_open_dialog_non_numeric_keeps_value(monkeypatch):
    app = _build_app()
    app._tk_root = object()
    _calls, _ref, ok, _cancel = _install_tk_stubs(entry_value="abc")
    menu_calls = []
    monkeypatch.setattr(app, "_safe_update_menu", lambda: menu_calls.append(True))

    app._open_minutes_dialog(45)
    ok[0]()

    assert app.selected_minutes == 45
    assert menu_calls == []


def test_open_dialog_guard_prevents_concurrent_open():
    app = _build_app()
    app._tk_root = object()
    calls, _ref, _ok, _cancel = _install_tk_stubs()
    app._dialog_lock.acquire()
    try:
        app._open_minutes_dialog(45)
    finally:
        app._dialog_lock.release()

    assert "top_created" not in calls


def test_open_dialog_returns_if_root_missing():
    app = _build_app()
    calls, _ref, _ok, _cancel = _install_tk_stubs()

    app._open_minutes_dialog(45)

    assert "top_created" not in calls
    assert app._dialog_lock.acquire(blocking=False) is True
    app._dialog_lock.release()


def test_open_dialog_tk_import_error_releases_lock(monkeypatch, capsys):
    app = _build_app()
    app._tk_root = object()
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tkinter":
            raise ImportError("tk unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    app._open_minutes_dialog(45)

    assert "failed to open minutes dialog" in capsys.readouterr().err
    assert app._dialog_lock.acquire(blocking=False) is True
    app._dialog_lock.release()


def test_tk_main_handles_missing_tkinter(monkeypatch, capsys):
    app = _build_app()
    ready = threading.Event()
    app._tk_ready = ready
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tkinter":
            raise ImportError("tk unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    app._tk_main()

    assert ready.is_set()
    assert app._tk_root is None
    assert "tkinter is not available" in capsys.readouterr().err


def test_tk_main_starts_root_event_loop(monkeypatch):
    app = _build_app()
    ready = threading.Event()
    app._tk_ready = ready
    calls = []

    class _RootStub:
        def withdraw(self):
            calls.append("withdraw")

        def after(self, ms, func):
            calls.append(("after", ms))

        def mainloop(self):
            calls.append("mainloop")

    tk_module = types.ModuleType("tkinter")
    tk_module.Tk = _RootStub
    monkeypatch.setitem(sys.modules, "tkinter", tk_module)

    app._tk_main()

    assert ready.is_set()
    assert app._tk_root is not None
    assert calls == ["withdraw", ("after", app.TRAY_POLL_MS), "mainloop"]


def test_run_starts_thread_runs_icon_and_shuts_down():
    app = _build_app()
    app._tk_ready = threading.Event()
    app._tk_ready.set()
    started = []
    joined = []
    app._tk_thread = types.SimpleNamespace(
        start=lambda: started.append(True),
        join=lambda **kwargs: joined.append(True),
    )
    icon_ran = []
    app._icon = types.SimpleNamespace(run=lambda: icon_ran.append(True))

    app.run()

    assert started == [True]
    assert icon_ran == [True]
    assert joined == [True]
    assert app._commands.get_nowait() is None


def test_on_quit_stops_icon_and_timer(monkeypatch):
    app = _build_app()
    stopped = []
    monkeypatch.setattr(app._icon, "stop", lambda: stopped.append(True))

    app.start_timer(2)
    app._on_quit()

    assert stopped == [True]
    assert app.timer_seconds_left == 0
    assert app._stop_event.is_set()


def test_find_powershell_returns_which_path(monkeypatch):
    fake = pathlib.Path("/tmp/powershell.exe")
    monkeypatch.setattr(windows_app.shutil, "which", lambda *_a, **_k: str(fake))

    assert windows_app._find_powershell() == fake


def test_find_powershell_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr(windows_app.shutil, "which", lambda *_a, **_k: None)

    assert windows_app._find_powershell() is None


def test_send_windows_toast_false_without_powershell(monkeypatch):
    monkeypatch.setattr(windows_app, "_find_powershell", lambda: None)

    assert windows_app._send_windows_toast("title", "message") is False


def test_send_windows_toast_invokes_powershell(monkeypatch):
    fake = pathlib.Path("/usr/bin/powershell.exe")
    monkeypatch.setattr(windows_app, "_find_powershell", lambda: fake)
    runs = []

    def fake_run(argv, **kwargs):
        runs.append((argv, kwargs))
        return None

    monkeypatch.setattr(windows_app.subprocess, "run", fake_run)

    assert windows_app._send_windows_toast("Пора подвигаться", "Таймер завершен.") is True

    argv, kwargs = runs[0]
    assert argv[0] == str(fake)
    assert "-NoProfile" in argv
    assert "-NonInteractive" in argv
    assert "-WindowStyle" in argv
    assert argv[argv.index("-Command") + 1] == windows_app._POWERTOAST_PS
    assert kwargs["env"][windows_app._NOTIFY_TITLE_ENV] == "Пора подвигаться"
    assert kwargs["env"][windows_app._NOTIFY_MESSAGE_ENV] == "Таймер завершен."


def test_send_windows_toast_swallows_subprocess_error(monkeypatch, capsys):
    fake = pathlib.Path("/usr/bin/powershell.exe")
    monkeypatch.setattr(windows_app, "_find_powershell", lambda: fake)

    def fake_run(argv, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(windows_app.subprocess, "run", fake_run)

    assert windows_app._send_windows_toast("title", "message") is False
    assert "failed to show notification" in capsys.readouterr().err


def test_powertoast_script_uses_both_aumids():
    script = windows_app._POWERTOAST_PS
    assert "MoveReminder.App" in script
    assert (
        "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
        "\\WindowsPowerShell\\v1.0\\powershell.exe" in script
    )


def test_deliver_notification_falls_back_to_icon(monkeypatch):
    app = _build_app()
    notified = []
    app._icon = types.SimpleNamespace(
        notify=lambda title, message: notified.append((title, message))
    )
    monkeypatch.setattr(windows_app, "_send_windows_toast", lambda *_a, **_k: False)

    app._deliver_notification()

    assert notified == [(windows_app._REMINDER_TITLE, windows_app._REMINDER_MESSAGE)]


def test_deliver_notification_skips_icon_on_success(monkeypatch):
    app = _build_app()
    called = []
    app._icon = types.SimpleNamespace(
        notify=lambda title, message: called.append(True)
    )
    monkeypatch.setattr(windows_app, "_send_windows_toast", lambda *_a, **_k: True)

    app._deliver_notification()

    assert called == []


def test_notify_done_runs_delivery_in_background_thread(monkeypatch):
    app = _build_app()
    app._icon = types.SimpleNamespace(
        notify=lambda title, message: None
    )
    targets = []
    monkeypatch.setattr(windows_app, "_send_windows_toast", lambda *_a, **_k: True)

    class FakeThread:
        def __init__(self, target=None, **_kwargs):
            targets.append(target)

        def start(self):
            for target in targets:
                target()

    monkeypatch.setattr(windows_app.threading, "Thread", FakeThread)

    app._notify_done()

    assert len(targets) == 1
    assert targets[0] is not None
    targets[0]()