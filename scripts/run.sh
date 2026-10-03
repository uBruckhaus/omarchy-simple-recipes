#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$(dirname "$(readlink -f "$0")")")"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
export PYTHONDONTWRITEBYTECODE=1
exec "$HOME/.local/share/simple-recipes/runtime/bin/python" -m app.native --background
