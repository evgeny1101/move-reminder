import atexit
import os
import pathlib
import queue
import sys
import threading
import time
from typing import Optional

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "Windows mode requires pystray and Pillow. Install: pip install pystray pillow"
    ) from exc


def _activate_dialog(top, entry) -> None:
    """Gives keyboard focus to the entry of a tkinter dialog.

    The dialog is created and shown from the persistent Tk thread event loop,
    so plain Tk calls (lift + focus_force) are sufficient on Windows 10/11.
    """
    try:
        top.update_idletasks()
    except Exception:
        pass
    try:
        top.lift()
    except Exception:
        pass
    try:
        top.focus_force()
    except Exception:
        pass
    try:
        entry.focus_set()
    except Exception:
        pass
    try:
        entry.select_range(0, "end")
    except Exception:
        pass


class MoveReminderWindowsApp:
    APP_NAME = "Move Reminder"
    TRAY_POLL_MS = 100

    def __init__(self) -> None:
        self._single_instance_lock = self._acquire_single_instance_lock()
        self._state_lock = threading.Lock()
        self._dialog_lock = threading.Lock()
        self.timer_seconds_left = 0
        self.selected_minutes = 45
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._commands: "queue.Queue" = queue.Queue()
        self._tk_root = None
        self._tk_ready = threading.Event()
        self._tk_thread = threading.Thread(target=self._tk_main, daemon=True)
        self._icon = pystray.Icon("move-reminder", self._create_icon(), self.APP_NAME)
        self._icon.menu = self._build_menu()

    def _acquire_single_instance_lock(self):
        import msvcrt

        lock_root = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home()))
        lock_dir = lock_root / "move-reminder"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "move-reminder.lock"
        lock_file = open(lock_path, "a+", encoding="utf-8")
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock_file.close()
            raise SystemExit(0)
        lock_file.write(str(os.getpid()))
        lock_file.truncate()
        lock_file.flush()
        atexit.register(lock_file.close)
        atexit.register(lambda: lock_path.exists() and lock_path.unlink())
        return lock_file

    def _create_icon(self):
        image = Image.new("RGB", (64, 64), (30, 144, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 12, 52, 52), fill=(255, 255, 255))
        draw.rectangle((30, 20, 34, 34), fill=(30, 144, 255))
        draw.rectangle((34, 30, 44, 34), fill=(30, 144, 255))
        return image

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _: self._status_label(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: f"Минуты: {self.selected_minutes}",
                self._on_edit_minutes_clicked,
            ),
            pystray.MenuItem(
                "Старт",
                self._on_start_clicked,
                enabled=lambda _: self.timer_seconds_left == 0,
            ),
            pystray.MenuItem(
                "Стоп",
                self._on_stop_clicked,
                enabled=lambda _: self.timer_seconds_left > 0,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("25 минут", lambda _icon, _item: self._on_preset_clicked(25)),
            pystray.MenuItem("45 минут", lambda _icon, _item: self._on_preset_clicked(45)),
            pystray.MenuItem("60 минут", lambda _icon, _item: self._on_preset_clicked(60)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._on_quit),
        )

    def _status_label(self) -> str:
        with self._state_lock:
            seconds_left = self.timer_seconds_left

        if seconds_left > 0:
            mm = seconds_left // 60
            ss = seconds_left % 60
            return f"Осталось: {mm:02d}:{ss:02d}"
        return "Осталось: --:--"

    def _safe_update_menu(self) -> None:
        try:
            self._icon.update_menu()
        except Exception:
            pass

    def _on_start_clicked(self, _icon=None, _item=None) -> None:
        with self._state_lock:
            minutes = self.selected_minutes
        self.start_timer(minutes)

    def _on_stop_clicked(self, _icon=None, _item=None) -> None:
        self.stop_timer()

    def _on_preset_clicked(self, minutes: int) -> None:
        with self._state_lock:
            self.selected_minutes = minutes
        self.start_timer(minutes)

    def _on_edit_minutes_clicked(self, _icon=None, _item=None) -> None:
        with self._state_lock:
            initial_minutes = self.selected_minutes
        self._commands.put(("edit_minutes", initial_minutes))

    def _open_minutes_dialog(self, initial_minutes: int) -> None:
        if not self._dialog_lock.acquire(blocking=False):
            return

        handed_off = False
        top = None
        try:
            if self._tk_root is None:
                return

            import tkinter as tk

            top = tk.Toplevel(self._tk_root)
            top.title("Изменить минуты")
            top.resizable(False, False)
            top.attributes("-topmost", True)

            frame = tk.Frame(top, padx=12, pady=12)
            frame.pack(fill="both", expand=True)

            label = tk.Label(frame, text="Минуты:")
            label.pack(anchor="w")

            entry = tk.Entry(frame, width=10)
            entry.insert(0, str(initial_minutes))
            entry.pack(fill="x", pady=(4, 8))

            btn_frame = tk.Frame(frame)
            btn_frame.pack(fill="x")

            def _finish(value: Optional[int]) -> None:
                try:
                    top.destroy()
                except Exception:
                    pass
                if value is not None:
                    with self._state_lock:
                        self.selected_minutes = value
                    self._safe_update_menu()
                self._dialog_lock.release()

            def _on_submit():
                try:
                    val = int(entry.get().strip())
                except (ValueError, TypeError):
                    val = None
                _finish(max(1, min(val, 600)) if val is not None else None)

            def _on_cancel():
                _finish(None)

            ok_btn = tk.Button(btn_frame, text="OK", width=8, command=_on_submit)
            ok_btn.pack(side="right", padx=(4, 0))

            cancel_btn = tk.Button(btn_frame, text="Отмена", width=8, command=_on_cancel)
            cancel_btn.pack(side="right")

            entry.bind("<Return>", lambda _: _on_submit())
            entry.bind("<Escape>", lambda _: _on_cancel())
            top.protocol("WM_DELETE_WINDOW", _on_cancel)

            _activate_dialog(top, entry)
            top.after(50, lambda: _activate_dialog(top, entry))
            top.grab_set()
            handed_off = True
        except Exception as exc:
            print(f"move-reminder: failed to open minutes dialog: {exc}", file=sys.stderr)
        finally:
            if not handed_off:
                if top is not None:
                    try:
                        top.destroy()
                    except Exception:
                        pass
                self._dialog_lock.release()

    def _poll_commands(self) -> None:
        root = self._tk_root
        if root is None:
            return
        try:
            while True:
                command = self._commands.get_nowait()
                if command is None:
                    root.destroy()
                    return
                self._handle_command(command)
        except queue.Empty:
            pass
        try:
            root.after(self.TRAY_POLL_MS, self._poll_commands)
        except Exception:
            pass

    def _handle_command(self, command) -> None:
        kind, payload = command
        if kind == "edit_minutes":
            self._open_minutes_dialog(int(payload))

    def _tk_main(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            print(
                "move-reminder: tkinter is not available, minutes dialog is disabled",
                file=sys.stderr,
            )
            self._tk_ready.set()
            return
        try:
            root = tk.Tk()
        except Exception as exc:
            print(f"move-reminder: failed to start GUI thread: {exc}", file=sys.stderr)
            self._tk_root = None
            self._tk_ready.set()
            return
        self._tk_root = root
        self._tk_ready.set()
        try:
            root.withdraw()
            root.after(self.TRAY_POLL_MS, self._poll_commands)
            root.mainloop()
        except Exception as exc:
            print(f"move-reminder: tkinter thread failed: {exc}", file=sys.stderr)

    def _on_quit(self, _icon=None, _item=None) -> None:
        self.stop_timer()
        self._icon.stop()

    def start_timer(self, minutes: int) -> None:
        minutes = max(1, min(minutes, 600))
        self.stop_timer()
        with self._state_lock:
            self.timer_seconds_left = minutes * 60
        self._stop_event.clear()
        self._timer_thread = threading.Thread(target=self._run_timer_loop, daemon=True)
        self._timer_thread.start()
        self._safe_update_menu()

    def stop_timer(self) -> None:
        self._stop_event.set()
        with self._state_lock:
            self.timer_seconds_left = 0
        self._safe_update_menu()

    def _run_timer_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._state_lock:
                if self.timer_seconds_left <= 0:
                    break
            time.sleep(1)
            if self._stop_event.is_set():
                return
            with self._state_lock:
                self.timer_seconds_left -= 1
            self._safe_update_menu()

        with self._state_lock:
            expired = self.timer_seconds_left <= 0
            if expired:
                self.timer_seconds_left = 0

        if expired and not self._stop_event.is_set():
            self._notify_done()
            self._play_sound()
            self._safe_update_menu()

    def _notify_done(self) -> None:
        try:
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(
                "Пора подвигаться",
                "Таймер завершен. Встань и немного разомнись.",
                duration=8,
                threaded=True,
            )
        except Exception as exc:
            print(f"move-reminder: failed to show notification: {exc}", file=sys.stderr)

    def _play_sound(self) -> None:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as exc:
            print(f"move-reminder: failed to play sound: {exc}", file=sys.stderr)

    def run(self) -> None:
        self._tk_thread.start()
        self._tk_ready.wait(10)
        try:
            self._icon.run()
        finally:
            self._commands.put(None)
            self._tk_thread.join(timeout=5)