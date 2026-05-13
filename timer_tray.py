#!/usr/bin/env python3

import signal
import sys

if sys.platform.startswith("win"):
    from windows_app import MoveReminderWindowsApp as MoveReminderApp

    def main() -> None:
        MoveReminderApp().run()


else:
    from linux_app import Gtk, MoveReminderApp

    def main() -> None:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        MoveReminderApp()
        Gtk.main()


if __name__ == "__main__":
    main()
