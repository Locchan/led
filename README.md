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

The config file is JSON. Both `sources` and `targets` are objects keyed by a
**user-chosen instance ID**; each entry must have a `type` field naming the
class. This means you can run multiple instances of the same type — e.g. two
`TargetTelegram` bots, or two `SourceHTTP` listeners on different ports.

```json
{
  "sources": {
    "<source_instance_id>": {
      "type": "<SourceType>",
      "...": "...source-specific fields..."
    }
  },
  "targets": {
    "<target_instance_id>": {
      "type": "<TargetType>",
      "...": "...target-specific fields..."
    }
  }
}
```

- The instance IDs are free-form; pick whatever is readable (`alerts_bot`,
  `cli`, `http_8080`, …). They show up in logs and in source `targets` lists.
- `type` must match the static `name` attribute of a class registered in
  `led/Sources/__init__.py` (`ENABLED_SOURCES`) or
  `led/Targets/__init__.py` (`ENABLED_TARGETS`).
- A source's `targets` list references target **instance IDs**, not types.
  Dangling references are rejected at startup.
- Each source/target validates its own fields in `_initialize()`; the daemon
  logs each component's setup line at startup before opening sockets.

## Sources

### `SourceCLI`

Listens on a Unix domain socket for messages from `led_send` (or any local
client speaking the same one-line JSON protocol). The daemon reads a single
`{"message": "..."}\n` per connection and replies with `OK\n` or
`ERR <ExceptionName>\n`.

| Field         | Type             | Required | Default              | Description                                                  |
|---------------|------------------|----------|----------------------|--------------------------------------------------------------|
| `socket_path` | string           | no       | `/run/led/cli.sock`  | Filesystem path to the Unix socket.                          |
| `targets`     | array of strings | no       | `[]`                 | Target instance IDs that receive each event.                 |

The socket is created with mode `0660`. Under systemd, `/run/led/` is
provisioned via `RuntimeDirectory=led` in the unit file, so non-root
clients can be granted write access by adding them to the daemon's group.

Example:

```json
"cli": {
  "type": "SourceCLI",
  "targets": ["alerts_bot"]
}
```

### `SourceHTTP`

Listens for HTTP `POST /event` with a JSON body `{"message": "..."}` and
forwards the message to the configured targets via the router.

| Field     | Type             | Required | Default | Description                                                  |
|-----------|------------------|----------|---------|--------------------------------------------------------------|
| `port`    | integer          | no       | `8080`  | TCP port the HTTP server binds to (`0.0.0.0`).               |
| `targets` | array of strings | no       | `[]`    | Target instance IDs that receive each event.                 |

Example:

```json
"http_main": {
  "type": "SourceHTTP",
  "port": 8080,
  "targets": ["alerts_bot"]
}
```

## Targets

### `TargetDummy`

Prints each routed message to stdout in the form
`Message from <source_instance_id>: <message>`. Useful for smoke-testing a
fresh install. Takes no fields beyond `type`.

Example:

```json
"console": { "type": "TargetDummy" }
```

### `TargetTelegram`

Sends each routed message as a Telegram message via the Bot API
(`https://api.telegram.org/bot<token>/sendMessage`). Multiple recipients are
supported — pass them as `chat_ids`.

| Field       | Type                       | Required | Default | Description                                                 |
|-------------|----------------------------|----------|---------|-------------------------------------------------------------|
| `bot_token` | string                     | yes      | —       | Bot token from BotFather.                                   |
| `chat_ids`  | array of strings/integers  | yes\*    | —       | One or more chat IDs (or `@channelusername`).               |
| `chat_id`   | string/integer             | yes\*    | —       | Shorthand for a single recipient; folded into `chat_ids`.   |

\* Exactly one of `chat_ids` or `chat_id` is required. Validation happens in
`_initialize()` at daemon startup, so misconfigured tokens/chats fail loudly.

Example (single recipient):

```json
"alerts_bot": {
  "type": "TargetTelegram",
  "bot_token": "123456:ABC-DEF...",
  "chat_id": "987654321"
}
```

Example (multiple bots and recipients):

```json
"alerts_bot": {
  "type": "TargetTelegram",
  "bot_token": "111:AAA...",
  "chat_ids": ["111111111", "222222222"]
},
"ops_bot": {
  "type": "TargetTelegram",
  "bot_token": "222:BBB...",
  "chat_ids": ["@ops_channel"]
}
```

## Full example

```json
{
  "sources": {
    "cli": {
      "type": "SourceCLI",
      "targets": ["console", "alerts_bot"]
    },
    "http_main": {
      "type": "SourceHTTP",
      "port": 8080,
      "targets": ["alerts_bot"]
    }
  },
  "targets": {
    "console": { "type": "TargetDummy" },
    "alerts_bot": {
      "type": "TargetTelegram",
      "bot_token": "123456:ABC-DEF...",
      "chat_ids": ["987654321"]
    }
  }
}
```
