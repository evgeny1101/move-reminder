import builtins
import importlib
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


def _install_tk_stubs(entry_value="45", raise_on_root=False, cancel=False):
    calls = {}
    entry_ref = [None]
    ok_command = [None]
    cancel_command = [None]

    class _Root:
        def withdraw(self):
            calls["withdrawn"] = True

        def destroy(self):
            calls["root_destroyed"] = True

    if raise_on_root:
        class _FailingRoot(_Root):
            def __init__(self):
                raise RuntimeError("tk init fail")

        tk_module = types.ModuleType("tkinter")
        tk_module.Tk = _FailingRoot
        sys.modules["tkinter"] = tk_module
        return calls, entry_ref

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

        def wait_window(self, w):
            calls["wait_window"] = True
            if cancel and cancel_command[0] is not None:
                cancel_command[0]()
            elif ok_command[0] is not None:
                ok_command[0]()

        def after(self, ms, func):
            func()

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
    tk_module.Toplevel = lambda parent: _TopLevel(parent)
    tk_module.Frame = _Frame
    tk_module.Label = _Label
    tk_module.Entry = _Entry
    tk_module.Button = _Button

    sys.modules["tkinter"] = tk_module
    return calls, entry_ref


_install_windows_stubs()
windows_app = importlib.import_module("windows_app")


def _build_app():
    app = windows_app.MoveReminderWindowsApp.__new__(windows_app.MoveReminderWindowsApp)
    app._state_lock = threading.Lock()
    app._dialog_lock = threading.Lock()
    app.selected_minutes = 45
    app._icon = types.SimpleNamespace(update_menu=lambda: None)
    return app


def test_edit_minutes_updates_value_and_menu(monkeypatch):
    app = _build_app()
    update_calls = []
    monkeypatch.setattr(app, "_safe_update_menu", lambda: update_calls.append(True))
    monkeypatch.setattr(app, "_ask_minutes_with_tk_dialog", lambda _initial: 30)

    app._on_edit_minutes_clicked()

    assert app.selected_minutes == 30
    assert update_calls == [True]


def test_edit_minutes_cancel_keeps_value(monkeypatch):
    app = _build_app()
    app.selected_minutes = 50
    update_calls = []
    monkeypatch.setattr(app, "_safe_update_menu", lambda: update_calls.append(True))
    monkeypatch.setattr(app, "_ask_minutes_with_tk_dialog", lambda _initial: None)

    app._on_edit_minutes_clicked()

    assert app.selected_minutes == 50
    assert update_calls == []


def test_tk_dialog_returns_value_and_closes_root():
    app = _build_app()
    calls, entry_ref = _install_tk_stubs(entry_value="60")

    result = app._ask_minutes_with_tk_dialog(45)

    assert result == 60
    assert entry_ref[0] is not None
    assert calls["withdrawn"] is True
    assert calls["topmost"] is True
    assert calls["lifted"] is True
    assert calls["top_focused"] is True
    assert calls["entry_focused"] is True
    assert calls["entry_selected"] is True
    assert calls["grab_set"] is True
    assert calls["wait_window"] is True
    assert calls["top_destroyed"] is True
    assert calls["root_destroyed"] is True


def test_tk_dialog_sets_initial_value_in_entry():
    app = _build_app()
    _calls, entry_ref = _install_tk_stubs(entry_value="45")

    app._ask_minutes_with_tk_dialog(33)

    assert entry_ref[0] is not None
    assert entry_ref[0]._value == "33"


def test_tk_dialog_binds_return_and_escape():
    app = _build_app()
    calls, _entry_ref = _install_tk_stubs()

    app._ask_minutes_with_tk_dialog(45)

    assert calls["bind_<Return>"] is not None
    assert calls["bind_<Escape>"] is not None
    assert calls["close_handler"] is not None


def test_tk_dialog_returns_none_on_exception(capsys):
    app = _build_app()
    calls, _entry_ref = _install_tk_stubs(raise_on_root=True)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None
    assert "failed to open minutes dialog" in capsys.readouterr().err


def test_tk_dialog_cancel_returns_none():
    app = _build_app()
    calls, _entry_ref = _install_tk_stubs(cancel=True)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None
    assert calls["top_destroyed"] is True
    assert calls["root_destroyed"] is True


def test_tk_dialog_guard_prevents_concurrent_open():
    app = _build_app()
    app._dialog_lock.acquire()
    try:
        result = app._ask_minutes_with_tk_dialog(45)
    finally:
        app._dialog_lock.release()

    assert result is None


def test_tk_dialog_tkinter_missing(monkeypatch, capsys):
    app = _build_app()
    sys.modules.pop("tkinter", None)
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tkinter":
            raise ImportError("tk unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None
    assert "tkinter is not available" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("entry_value", "expected"),
    [
        ("0", 1),
        ("1000", 600),
        ("30", 30),
    ],
)
def test_tk_dialog_clamps_input(entry_value, expected):
    app = _build_app()
    _calls, _entry_ref = _install_tk_stubs(entry_value=entry_value)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result == expected


def test_tk_dialog_non_numeric_input_returns_none():
    app = _build_app()
    _calls, _entry_ref = _install_tk_stubs(entry_value="abc")

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None