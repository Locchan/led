# Installation

The config file always lives at **`/etc/led/config.json`**. Both `led` (the
daemon) and `led_send` (the CLI client) read it from that fixed path.

## Running for local development

```
python main.py --config <path>
```

When invoked without `--config`, `led` reads `/etc/led/config.json`.

## Installing as a systemd service (Linux)

Run the installer as root from the repo root:

```
sudo bash install.sh
```

The installer will:

1. If the checkout is a git repo and is behind its upstream, prompt to
   `git pull --ff-only` and re-launch itself with the updated code.
2. Ensure `/etc/led/config.json` exists; if not, copy `default_config.json`
   from the repo into place. The default wires `SourceCLI` to `TargetDummy`,
   so a fresh install can be exercised end-to-end with `led_send "hi"`.
3. Create a dedicated virtualenv at `/opt/led/venv` (if absent) and run
   `pip install --force-reinstall --no-deps .` inside it. Using a venv keeps
   the daemon out of the system Python, which on modern Debian/Ubuntu is
   blocked from `pip install` by PEP 668. `--force-reinstall` ensures new
   code is picked up even when the version in `pyproject.toml` wasn't bumped.
4. Symlink `/opt/led/venv/bin/led` and `led_send` into `/usr/local/bin/`
   so both are on the default `PATH`.
5. Render `led.service` into `/etc/systemd/system/led.service` with the
   venv's `led` path substituted into `ExecStart`.
6. `systemctl daemon-reload`. If the service is already active, it's
   restarted so the new code takes effect immediately.

After install:

```
sudo $EDITOR /etc/led/config.json
sudo systemctl enable --now led
journalctl -u led -f                 # follow logs
```

To re-deploy after code changes, just run `sudo bash install.sh` again.

## Prerequisites

- `python3` and the `venv` + `ensurepip` modules (the installer checks
  these up front and prints distro-specific package hints if missing).
- `openssl` on `PATH` (only used at runtime if the cluster subsystem needs
  to auto-generate self-signed TLS certs).
