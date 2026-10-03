#!/usr/bin/env bash
set -euo pipefail
root="$(dirname "$(readlink -f "$0")")"
umask 077
for cmd in uv systemctl python3; do
  command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }
done
unit="$HOME/.config/systemd/user/simple-recipes.service"
if [[ -e "$unit" ]] && ! grep -q '^# Managed by ubruckhaus.simple-recipes$' "$unit"; then
  echo "Refusing to replace existing unmanaged $unit" >&2
  exit 1
fi
runtime="$HOME/.local/share/simple-recipes/runtime"
if [[ ! -x "$runtime/bin/python" ]]; then
  uv venv --python 3.14 "$runtime"
fi
uv pip install --python "$runtime/bin/python" -r "$root/requirements.txt"
# SQLite is included with Python; create or migrate the local database now.
(cd "$root"; PYTHONDONTWRITEBYTECODE=1 "$runtime/bin/python" -c 'from app.recipe_store import initialize; initialize()')
mkdir -p "$(dirname "$unit")"
# systemd specifiers and quoting need escaping for unusual home paths.
escaped_root="${root//%/%%}"
escaped_root="${escaped_root//\\/\\\\}"
escaped_root="${escaped_root//\"/\\\"}"
cat > "$unit" <<EOF
# Managed by ubruckhaus.simple-recipes
[Unit]
Description=Simple Recipes local recipe library
After=graphical-session.target
PartOf=graphical-session.target
[Service]
Type=simple
ExecStart=/usr/bin/bash "$escaped_root/scripts/run.sh"
ExecStopPost=-/usr/bin/systemctl --user stop llama-server.service
UMask=0077
Restart=on-failure
RestartSec=3
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=QT_QPA_PLATFORM=wayland
TimeoutStopSec=10
EOF
systemctl --user daemon-reload
hypr_config="$HOME/.config/hypr/hyprland.lua"
rule_file="$HOME/.config/hypr/simple-recipes.lua"
if [[ -f "$hypr_config" ]]; then
  if [[ -e "$rule_file" ]] && ! grep -q '^-- Managed by ubruckhaus.simple-recipes$' "$rule_file"; then
    echo "Refusing to overwrite unmanaged $rule_file" >&2
    exit 1
  fi
  cat > "$rule_file" <<'RULE'
-- Managed by ubruckhaus.simple-recipes
o.window("^simple-recipes$", { float = true, center = true })
RULE
  if ! grep -Fq 'require("hypr.simple-recipes")' "$hypr_config"; then
    cp "$hypr_config" "$hypr_config.before-simple-recipes-$(date +%s)"
    printf '\n-- Simple Recipes native window\nrequire("hypr.simple-recipes")\n' >> "$hypr_config"
  fi
  if command -v hyprctl >/dev/null; then
    hyprctl reload
    errors="$(hyprctl configerrors)"
    if [[ -n "$errors" && "$errors" != 'ok' ]]; then
      echo "$errors" >&2
      exit 1
    fi
  fi
fi
echo "Setup complete. Enable the plugin with: omarchy plugin enable ubruckhaus.simple-recipes"
echo "The native Python window starts on click, with first-run setup and built-in help."
echo "No browser or HTTP server is used. Stop it with: bash $root/scripts/stop.sh"
