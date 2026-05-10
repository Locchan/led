# Locchan's Event Daemon

The config file always lives at **`/etc/led/config.json`**. Both `led` (the
daemon) and `led_send` (the CLI client) read it from that fixed path.

## Running

For local development:

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

1. Ensure `/etc/led/config.json` exists; if not, copy `default_config.json`
   from the repo into place. The default wires `SourceCLI` to `TargetDummy`,
   so a fresh install can be exercised end-to-end with `led_send "hi"`.
2. Create a dedicated virtualenv at `/opt/led/venv` (if absent) and run
   `pip install --force-reinstall --no-deps .` inside it. Using a venv keeps
   the daemon out of the system Python, which on modern Debian/Ubuntu is
   blocked from `pip install` by PEP 668. `--force-reinstall` ensures new
   code is picked up even when the version in `pyproject.toml` wasn't bumped.
3. Symlink `/opt/led/venv/bin/led` and `led_send` into `/usr/local/bin/`
   so both are on the default `PATH`.
4. Render `led.service` into `/etc/systemd/system/led.service` with the
   venv's `led` path substituted into `ExecStart`.
5. `systemctl daemon-reload`. If the service is already active, it's
   restarted so the new code takes effect immediately.

After install:

```
sudo $EDITOR /etc/led/config.json
sudo systemctl enable --now led
journalctl -u led -f                 # follow logs
```

To re-deploy after code changes, just run `sudo bash install.sh` again.

## Sending events (`led_send`)

`led_send` is a CLI client installed alongside `led`. It always talks to
the daemon over the local Unix socket exposed by `SourceCLI`.

```
led_send "hello world"
```

One positional argument, no flags. Exit code is `0` on success, `1` if the
socket could not be reached or the daemon rejected the message, `2` on a
usage error. For `led_send` to work, `SourceCLI` must be present in the
config; the installer's stub config includes it by default.

## Configuration file

The config file is JSON with the following top-level shape:

```json
{
  "sources": {
    "<SourceName>": { ...source config... }
  },
  "targets": {
    "<TargetName>": { ...target config... }
  }
}
```

- `sources` and `targets` are **objects** (not arrays).
- Each key must match the static `name` attribute of a class registered in
  `led/Sources/__init__.py` (`ENABLED_SOURCES`) or
  `led/Targets/__init__.py` (`ENABLED_TARGETS`).
- Validation happens at startup; unknown names abort with a `ValueError`.

## Sources

### `SourceCLI`

Listens on a Unix domain socket for messages from `led_send` (or any local
client speaking the same one-line JSON protocol). The daemon reads a single
`{"message": "..."}\n` per connection and replies with `OK\n` or
`ERR <ExceptionName>\n`.

| Field         | Type             | Required | Default              | Description                                                  |
|---------------|------------------|----------|----------------------|--------------------------------------------------------------|
| `socket_path` | string           | no       | `/run/led/cli.sock`  | Filesystem path to the Unix socket.                          |
| `targets`     | array of strings | no       | `[]`                 | Names of targets that receive each event.                    |

The socket is created with mode `0660`. Under systemd, `/run/led/` is
provisioned via `RuntimeDirectory=led` in the unit file, so non-root
clients can be granted write access by adding them to the daemon's group.

Example:

```json
"SourceCLI": {
  "targets": ["TargetTelegram"]
}
```

### `SourceHTTP`

Listens for HTTP `POST /event` with a JSON body `{"message": "..."}` and
forwards the message to the configured targets via the router.

| Field     | Type             | Required | Default | Description                                                  |
|-----------|------------------|----------|---------|--------------------------------------------------------------|
| `port`    | integer          | no       | `8080`  | TCP port the HTTP server binds to (`0.0.0.0`).               |
| `targets` | array of strings | no       | `[]`    | Names of targets (from `targets`) that receive each event.   |

Example:

```json
"SourceHTTP": {
  "port": 8080,
  "targets": ["TargetTelegram"]
}
```

## Targets

### `TargetDummy`

Prints each routed message to stdout in the form
`Message from <SourceName>: <message>`. Useful for smoke-testing a fresh
install. Takes no fields.

Example:

```json
"TargetDummy": {}
```

### `TargetTelegram`

Sends each routed message as a Telegram message via the Bot API
(`https://api.telegram.org/bot<token>/sendMessage`).

| Field       | Type   | Required | Default | Description                                                 |
|-------------|--------|----------|---------|-------------------------------------------------------------|
| `bot_token` | string | yes      | —       | Bot token from BotFather.                                   |
| `chat_id`   | string | yes      | —       | Target chat ID (or `@channelusername`).                     |

Example:

```json
"TargetTelegram": {
  "bot_token": "123456:ABC-DEF...",
  "chat_id": "987654321"
}
```

## Full example

```json
{
  "sources": {
    "SourceCLI": {
      "targets": ["TargetTelegram"]
    },
    "SourceHTTP": {
      "port": 8080,
      "targets": ["TargetTelegram"]
    }
  },
  "targets": {
    "TargetTelegram": {
      "bot_token": "123456:ABC-DEF...",
      "chat_id": "987654321"
    }
  }
}
```
