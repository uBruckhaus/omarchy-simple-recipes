#!/usr/bin/env bash
set -euo pipefail
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
bash "$root/scripts/ensure-service.sh" >/dev/null
cd "$root"
exec "$HOME/.local/share/simple-recipes/runtime/bin/python" -m app.native_ipc toggle
