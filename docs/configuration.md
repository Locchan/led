# Configuration

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
- Each source/target validates its own fields during construction; the
  daemon logs each component's setup line at startup before opening sockets.

See [sources.md](sources.md), [targets.md](targets.md), and
[clustering.md](clustering.md) for the fields each type accepts.

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
