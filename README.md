# Locchan's Event Daemon

## Running

For local development:

```
python main.py --config <path>
```

## Installing as a systemd service (Linux)

Run the installer as root from the repo root:

```
sudo bash install.sh
```

The installer will:

1. Prompt for the config file path (default: `/etc/led/config.json`). If the
   file doesn't exist, it writes a stub with empty `sources` and `targets`.
2. Run `pip install --force-reinstall --no-deps .`, which places the `led`
   binary on `PATH`. `--force-reinstall` ensures the new code is picked up
   even if the version in `pyproject.toml` wasn't bumped.
3. Render `led.service` into `/etc/systemd/system/led.service` with the
   resolved `led` binary path and config path substituted in.
4. `systemctl daemon-reload`. If the service is already active, it's
   restarted so the new code takes effect immediately.

After install:

```
sudo $EDITOR /etc/led/config.json    # or wherever you chose
sudo systemctl enable --now led
journalctl -u led -f                 # follow logs
```

To re-deploy after code changes, just run `sudo bash install.sh` again.

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
  "targets": ["TelegramTarget"]
}
```

## Targets

### `TelegramTarget`

Sends each routed message as a Telegram message via the Bot API
(`https://api.telegram.org/bot<token>/sendMessage`).

| Field       | Type   | Required | Default | Description                                                 |
|-------------|--------|----------|---------|-------------------------------------------------------------|
| `bot_token` | string | yes      | —       | Bot token from BotFather.                                   |
| `chat_id`   | string | yes      | —       | Target chat ID (or `@channelusername`).                     |

Example:

```json
"TelegramTarget": {
  "bot_token": "123456:ABC-DEF...",
  "chat_id": "987654321"
}
```

## Full example

```json
{
  "sources": {
    "SourceHTTP": {
      "port": 8080,
      "targets": ["TelegramTarget"]
    }
  },
  "targets": {
    "TelegramTarget": {
      "bot_token": "123456:ABC-DEF...",
      "chat_id": "987654321"
    }
  }
}
```
