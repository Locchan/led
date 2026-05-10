#!/usr/bin/env bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "This installer must run as root." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

CONFIG_PATH=/etc/led/config.json
mkdir -p "$(dirname "$CONFIG_PATH")"

if [ ! -f "$CONFIG_PATH" ]; then
    cat > "$CONFIG_PATH" <<'EOF'
{
  "sources": {},
  "targets": {}
}
EOF
    echo "Wrote stub config at $CONFIG_PATH"
fi

echo "Installing the led package..."
pip install --force-reinstall --no-deps "$SCRIPT_DIR"

LED_BIN="$(command -v led)"
if [ -z "$LED_BIN" ]; then
    echo "Could not locate the 'led' binary on PATH after install." >&2
    exit 1
fi
echo "led binary at: $LED_BIN"

UNIT_PATH=/etc/systemd/system/led.service
sed -e "s|%LED_BIN%|$LED_BIN|g" "$SCRIPT_DIR/led.service" > "$UNIT_PATH"
echo "Installed unit file: $UNIT_PATH"

systemctl daemon-reload

if systemctl is-active --quiet led; then
    echo "Restarting led service to pick up new code..."
    systemctl restart led
fi

cat <<EOF

Done. Next steps:
  1. Edit $CONFIG_PATH to configure sources and targets (see README.md).
  2. systemctl enable --now led
  3. journalctl -u led -f   # to watch logs
EOF
