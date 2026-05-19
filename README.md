<div align="center">
  <br />

  <h1>decibench</h1>

  <p><code>pip install git+https://github.com/unforkopensource-org/decibench.git</code></p>

  <p>
    <a href="https://github.com/unforkopensource-org/decibench/actions"><img src="https://img.shields.io/github/actions/workflow/status/unforkopensource-org/decibench/ci.yml?style=flat-square&label=ci&color=39FF14" alt="CI" /></a>
    <a href="https://github.com/unforkopensource-org/decibench"><img src="https://img.shields.io/badge/v1.0.0-release-00F0FF?style=flat-square" alt="v1.0.0" /></a>
    <a href="https://github.com/unforkopensource-org/decibench/blob/main/LICENSE"><img src="https://img.shields.io/github/license/unforkopensource-org/decibench?style=flat-square&color=8A2BE2" alt="License" /></a>
    <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?style=flat-square" alt="Python" />
  </p>

  <p>
    <b>The open testing standard for voice AI agents.</b><br/>
    Deterministic + semantic + RAG-augmented evaluation.<br/>
    Local-first. Zero telemetry. One CLI.
  </p>

</div>

<br/>

---

## The Problem

You built a voice AI agent. It works in your demo. Then in production:

- It hallucinates a refund policy that doesn't exist
- It takes 4 seconds to respond and the caller hangs up
- It crumbles when someone interrupts mid-sentence
- It leaks a customer's SSN in the transcript log

You find out from your customers, not your test suite — because you don't have one.

**Decibench fixes this.** It's `pytest` for voice agents.

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                    decibench run                        │
│                                                         │
│  ┌──────────┐    TTS     ┌──────────────┐   Evaluate    │
│  │ Scenario │ ────────▶  │  Your Agent  │ ───────────▶  │
│  │  (YAML)  │   Audio    │  (any target)│   10 metrics  │
│  └──────────┘  ◀──────── └──────────────┘               │
│                    STT                                   │
│                                                         │
│  Score: 87/100 │ Latency p95: 1.2s │ WER: 3.1%         │
│  ✓ compliance  │ ✓ hallucination   │ ✗ interruption     │
└─────────────────────────────────────────────────────────┘
```

1. You write scenarios in YAML (or auto-generate them from your docs)
2. Decibench synthesizes caller audio, calls your agent, transcribes the response
3. 10 evaluators score every call across latency, accuracy, compliance, and more
4. Results go to a local SQLite DB → Rich CLI report, HTML, JUnit, or a full Vue dashboard

---

## Quick Start

```bash
# Install from source
pip install git+https://github.com/unforkopensource-org/decibench.git

# Or clone and install locally
git clone https://github.com/unforkopensource-org/decibench.git
cd decibench
pip install -e .

# Verify the install
decibench doctor

# Run the built-in demo (zero config, zero API keys)
decibench run target=demo suite=quick

# Open the dashboard
decibench serve
```

### Test your own agent

```bash
# WebSocket endpoint (generic — works with any agent)
decibench run target=ws://localhost:8080/ws suite=quick

# Native Vapi / Retell / ElevenLabs
decibench run target=vapi://agent_abc123 suite=standard

# Twilio Media Streams mock (no call credits needed)
decibench run target=twilio://localhost:5050/media suite=realestate

# Spawn a local process and pipe PCM through stdin/stdout
decibench run target='exec:"python my_agent.py"' suite=quick
```

---

## Three Testing Modes

| Mode | What it does | Cost | Speed |
|:--|:--|:--|:--|
| **`deterministic`** | Exact string matching, regex, keyword checks | Free | ~ms |
| **`semantic`** | LLM-as-Judge scores accuracy, compliance, hallucination | ~$0.01/call | ~2s |
| **`semantic+rag`** | Upload your docs → auto-generate adversarial test suites | ~$0.03/call | ~5s |

```bash
# Free deterministic checks only
decibench run target=demo suite=quick --mode deterministic

# Full semantic evaluation with GPT-4o / Claude / Gemini / Ollama
decibench run target=ws://... suite=standard --mode semantic

# Generate tests from your own knowledge base
decibench rag ingest ./docs/training-manual.pdf
decibench rag synthesize --suite-name my-tests --count 20
decibench run target=ws://... suite=my-tests --mode semantic+rag
```

---

## 10 Built-In Evaluators

Every call is scored across all applicable metrics automatically:

| Evaluator | Metric | What it catches |
|:--|:--|:--|
| **Latency** | `p50` `p90` `p95` `ttfb` | Slow responses that cause hangups |
| **WER / CER** | Word/character error rate | Garbled or inaccurate speech |
| **Hallucination** | LLM-graded factual accuracy | Agent invents information |
| **Task Completion** | Did the agent achieve the goal? | Broken conversation flows |
| **Compliance** | Mandatory disclosures, disclaimers | Regulatory violations |
| **Interruption** | Barge-in handling | Agent crashes on user interrupts |
| **Silence** | Dead air detection | Agent goes silent mid-call |
| **MOS** | Mean Opinion Score (DNSMOS) | Audio quality degradation |
| **STOI** | Short-Time Objective Intelligibility | Unintelligible speech |
| **Composite Score** | Weighted aggregate of all metrics | Single pass/fail number |

---

## Connectors

Decibench talks to your agent, not the other way around. No SDK to install in your agent code.

| Connector | Target URI | Status |
|:--|:--|:--|
| **Demo** | `demo://` | ✅ Shipped |
| **WebSocket** | `ws://host:port/path` | ✅ Shipped |
| **HTTP** | `http://host/endpoint` | ✅ Shipped |
| **Process** | `exec:"command"` | ✅ Shipped |
| **ElevenLabs** | `elevenlabs://agent_id` | ✅ Shipped |
| **Twilio Mock** | `twilio://host/path` | ✅ Shipped |
| **Retell** | `retell://agent_id` | 🧪 Experimental |
| **Vapi** | `vapi://agent_id` | 🧪 Experimental |
| **LiveKit** | — | 📋 Planned |
| **Bland** | — | 📋 Planned |

---

## LLM Judge Providers

Semantic evaluation works with any OpenAI-compatible API:

```toml
# decibench.toml
[judge]
provider = "openai"     # or "anthropic", "gemini", "ollama"
model    = "gpt-4o"     # or "claude-sonnet-4-20250514", "gemini-2.5-flash", "llama3"

# Self-hosted? Point at any OpenAI-compatible endpoint
[judge]
provider = "openai"
model    = "mistral-7b"
base_url = "http://localhost:11434/v1"  # Ollama, vLLM, LM Studio, etc.
```

---

## MCP Server

Decibench ships a Model Context Protocol server so AI coding agents (Cursor, Windsurf, Claude Code) can run and analyze your voice tests directly:

```bash
pip install decibench[mcp]
decibench-mcp
```

Tools exposed: `run_test`, `list_runs`, `analyze_failures`, `generate_scenario`, `manage_suites`, and more.

---

## CLI Reference

```
decibench run           Run a test suite against a target
decibench compare       Side-by-side comparison of two targets
decibench serve         Launch the Vue dashboard + REST API
decibench import        Import production call logs (Vapi, Retell, JSONL)
decibench evaluate-calls Score imported calls against evaluators
decibench replay        Re-evaluate a previous run with different settings
decibench rag ingest    Ingest documents into the RAG corpus
decibench rag synthesize Auto-generate test scenarios from your docs
decibench scenario      List / inspect / generate scenarios
decibench runs          List previous test runs
decibench scoring       View scoring weights and policies
decibench doctor        Verify installation and dependencies
decibench auth          Manage API key storage (keyring-backed)
decibench bridge        Launch the headless browser sidecar
```

---

## Architecture

```
decibench/
├── cli/                 # Click CLI — thin wrappers, no business logic
├── connectors/          # Protocol adapters (WS, HTTP, Twilio, ElevenLabs, …)
├── evaluators/          # 10 metric evaluators (latency, WER, hallucination, …)
├── providers/           # Pluggable TTS, STT, and LLM Judge backends
├── reporters/           # Output: Rich terminal, HTML, JSON, JUnit, Markdown
├── rag/                 # Document ingestion, embedding, retrieval, synthesis
├── mcp/                 # Model Context Protocol server (stdio + SSE)
├── store/               # SQLite with migrations, privacy redaction engine
├── bridge/              # Protocol for headless browser sidecar (WebRTC targets)
├── scenarios/           # Built-in test suites (quick, standard, acoustic, adversarial, realestate)
└── api/                 # FastAPI REST server + embedded Vue dashboard
```

---

## Privacy & Security

Decibench is built for teams that handle sensitive call data:

- **Zero telemetry** — no data leaves your machine, ever
- **PII redaction engine** — phone numbers, SSNs, emails, and credit cards are scrubbed from transcripts before they hit the local SQLite database
- **API keys in keyring** — secrets are stored in your OS keychain, not in config files
- **Local-only storage** — SQLite database stays on your machine unless you explicitly export

---

## Configuration

```toml
# decibench.toml

[target]
uri = "ws://localhost:8080/ws"

[tts]
provider = "edge"        # Free Microsoft Edge TTS (default)

[stt]
provider = "faster_whisper"
model    = "base"

[judge]
provider = "openai"
model    = "gpt-4o"

[scoring]
latency_weight       = 0.25
accuracy_weight      = 0.25
compliance_weight    = 0.20
task_completion_weight = 0.20
audio_quality_weight = 0.10
```

---

## Installation

```bash
# Install from GitHub (recommended)
pip install git+https://github.com/unforkopensource-org/decibench.git

# With semantic evaluation + MCP server
pip install "decibench[mcp] @ git+https://github.com/unforkopensource-org/decibench.git"

# With RAG-augmented testing
pip install "decibench[rag] @ git+https://github.com/unforkopensource-org/decibench.git"

# Everything
pip install "decibench[all] @ git+https://github.com/unforkopensource-org/decibench.git"

# Or clone for local development
git clone https://github.com/unforkopensource-org/decibench.git
cd decibench
pip install -e ".[dev]"
```

**Requirements:** Python 3.11+ · macOS / Linux / WSL

> **Note:** PyPI publishing is coming soon. For now, install directly from GitHub.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines. Run the test suite:

```bash
pip install -e ".[dev]"
python -m pytest --timeout=60
python -m ruff check src tests
python -m ruff format --check src tests
```

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).

---

<div align="center">
  <br />
  <p>
    <sub>Built by <a href="https://github.com/unforkopensource-org"><b>Unfork Open Source</b></a></sub>
  </p>
</div>
