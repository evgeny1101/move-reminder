#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
  echo "Virtualenv not found. Run: ./setup_dev.sh"
  exit 1
fi

source "${SCRIPT_DIR}/.venv/bin/activate"
exec python "${SCRIPT_DIR}/timer_tray.py"
