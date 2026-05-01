# Decibench Docs

This folder is the user-facing docs map for the current alpha release.

## Start here

If you are using Decibench for the first time, read these in order:

1. [README.md](../README.md)
2. [userinfo.md](../userinfo.md)
3. [Install](install.md)
4. [Quick start](quickstart.md)

## User guides

| Topic | What it covers |
| --- | --- |
| [Install](install.md) | Install paths, verification, optional extras |
| [Quick start](quickstart.md) | First five minutes with the CLI and local workbench |
| [WebSocket testing](websocket-testing.md) | `ws://` targets, presets, and protocol tuning |
| [Local `exec:` testing](exec-testing.md) | Agents you can spawn as local processes |
| [Production import + evaluation](import-and-evaluate.md) | Offline analysis of real calls |
| [Replay to regression](replay-to-regression.md) | Turning failures into reusable scenarios |
| [Native connector status](native-connectors.md) | Retell and Vapi bridge-backed flows |
| [Dashboard / failure workbench](dashboard.md) | Using the local UI |
| [Bridge protocol](bridge-protocol.md) | Local native-bridge wire contract |
| [Honest limitations](limitations.md) | What is still rough or intentionally narrow |

## Truth files

These are the files to trust when you want the current product story:

- [README.md](../README.md)
- [userinfo.md](../userinfo.md)
- [support-matrix.yaml](support-matrix.yaml)

## Maintainer notes

These root-level files are useful for contributors, planning, and internal
engineering context. They are **not** required reading for first-time users:

| File | Why it exists |
| --- | --- |
| [architecture.md](../architecture.md) | Deep architecture and system diagrams |
| [plan.md](../plan.md) | Current roadmap and launch planning |
| [currentbug.md](../currentbug.md) | Bug ledger and audit notes |
| [prod.md](../prod.md) | Product positioning and support truth |
| [techimplemntation.md](../techimplemntation.md) | Implementation planning notes |
| [versionmanagement.md](../versionmanagement.md) | Release/version notes |
| [competet.md](../competet.md) | Competitive research notes |

If you are here to use Decibench, you can safely ignore that maintainer
material and stay inside the README, `userinfo.md`, and this `docs/` folder.
