# Move Reminder (кроссплатформенный таймер в трее)

Move Reminder - таймер в системном трее для Linux (Ubuntu GNOME) и Windows 10/11:
- запускается из значка в трее;
- позволяет выбрать минуты и запустить одноразовый таймер;
- по завершении отправляет системное уведомление и проигрывает звук;
- работает в режиме одного экземпляра.

Проект ведется с использованием OpenCode.

## Требования

### Linux (Ubuntu 24.04 GNOME)

- Python 3
- Пакеты: `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-notify-0.7`, `gir1.2-ayatanaappindicator3-0.1`

### Windows 10/11

- Python 3
- Python-пакеты для запуска: `pystray`, `pillow`, `win10toast`
- Для сборки дистрибутива: зависимости из `requirements-windows.txt` и Inno Setup 6 (`ISCC.exe`)

## 1) Настройка окружения для разработки (с venv)

```bash
chmod +x setup_dev.sh run.sh
./setup_dev.sh
./run.sh
```

Примечания:
- `python3-gi` и пакеты GIR устанавливаются через `apt` (системные библиотеки);
- venv создается с `--system-site-packages`, поэтому `gi` доступен внутри venv;
- использовать системный `pip` не требуется.

## 2) Ручной запуск

```bash
./run.sh
```

На Windows:

```bash
python timer_tray.py
```

## Windows: сборка дистрибутива

Сборка portable `.exe` на Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_portable.ps1
```

Результат: `dist/move-reminder-portable.exe`

Сборка установщика `.exe` на Windows (после portable):

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "/DMyAppVersion=1.0.0" ".\packaging\windows\move-reminder.iss"
```

Результат: `dist/move-reminder-setup.exe`

Для релиза рекомендуется передавать версию из тега `vX.Y.Z` как `X.Y.Z` в параметр `MyAppVersion`.

В GitHub Actions Windows-артефакты (`portable.exe` и `setup.exe`) публикуются автоматически при push тега `v*`.

## Проверка изменений

Быстрые проверки перед коммитом:

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python -m py_compile timer_tray.py
```

Проверки скриптов и desktop-файлов (как в CI):

```bash
bash -n run.sh
bash -n setup_dev.sh
bash -n debian/move-reminder-launcher
desktop-file-validate move-reminder.desktop
desktop-file-validate debian/move-reminder.desktop
```

## 3) Необязательное добавление ярлыка

Ярлык рассчитан на запуск установленного Debian-пакета (`Exec=move-reminder-launcher`).
Если пакет уже установлен, дополнительная настройка не нужна.

Для локальной разработки используйте запуск через `./run.sh`.

Если нужно вручную добавить ярлык после установки пакета:

```bash
mkdir -p ~/.local/share/applications
cp move-reminder.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications || true
```

## 4) Сборка пакета для использования без pip на целевой системе

Проект содержит шаблон Debian-пакетирования в `debian/`.

Зависимости для сборки (на машине сборки):

```bash
sudo apt update
sudo apt install -y build-essential debhelper dh-python dpkg-dev
```

Сборка пакета:

```bash
chmod +x debian/rules debian/move-reminder-launcher
dpkg-buildpackage -us -uc -b
```

Результат создается на один уровень выше корня проекта, например:
`../move-reminder_0.1.0-1_all.deb`

Установка на целевой машине:

```bash
sudo apt install ../move-reminder_0.1.0-1_all.deb
```

Переустановка пакета на целевой машине:

```bash
sudo apt install --reinstall ../move-reminder_0.1.0-1_all.deb
```

Удаление пакета с целевой машины:

```bash
sudo apt remove move-reminder
```

Полное удаление пакета вместе с системными конфигурационными файлами:

```bash
sudo apt purge move-reminder
```

Этот вариант запуска использует только системный `python3` и зависимости из `apt` (на целевой системе `pip` не требуется).

## Troubleshooting

- Если нет значка в трее, проверьте что установлен пакет `gir1.2-ayatanaappindicator3-0.1`.
- Если уведомление без звука, проверьте наличие `libcanberra-gtk3-module` и `pulseaudio-utils`.
- Если не запускается из ярлыка, проверьте права на запуск: `chmod +x run.sh`.
- Приложение работает в режиме одного экземпляра: повторный запуск (в том числе по клику на уведомление) не создает второй таймер в трее.

## Ограничения

- Linux-режим рассчитан на Ubuntu GNOME и системный tray/AppIndicator.
- Windows-режим использует `pystray` и может отличаться по отображению в зависимости от shell и настроек уведомлений.
- Неподписанные Windows-бинарники могут показывать предупреждение SmartScreen.
- Таймер одноразовый, без истории и автоповтора.

## Лицензия

MIT, см. файл `LICENSE`.
