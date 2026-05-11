#!/usr/bin/env bash
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "This installer must run as root." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR=/opt/led/venv
CONFIG_PATH=/etc/led/config.json

# If this checkout is a git repo and the local branch is behind its upstream,
# offer to pull. If the user pulls, re-exec to pick up the new install.sh.
maybe_self_update() {
    command -v git >/dev/null 2>&1 || return 0
    git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0

    echo "Checking the git checkout for updates..."
    if ! git -C "$SCRIPT_DIR" fetch --quiet 2>/dev/null; then
        echo "  git fetch failed; continuing with the local checkout."
        return 0
    fi

    local upstream
    upstream="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
    if [ -z "$upstream" ]; then
        echo "  no upstream tracking branch configured; skipping update check."
        return 0
    fi

    local local_head upstream_head
    local_head="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"
    upstream_head="$(git -C "$SCRIPT_DIR" rev-parse "$upstream")"

    if [ "$local_head" = "$upstream_head" ]; then
        echo "  already at $upstream ($local_head)."
        return 0
    fi

    echo "Local checkout is behind $upstream:"
    echo "  local:    $local_head"
    echo "  upstream: $upstream_head"
    local answer
    read -rp "Run 'git pull --ff-only' before installing? [y/N]: " answer
    case "$answer" in
        [yY]|[yY][eE][sS])
            git -C "$SCRIPT_DIR" pull --ff-only
            echo "Re-launching installer with the updated code..."
            exec bash "$0" "$@"
            ;;
        *)
            echo "Skipping pull; installing the current local checkout."
            ;;
    esac
}

maybe_self_update "$@"

mkdir -p "$(dirname "$CONFIG_PATH")"

if [ ! -f "$CONFIG_PATH" ]; then
    cp "$SCRIPT_DIR/default_config.json" "$CONFIG_PATH"
    echo "Wrote default config to $CONFIG_PATH"
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required but was not found on PATH." >&2
    exit 1
fi

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    cat >&2 <<'EOF'
ERROR: python3 -m venv is not fully usable on this system
       (the 'venv' or 'ensurepip' module is missing).

Install the appropriate package, then re-run this script:
  Debian / Ubuntu / Mint:  sudo apt install python3-venv
  Fedora / RHEL / CentOS:  sudo dnf install python3
  Arch / Manjaro:          sudo pacman -S python
  openSUSE:                sudo zypper install python3
  Alpine:                  sudo apk add python3
EOF
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating venv at $VENV_DIR..."
    mkdir -p "$(dirname "$VENV_DIR")"
    python3 -m venv "$VENV_DIR"
fi

echo "Installing the led package into $VENV_DIR..."
"$VENV_DIR/bin/pip" install --quiet --force-reinstall --no-deps "$SCRIPT_DIR"

LED_BIN="$VENV_DIR/bin/led"
LED_SEND_BIN="$VENV_DIR/bin/led_send"

ln -sf "$LED_BIN" /usr/local/bin/led
ln -sf "$LED_SEND_BIN" /usr/local/bin/led_send
echo "Linked: /usr/local/bin/led -> $LED_BIN"
echo "Linked: /usr/local/bin/led_send -> $LED_SEND_BIN"

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
