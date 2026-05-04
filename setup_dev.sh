#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-gi \
  gir1.2-gtk-3.0 \
  gir1.2-notify-0.7 \
  gir1.2-ayatanaappindicator3-0.1 \
  libnotify-bin \
  libcanberra-gtk3-module \
  libcanberra-gtk3-0 \
  pulseaudio-utils

python3 -m venv --system-site-packages "${SCRIPT_DIR}/.venv"

echo "Done. Start app with: ./run.sh"
