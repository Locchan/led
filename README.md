# Locchan's Event Daemon

A small event-router daemon that listens on a set of configurable sources
(Unix socket, HTTP, directory spool) and fans messages out to a set of
configurable targets (stdout, Telegram, …). Optional multi-node clustering
with health pings is built in.

The daemon is `led`. A tiny CLI client, `led_send`, ships alongside it for
sending events from the local shell. Both read their config from
`/etc/led/config.json`.

## Documentation

- [Installation](docs/installation.md) — installer flow, systemd service,
  prerequisites.
- [Configuration](docs/configuration.md) — overall config shape, instance
  IDs, full example.
- [Sources](docs/sources.md) — `SourceCLI`, `SourceFiles`, `SourceHTTP`, and
  their fields.
- [Targets](docs/targets.md) — `TargetDummy`, `TargetTelegram`, and their
  fields.
- [`led_send`](docs/cli.md) — using the CLI client.
- [Clustering](docs/clustering.md) — multi-node setup, TLS, alerts.

## Quick start

```
sudo bash install.sh
sudo systemctl enable --now led
led_send "hello"
journalctl -u led -f
```

The default config wires a `SourceCLI` to a `TargetDummy`, so after install
the line above should produce `Message from cli: hello` in the journal.
