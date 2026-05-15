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


def _install_tk_stubs(value=None, raise_on_ask=False):
    calls = {
        "destroyed": False,
        "withdrawn": False,
        "topmost": False,
        "lifted": False,
        "focused": False,
        "updated": False,
    }
    ask_calls = []

    class _Root:
        def withdraw(self):
            calls["withdrawn"] = True

        def attributes(self, key, enabled):
            if key == "-topmost" and enabled is True:
                calls["topmost"] = True

        def destroy(self):
            calls["destroyed"] = True

        def lift(self):
            calls["lifted"] = True

        def focus_force(self):
            calls["focused"] = True

        def update(self):
            calls["updated"] = True

    tk_module = types.ModuleType("tkinter")
    tk_module.Tk = lambda: _Root()

    def _askinteger(*_args, **_kwargs):
        ask_calls.append(_kwargs)
        if raise_on_ask:
            raise RuntimeError("dialog fail")
        return value

    simpledialog_module = types.ModuleType("tkinter.simpledialog")
    simpledialog_module.askinteger = _askinteger
    tk_module.simpledialog = simpledialog_module

    sys.modules["tkinter"] = tk_module
    sys.modules["tkinter.simpledialog"] = simpledialog_module
    return calls, ask_calls


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
    calls, ask_calls = _install_tk_stubs(value=60)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result == 60
    assert ask_calls[0]["initialvalue"] == 45
    assert ask_calls[0]["minvalue"] == 1
    assert ask_calls[0]["maxvalue"] == 600
    assert ask_calls[0]["parent"] is not None
    assert calls["withdrawn"] is True
    assert calls["topmost"] is True
    assert calls["lifted"] is True
    assert calls["focused"] is True
    assert calls["updated"] is True
    assert calls["destroyed"] is True


def test_tk_dialog_returns_none_on_exception(capsys):
    app = _build_app()
    calls, _ask_calls = _install_tk_stubs(raise_on_ask=True)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None
    assert calls["destroyed"] is True
    assert "failed to open minutes dialog" in capsys.readouterr().err


def test_tk_dialog_cancel_returns_none():
    app = _build_app()
    calls, _ask_calls = _install_tk_stubs()

    result = app._ask_minutes_with_tk_dialog(45)

    assert result is None
    assert calls["destroyed"] is True


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
    ("dialog_value", "expected"),
    [
        (0, 1),
        (1000, 600),
        (30, 30),
    ],
)
def test_tk_dialog_clamps_input(dialog_value, expected):
    app = _build_app()
    _calls, _ask_calls = _install_tk_stubs(value=dialog_value)

    result = app._ask_minutes_with_tk_dialog(45)

    assert result == expected
