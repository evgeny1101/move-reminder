import atexit
import os
import pathlib
import subprocess
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


class MoveReminderWindowsApp:
    APP_NAME = "Move Reminder"

    def __init__(self) -> None:
        self._single_instance_lock = self._acquire_single_instance_lock()
        self._state_lock = threading.Lock()
        self.timer_seconds_left = 0
        self.selected_minutes = 45
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
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

        value = self._ask_minutes_with_tk_dialog(initial_minutes)
        if value is None:
            return

        with self._state_lock:
            self.selected_minutes = value
        self._safe_update_menu()

    def _ask_minutes_with_tk_dialog(self, initial_minutes: int) -> Optional[int]:
        script = (
            "import sys\n"
            "import tkinter as tk\n"
            "from tkinter import simpledialog\n"
            "root = tk.Tk()\n"
            "root.withdraw()\n"
            "value = simpledialog.askinteger(\n"
            "    'Изменить минуты',\n"
            "    'Минуты:',\n"
            "    initialvalue=int(sys.argv[1]),\n"
            "    minvalue=1,\n"
            "    maxvalue=600,\n"
            ")\n"
            "root.destroy()\n"
            "if value is not None:\n"
            "    print(value)\n"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", script, str(initial_minutes)],
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except Exception as exc:
            print(f"move-reminder: failed to open minutes dialog: {exc}", file=sys.stderr)
            return None

        if result.returncode != 0:
            error = result.stderr.strip() or f"exit code {result.returncode}"
            print(f"move-reminder: minutes dialog failed: {error}", file=sys.stderr)
            return None

        output = result.stdout.strip()
        if not output:
            return None

        try:
            value = int(output)
        except ValueError:
            print("move-reminder: invalid minutes dialog output", file=sys.stderr)
            return None

        return max(1, min(value, 600))

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
        self._icon.run()
