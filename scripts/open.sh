#!/usr/bin/env bash
set -euo pipefail
root="$(dirname "$(dirname "$(readlink -f "$0")")")"
path="${1:-/}"
command=show
argument=()
if [[ "$path" == /einstellungen ]]; then
  command=settings
elif [[ "$path" =~ ^/recipe/([0-9]+)$ ]]; then
  command=recipe
  argument=("${BASH_REMATCH[1]}")
elif [[ "$path" != / ]]; then
  echo "Invalid recipe app path" >&2
  exit 1
fi
bash "$root/scripts/ensure-service.sh" >/dev/null
cd "$root"
exec "$HOME/.local/share/simple-recipes/runtime/bin/python" -m app.native_ipc "$command" "${argument[@]}"
