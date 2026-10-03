#!/usr/bin/env bash
set -euo pipefail
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
runtime="$HOME/.local/share/simple-recipes/runtime/bin/python"
[[ -x "$runtime" ]] || { echo "Run bash $root/setup.sh first." >&2; exit 1; }
systemctl --user start simple-recipes.service
cd "$root"
exec "$runtime" -m app.native_ipc ping --wait 30
