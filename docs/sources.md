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

## `SourceFiles`

Scans a directory on a fixed interval, picks up any `*.json` files, and
forwards their contents to the configured targets. The JSON payload has the
shape `{"message": "...", "files": ["a.jpg", "subdir/b.jpg"]}`. The `files`
key is optional — a payload with no `files` (or an empty list) is delivered
as a plain message. Paths in `files` are resolved relative to `basedir`, so
the source hands targets absolute paths. After a successful dispatch the
`.json` file is renamed to `.json.sent`. Malformed JSON is logged and left
in place so it can be inspected. A periodic sweep removes all files in
`basedir` (recursively) whose mtime is older than `max_age` — this is the
only mechanism that deletes files, cleaning up `.json.sent` files,
referenced media, and any other stragglers.

| Field      | Type             | Required | Default  | Description                                                                |
|------------|------------------|----------|----------|----------------------------------------------------------------------------|
| `basedir`  | string           | yes      | —        | Directory scanned for `*.json` spool files and root for `files`.           |
| `interval` | number (seconds) | no       | `5`      | Delay between directory scans.                                             |
| `max_age`  | number (seconds) | no       | `86400`  | Files older than this in `basedir` are deleted on each scan as cleanup.    |
| `targets`  | array of strings | no       | `[]`     | Target instance IDs that receive each event.                               |

Example:

```json
"spool": {
  "type": "SourceFiles",
  "basedir": "/var/spool/led",
  "interval": 5,
  "targets": ["console"]
}
```

Not every target supports files — see [targets.md](targets.md) for which do.

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
