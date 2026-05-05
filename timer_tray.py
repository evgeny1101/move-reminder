#!/usr/bin/env python3
import atexit
import fcntl
import os
import signal
import subprocess
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")

from gi.repository import GLib, Gtk, Notify  # noqa: E402


def _load_indicator_class():
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # type: ignore

        return AppIndicator3
    except (ValueError, ImportError):
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3  # type: ignore

        return AppIndicator3


AppIndicator3 = _load_indicator_class()


class MoveReminderApp:
    APP_ID = "move-reminder"
    APP_NAME = "Move Reminder"

    def __init__(self) -> None:
        self._single_instance_lock = self._acquire_single_instance_lock()
        Notify.init(self.APP_ID)

        self.indicator = AppIndicator3.Indicator.new(
            self.APP_ID,
            "appointment-soon",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self.timer_seconds_left = 0
        self.timer_source_id: Optional[int] = None
        self.selected_minutes = 45

        self.menu = Gtk.Menu()
        self.indicator.set_menu(self.menu)
        self._build_menu()
        self._refresh_view()

    def _acquire_single_instance_lock(self):
        lock_path = "/tmp/move-reminder.lock"
        lock_file = open(lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            raise SystemExit(0)

        lock_file.write(f"{os.getpid()}\n")
        lock_file.flush()
        atexit.register(lock_file.close)
        return lock_file

    def _build_menu(self) -> None:
        self.status_item = Gtk.MenuItem(label="Осталось: --:--")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.minutes_item = Gtk.MenuItem(label=f"Минуты: {self.selected_minutes}")
        self.minutes_item.connect("activate", self._on_edit_minutes_clicked)
        self.menu.append(self.minutes_item)

        self.start_item = Gtk.MenuItem(label="Старт")
        self.start_item.connect("activate", self._on_start_clicked)
        self.menu.append(self.start_item)

        self.stop_item = Gtk.MenuItem(label="Стоп")
        self.stop_item.connect("activate", self._on_stop_clicked)
        self.menu.append(self.stop_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        presets_label = Gtk.MenuItem(label="Быстрый запуск")
        presets_label.set_sensitive(False)
        self.menu.append(presets_label)

        for minutes in (25, 45, 60):
            preset_item = Gtk.MenuItem(label=f"{minutes} минут")
            preset_item.connect("activate", self._on_preset_clicked, minutes)
            self.menu.append(preset_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Выход")
        quit_item.connect("activate", self._on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()

    def _on_start_clicked(self, _widget: Gtk.Widget) -> None:
        self.start_timer(self.selected_minutes)

    def _on_stop_clicked(self, _widget: Gtk.Widget) -> None:
        self.stop_timer()

    def _on_preset_clicked(self, _widget: Gtk.Widget, minutes: int) -> None:
        self.selected_minutes = minutes
        self._refresh_minutes_label()
        self.start_timer(minutes)

    def _on_edit_minutes_clicked(self, _widget: Gtk.Widget) -> None:
        dialog = Gtk.Dialog(
            title="Изменить минуты",
            modal=True,
        )
        dialog.add_button("Отмена", Gtk.ResponseType.CANCEL)
        dialog.add_button("OK", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_border_width(10)

        label = Gtk.Label(label="Минуты:")
        label.set_xalign(0.0)
        spin = Gtk.SpinButton.new_with_range(1, 600, 1)
        spin.set_numeric(True)
        spin.set_value(self.selected_minutes)

        content.pack_start(label, False, False, 0)
        content.pack_start(spin, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.selected_minutes = int(spin.get_value())
            self._refresh_minutes_label()

        dialog.destroy()

    def _on_quit(self, _widget: Gtk.Widget) -> None:
        self.stop_timer()
        Notify.uninit()
        Gtk.main_quit()

    def start_timer(self, minutes: int) -> None:
        minutes = max(1, min(minutes, 600))
        self.stop_timer()
        self.timer_seconds_left = minutes * 60
        self.timer_source_id = GLib.timeout_add_seconds(1, self._tick)
        self._refresh_view()

    def stop_timer(self) -> None:
        if self.timer_source_id is not None:
            GLib.source_remove(self.timer_source_id)
            self.timer_source_id = None
        self.timer_seconds_left = 0
        self._refresh_view()

    def _tick(self) -> bool:
        self.timer_seconds_left -= 1
        self._refresh_view()

        if self.timer_seconds_left <= 0:
            self.timer_source_id = None
            self.timer_seconds_left = 0
            self._notify_done()
            self._play_sound()
            self._refresh_view()
            return False

        return True

    def _refresh_view(self) -> None:
        if self.timer_seconds_left > 0:
            mm = self.timer_seconds_left // 60
            ss = self.timer_seconds_left % 60
            self.status_item.set_label(f"Осталось: {mm:02d}:{ss:02d}")
            self.start_item.set_sensitive(False)
            self.stop_item.set_sensitive(True)
            self.indicator.set_icon_full("alarm", "timer running")
        else:
            self.status_item.set_label("Осталось: --:--")
            self.start_item.set_sensitive(True)
            self.stop_item.set_sensitive(False)
            self.indicator.set_icon_full("appointment-soon", "timer idle")

    def _refresh_minutes_label(self) -> None:
        self.minutes_item.set_label(f"Минуты: {self.selected_minutes}")

    def _notify_done(self) -> None:
        notification = Notify.Notification.new(
            "Пора подвигаться",
            "Таймер завершен. Встань и немного разомнись.",
            "dialog-information",
        )
        notification.set_urgency(Notify.Urgency.NORMAL)
        notification.show()

    def _play_sound(self) -> None:
        commands = [
            ["canberra-gtk-play", "-i", "complete", "-d", self.APP_NAME],
            [
                "paplay",
                "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
            ],
            [
                "paplay",
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
            ],
        ]
        for command in commands:
            try:
                subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except FileNotFoundError:
                continue


def main() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    MoveReminderApp()
    Gtk.main()


if __name__ == "__main__":
    main()
