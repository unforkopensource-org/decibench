# WebSocket Testing

The `ws://` connector is the main path for custom real-time agents.

Use it for:

- your own local or hosted WebSocket voice agent
- agents behind a custom wrapper
- real-time systems where you control the wire contract

## Basic run

```bash
decibench run --target ws://localhost:8000/ws --suite quick
```

## How the connector behaves

The WebSocket connector can send caller turns in several ways:

- raw binary PCM
- JSON with base64 audio
- JSON with byte arrays
- plain text for text-style targets

The exact behavior is controlled by either:

- a preset with `ws_protocol`
- explicit connector keys in `decibench.toml`

## Protocol presets

Available presets:

- `auto`
- `raw-pcm`
- `openai-realtime`
- `twilio`
- `gemini-live`
- `text`

Example:

```toml
[connector]
ws_protocol = "gemini-live"
```

## Useful connector settings

```toml
[connector]
ws_protocol = "auto"
sample_rate = 16000
ws_send_format = "binary"
ws_setup_message = ""
ws_commit_message = ""
ws_recv_timeout = 2.0
ws_silence_max = 2
```

What they mean:

- `sample_rate` - caller audio sample rate sent by Decibench
- `ws_send_format` - `binary`, `json_base64`, `json_bytes`, or `text`
- `ws_setup_message` - JSON message sent immediately after connect
- `ws_commit_message` - JSON message sent after each caller turn
- `ws_recv_timeout` - how long Decibench waits for each receive attempt
- `ws_silence_max` - how many receive timeouts in a row count as end-of-turn

## When `auto` works well

`auto` is a good starting point when:

- the server sends an initial JSON greeting or session message
- the protocol is close to raw PCM or a common JSON audio envelope

## When you should override the preset

Set an explicit preset or connector config when:

- the server accepts the socket but closes on first audio
- the server expects a setup handshake
- the server expects a commit or end-of-turn message
- the server expects JSON instead of raw PCM
- the server expects a different sample rate

## Practical examples

### Raw PCM target

```toml
[connector]
ws_protocol = "raw-pcm"
sample_rate = 16000
```

### Gemini-style wrapper

```toml
[connector]
ws_protocol = "gemini-live"
ws_send_format = "json_base64"
```

### Text-oriented wrapper

```toml
[connector]
ws_protocol = "text"
```

### Custom setup and commit

```toml
[connector]
ws_protocol = "raw-pcm"
ws_setup_message = "{\"type\":\"session.start\"}"
ws_commit_message = "{\"type\":\"audio.end\"}"
```

## Debugging checklist

If the target connects but the run fails:

1. Run `decibench doctor`
2. Confirm the URL is correct
3. Confirm the endpoint is actually a voice WebSocket, not a plain chat socket
4. Try an explicit `ws_protocol`
5. Check the required sample rate
6. Add setup or commit messages if your server expects them
7. Re-run with `-v` for verbose logs

## Common failure pattern

If you see the socket connect cleanly but the server closes during audio
streaming, the usual cause is a protocol mismatch, not a dead server.

That usually means one of:

- wrong `ws_protocol`
- wrong `sample_rate`
- wrong `ws_send_format`
- missing `ws_setup_message`
- missing `ws_commit_message`

## Related guides

- [Quick start](quickstart.md)
- [Native connector status](native-connectors.md)
- [Honest limitations](limitations.md)
