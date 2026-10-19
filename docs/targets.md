# Targets

A target is something that receives routed messages from one or more
sources. Each target class is registered in `led/Targets/__init__.py`
(`ENABLED_TARGETS`).

## `TargetDummy`

Prints each routed message to stdout in the form
`Message from <source_instance_id>: <message>`. Useful for smoke-testing a
fresh install. Takes no fields beyond `type`.

When the event also carries files (e.g. from `SourceFiles`), `TargetDummy`
does not send them — it prints the list of filenames and a note that file
delivery is unsupported.

Example:

```json
"console": { "type": "TargetDummy" }
```

## `TargetTelegram`

Sends each routed message as a Telegram message via the Bot API
(`https://api.telegram.org/bot<token>/sendMessage`). Multiple recipients are
supported — pass them as `chat_ids`.

Files ride along as the message caption. The extension picks the method:
`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, and `.gif` use `sendPhoto`;
`.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, and `.m4v` use `sendVideo`
(with streaming enabled). Every other file uses `sendDocument`.

A Telegram API error (`ok: false` in the response body) is not retried.
led sends an alert through this same target and deletes that file. A
timeout or a dropped connection leaves the file in place so the router
can try again.

| Field       | Type                       | Required | Default | Description                                                 |
|-------------|----------------------------|----------|---------|-------------------------------------------------------------|
| `bot_token` | string                     | yes      | —       | Bot token from BotFather.                                   |
| `chat_ids`  | array of strings/integers  | yes\*    | —       | One or more chat IDs (or `@channelusername`).               |
| `chat_id`   | string/integer             | yes\*    | —       | Shorthand for a single recipient; folded into `chat_ids`.   |

\* Exactly one of `chat_ids` or `chat_id` is required. Validation happens
at daemon startup, so misconfigured tokens/chats fail loudly.

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
