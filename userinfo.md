# Decibench User Guide

This is the practical guide for people using Decibench day to day.

If you only read one file after the README, make it this one.

## 1. What Decibench is

Decibench is a local-first voice agent QA tool. It helps you:

- run scenario suites against a voice agent
- inspect results locally
- import real calls from production exports
- evaluate those imported calls
- turn failures into regression scenarios
- optionally add semantic judging with a local or cloud LLM

Decibench is **not** a hosted SaaS. It does not make you create a
Decibench account or route your runs through a managed backend.

## 2. What alpha means

The current public release is an alpha.

That means:

- the product is real and usable
- core local workflows are working
- the CLI, local workbench, and local store are the center of the product
- some integrations are still rougher than a mature commercial platform
- vendor-specific edge cases can still require tuning

The safest way to think about it is:

> strong local QA tool, still getting sharper around advanced integrations

## 3. Requirements

### Required

- Python 3.11, 3.12, or 3.13

### Optional but common

- Node.js + npm for bridge-backed native connectors
- Ollama for free local semantic evaluation
- provider API keys for OpenAI, Anthropic, Gemini, Retell, Vapi, or ElevenLabs

## 4. Install

### Recommended install

```bash
pipx install git+https://github.com/unforkopensource-org/decibench.git
```

### Direct install with `pip`

```bash
python -m pip install git+https://github.com/unforkopensource-org/decibench.git
```

### Source install for development

```bash
git clone https://github.com/unforkopensource-org/decibench.git
cd testv1
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### Why `pipx install decibench` does not work yet

The package name is not published to PyPI right now.

Use:

```bash
pipx install git+https://github.com/unforkopensource-org/decibench.git
```

not:

```bash
pipx install decibench
```

## 5. First run with no keys and no cost

This is the fastest way to confirm that your install is healthy.

```bash
decibench doctor
decibench init
decibench run --target demo --suite quick --mode deterministic
decibench serve
```

What happens here:

1. `doctor` checks your install and local environment
2. `init` creates `decibench.toml`
3. `run` executes the built-in `demo` target
4. `serve` opens the local workbench API and UI on `127.0.0.1:8000`

## 6. Core ideas to know

### Project config

Decibench stores project config in:

```text
decibench.toml
```

You usually create it with:

```bash
decibench init
```

### Local store

By default Decibench stores runs, imported calls, and evaluations in:

```text
.decibench/decibench.sqlite
```

You can override that per command with:

```bash
decibench serve --store /path/to/decibench.sqlite
decibench run --store /path/to/decibench.sqlite
```

### Secrets

For supported providers, Decibench prefers:

1. system keyring
2. environment variables

It avoids storing raw API keys in `decibench.toml` unless you choose to do
that yourself.

## 7. Target URIs

These are the main target types you can point Decibench at.

| Target type | Example | Best use |
| --- | --- | --- |
| Demo | `demo` | Smoke tests, CI, first run |
| WebSocket | `ws://localhost:8000/ws` | Most real-time agents you control |
| Local process | `exec:python my_agent.py` | Agents you can launch locally |
| HTTP | `http://localhost:8080/invoke` | Batch or endpoint-style flows |
| Retell native | `retell://your_agent_id` | Retell via local bridge |
| Vapi native | `vapi://your_agent_id` | Vapi via local bridge |
| ElevenLabs | `elevenlabs://your_agent_id` | ElevenLabs conversational agents |
| Twilio mock | `twilio://localhost:3000/media-stream` | Local Twilio Media Streams testing |

## 8. Every command that matters

### `decibench init`

Creates a local `decibench.toml`.

```bash
decibench init
decibench init --no-prompt --name my-agent --target ws://localhost:8000/ws
decibench init --provider ollama --model llama3.2:3b
```

Use it when:

- you are starting a new test project
- you want a clean config for the current folder

### `decibench doctor`

Checks your current environment.

```bash
decibench doctor
```

It checks things like:

- Python
- keyring availability
- Node/npm
- workbench server install
- local config
- target reachability for configured HTTP or WebSocket targets
- native bridge readiness for Retell and Vapi

### `decibench run`

Runs a benchmark suite or one specific scenario.

```bash
decibench run --target demo --suite quick --mode deterministic
decibench run --target ws://localhost:8000/ws --suite quick
decibench run --target retell://your_agent_id --suite quick
decibench run --target demo --suite quick --scenario quick-greeting-001
```

Important modes:

- `deterministic` - free, rule-based scoring
- `semantic` - cloud LLM judging
- `semantic-local` - local Ollama judging
- `ask` - interactive mode chooser

### `decibench serve`

Starts the local workbench.

```bash
decibench serve
decibench serve --port 8765
decibench serve --store /path/to/decibench.sqlite
```

Default address:

```text
http://127.0.0.1:8000
```

### `decibench auth`

Manages provider credentials.

```bash
decibench auth list
decibench auth set openai
decibench auth set anthropic
decibench auth set gemini
decibench auth set retell
decibench auth test openai
decibench auth remove gemini
```

Providers supported by `auth` today:

- `openai`
- `anthropic`
- `gemini`
- `vapi`
- `retell`
- `elevenlabs`

### `decibench models`

Helps you choose a semantic provider and model.

```bash
decibench models current
decibench models list openai
decibench models list gemini --curated
decibench models preset ollama balanced
decibench models preset anthropic quality
decibench models use gemini gemini-2.5-pro
```

### `decibench bridge`

Installs and checks the local bridge sidecar used for native Retell and Vapi.

```bash
decibench bridge install
decibench bridge doctor
decibench bridge version
```

Use it for:

- `retell://...`
- `vapi://...`

### `decibench import`

Imports real calls into the local store.

```bash
decibench import jsonl path/to/calls.jsonl
decibench import retell path/to/retell-export.json
decibench import vapi path/to/vapi-export.json
```

### `decibench evaluate-calls`

Grades imported calls already stored locally.

```bash
decibench evaluate-calls
decibench evaluate-calls --failed-only
decibench evaluate-calls --source retell
decibench evaluate-calls --limit 20
```

### `decibench replay`

Inspects an imported call or turns it into a regression scenario.

```bash
decibench replay call_123
decibench replay call_123 --to-scenario scenarios/regressions/call_123.yaml
```

### `decibench runs`

Looks at what is already stored.

```bash
decibench runs list
decibench runs show run_123
decibench runs calls
decibench runs evaluations
decibench runs evaluation-show eval_123
```

### `decibench scenario`

Works with scenario definitions.

```bash
decibench scenario list
decibench scenario validate scenarios/custom/my_scenario.yaml
decibench scenario schema
```

### `decibench scoring`

Adjusts weights and policies.

```bash
decibench scoring show
decibench scoring set-weight compliance 20
decibench scoring set-policy ai_disclosure blocking
decibench scoring reset
```

### `decibench compare`

Runs the same suite against two targets.

```bash
decibench compare --a demo --b ws://localhost:8000/ws --suite quick
```

### `decibench version`

Shows version and environment info.

```bash
decibench version
decibench version --verbose
```

## 9. Deterministic vs semantic evaluation

### Deterministic mode

Best when you want:

- no API cost
- reproducible checks
- quick smoke tests
- CI-friendly baselines

```bash
decibench run --target demo --suite quick --mode deterministic
```

### Semantic mode

Best when you want:

- task-completion style judging
- coherence or hallucination checks
- richer quality calls than rule-based scoring alone

Cloud:

```bash
decibench auth set gemini
decibench models preset gemini balanced
decibench run --target demo --suite quick --mode semantic
```

Local:

```bash
decibench models preset ollama balanced
decibench run --target demo --suite quick --mode semantic-local
```

## 10. Free local models with Ollama

This is the most practical no-subscription LLM path in Decibench today.

### Install Ollama

Official options:

- macOS: install from the official download page
- Windows: install from the official download page
- Linux: use the official install script

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Pull a model

The best default for Decibench right now is:

```bash
ollama pull llama3.2:3b
```

Other useful local options:

- `qwen2.5:3b`
- `llama3.2:3b`
- `phi3:mini`
- `gemma2:2b`

### Start Ollama

```bash
ollama serve
```

### Tell Decibench to use it

```bash
decibench models preset ollama balanced
decibench models current
decibench run --target demo --suite quick --mode semantic-local
```

### How Decibench talks to Ollama

Decibench uses Ollama's OpenAI-compatible local API surface. The model
runs on your machine, so there is no provider key to store for this path.

## 11. Cloud semantic providers

### OpenAI

```bash
decibench auth set openai
decibench models preset openai balanced
decibench run --target demo --suite quick --mode semantic
```

Default balanced model:

```text
gpt-4.1-mini
```

### Anthropic

```bash
decibench auth set anthropic
decibench models preset anthropic balanced
decibench run --target demo --suite quick --mode semantic
```

Default balanced model:

```text
claude-sonnet-4-20250514
```

### Gemini

```bash
decibench auth set gemini
decibench models preset gemini balanced
decibench run --target demo --suite quick --mode semantic
```

Default balanced model:

```text
gemini-2.5-flash
```

## 12. WebSocket testing

Most custom real-time agents should start here:

```bash
decibench run --target ws://localhost:8000/ws --suite quick
```

Useful connector config lives in `decibench.toml`:

```toml
[connector]
ws_protocol = "auto"
sample_rate = 16000
ws_send_format = "binary"
ws_recv_timeout = 2.0
ws_silence_max = 2
```

Available protocol presets:

- `auto`
- `raw-pcm`
- `openai-realtime`
- `twilio`
- `gemini-live`
- `text`

If a WebSocket target connects but closes during streaming, the usual causes
are:

- protocol mismatch
- sample-rate mismatch
- missing setup message
- missing end-of-turn commit message

## 13. Native vendor flows

### Retell and Vapi

These targets rely on the local bridge sidecar.

```bash
decibench bridge install
decibench auth set retell
decibench run --target retell://your_agent_id --suite quick
```

```bash
decibench bridge install
decibench auth set vapi
decibench run --target vapi://your_agent_id --suite quick
```

### ElevenLabs

This path does not use the Retell/Vapi bridge flow.

```bash
decibench auth set elevenlabs
decibench run --target elevenlabs://your_agent_id --suite quick
```

### Twilio local mock

```bash
decibench run --target twilio://localhost:3000/media-stream --suite quick
```

## 14. Import, evaluate, replay

This is the offline QA loop.

```bash
decibench import jsonl calls.jsonl
decibench evaluate-calls
decibench runs calls
decibench replay call_123 --to-scenario scenarios/regressions/call_123.yaml
```

Typical use:

1. import production data
2. score it locally
3. inspect failures in the workbench
4. turn important misses into regression scenarios

## 15. Local workbench

Launch it with:

```bash
decibench serve
```

Use it for:

- recent runs
- stored imported calls
- stored evaluations
- failure review
- replay and regression follow-up

It is local-only unless you deliberately expose the host/port yourself.

## 16. How MCP works

MCP lets another local tool call Decibench as a tool server instead of
shelling out manually.

Think of it like this:

- Decibench stays on your machine
- an MCP client starts or connects to `decibench-mcp`
- the client can ask Decibench to run tests, inspect runs, compare results,
  or read scoring/config information

### Reliable install path for MCP

The base GitHub install does not include the optional `mcp` dependency.
Use this when you want the MCP server:

```bash
python -m pip install "decibench[mcp] @ git+https://github.com/unforkopensource-org/decibench.git"
```

### Run over stdio

```bash
decibench-mcp
```

This is the common path for desktop MCP clients.

### Run over SSE

```bash
decibench-mcp --transport sse --port 8090
```

### Tools exposed today

- `run_test`
- `run_quick_test`
- `list_runs`
- `get_run_detail`
- `get_latest_score`
- `analyze_failures`
- `compare_runs`
- `doctor`
- `list_connectors`
- `list_suites`
- `show_scoring`
- `configure_scoring`

### What MCP is good for

- asking an assistant to run Decibench without copy-pasting shell commands
- wiring Decibench into local agent workflows
- inspecting run history from another tool

## 17. Troubleshooting

### `pipx install decibench` fails

Use the GitHub install:

```bash
pipx install git+https://github.com/unforkopensource-org/decibench.git
```

### `decibench-mcp` fails with `No module named 'mcp'`

Install the MCP extra:

```bash
python -m pip install "decibench[mcp] @ git+https://github.com/unforkopensource-org/decibench.git"
```

### `decibench serve` works but you cannot find the URL

Default URL:

```text
http://127.0.0.1:8000
```

### `decibench auth set ...` says keyring is unavailable

Use environment variables instead:

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GEMINI_API_KEY="..."
export RETELL_API_KEY="..."
export VAPI_API_KEY="..."
export ELEVENLABS_API_KEY="..."
```

### WebSocket target connects but the run fails

Start with:

```bash
decibench doctor
```

Then check:

- the URL is correct
- the target is actually a voice WebSocket, not a text endpoint
- `ws_protocol`
- `sample_rate`
- whether your agent expects a setup message or end-turn commit message

### Native bridge target fails

Check:

```bash
decibench bridge doctor
```

and make sure:

- Node and npm are installed
- bridge install completed
- the right provider key exists

## 18. What to read next

- [README.md](README.md)
- [docs/README.md](docs/README.md)
- [docs/install.md](docs/install.md)
- [docs/quickstart.md](docs/quickstart.md)
- [docs/import-and-evaluate.md](docs/import-and-evaluate.md)
- [docs/native-connectors.md](docs/native-connectors.md)

## 19. Links used for the local-model guidance

- [Ollama download](https://ollama.com/download)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Ollama Llama 3.2 model library](https://ollama.com/library/llama3.2)
