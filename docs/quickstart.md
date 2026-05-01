# Quick Start

This gets you from install to a real stored run and a local UI in a few
minutes.

## 1. Check the environment

```bash
decibench doctor
```

If you have not created a project config yet, `doctor` will warn you. That
is normal.

## 2. Create local config

```bash
decibench init
```

For a non-interactive setup:

```bash
decibench init --no-prompt --name my-agent --target demo
```

## 3. Run the free deterministic smoke test

```bash
decibench run --target demo --suite quick --mode deterministic
```

This uses the built-in demo target and does not require any API key.

## 4. Open the local workbench

```bash
decibench serve
```

Open:

```text
http://127.0.0.1:8000
```

## 5. Point it at your real target

### WebSocket target

```bash
decibench run --target ws://localhost:8000/ws --suite quick
```

### Local process target

```bash
decibench run --target 'exec:python my_agent.py' --suite quick
```

### HTTP target

```bash
decibench run --target http://localhost:8080/invoke --suite quick
```

### Bridge-backed native target

```bash
decibench bridge install
decibench run --target retell://your_agent_id --suite quick
```

## 6. Add semantic judging later

### Cloud

```bash
decibench auth set gemini
decibench models preset gemini balanced
decibench run --target demo --suite quick --mode semantic
```

### Local Ollama

```bash
ollama pull llama3.2:3b
ollama serve
decibench models preset ollama balanced
decibench run --target demo --suite quick --mode semantic-local
```

## 7. Import real calls

```bash
decibench import jsonl calls.jsonl
decibench evaluate-calls
decibench serve
```

## 8. What to read next

- [userinfo.md](../userinfo.md)
- [WebSocket testing](websocket-testing.md)
- [Production import + evaluation](import-and-evaluate.md)
- [Native connector status](native-connectors.md)
