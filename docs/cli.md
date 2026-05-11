# `led_send` (CLI client)

`led_send` is a CLI client installed alongside `led`. It always talks to
the daemon over the local Unix socket exposed by `SourceCLI`.

```
led_send "hello world"
```

One positional argument, no flags. Exit codes:

- `0` — success.
- `1` — could not reach the socket, or the daemon rejected the message.
- `2` — usage error.

For `led_send` to work, a `SourceCLI` instance must be present in the
config; the installer's default config includes one. Connection details
(socket path) come from the config file — there's no host/port to pass.

If multiple `SourceCLI` instances are configured (unusual), `led_send` uses
the first one in iteration order and prints which instance ID it sent
through.
