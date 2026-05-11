# Sources

A source is something that listens for incoming events and pushes them
through the router to one or more targets. Each source class is registered
in `led/Sources/__init__.py` (`ENABLED_SOURCES`).

## `SourceCLI`

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

## `SourceHTTP`

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
