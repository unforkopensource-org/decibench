# Install

Decibench is a local-first Python tool. There is no hosted signup flow.

## Requirements

### Required

- Python 3.11, 3.12, or 3.13

### Optional, depending on what you want to do

- Node.js + npm for bridge-backed Retell or Vapi targets
- Ollama for free local semantic evaluation
- provider API keys for OpenAI, Anthropic, Gemini, Retell, Vapi, or ElevenLabs

## Recommended install

```bash
pipx install git+https://github.com/unforkopensource-org/decibench.git
```

## Direct `pip` install

```bash
python -m pip install git+https://github.com/unforkopensource-org/decibench.git
```

## Local source install

```bash
git clone https://github.com/unforkopensource-org/decibench.git
cd testv1
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Verify the install

```bash
decibench version
decibench doctor
decibench run --target demo --suite quick --mode deterministic
```

If those work, your base local install is in good shape.

## Why the PyPI command is not the default yet

This alpha is not published under the short PyPI install name.

So use:

```bash
pipx install git+https://github.com/unforkopensource-org/decibench.git
```

instead of:

```bash
pipx install decibench
```

## Optional extras

### MCP

If you want the MCP server, use the `mcp` extra:

```bash
python -m pip install "decibench[mcp] @ git+https://github.com/unforkopensource-org/decibench.git"
```

Verify:

```bash
decibench-mcp --help
```

### Development

```bash
pip install -e .[dev]
```

## Optional local-model path

For free local semantic evaluation, install Ollama and then:

```bash
ollama pull llama3.2:3b
ollama serve
decibench models preset ollama balanced
```

## Optional native bridge path

For `retell://...` and `vapi://...` targets:

```bash
decibench bridge install
decibench bridge doctor
```

## Next step

Go to [Quick start](quickstart.md).
