#!/usr/bin/env bash
# Linux VPS bootstrap (Telegram + Excel). Live MT5 native API still needs Windows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "Edit .env and config.yaml, then:"
echo "  source .venv/bin/activate"
echo "  python scripts/login_telegram.py"
echo "  sudo cp scripts/vps/gold-signal-bot.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload && sudo systemctl enable --now gold-signal-bot"
