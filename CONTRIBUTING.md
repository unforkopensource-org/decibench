# Contributing to Decibench

Thanks for considering a contribution. This file describes how Decibench is
maintained so a change you spend time on actually lands.

## Brand promise

Decibench has one north star: **the number must be trustworthy**.

That means every contribution is evaluated against three questions:

1. Does this change make the Decibench Score more or less reproducible?
2. Does it match what the docs (especially `docs/support-matrix.yaml` and
   `docs/limitations.md`) already promise?
3. Does it ship with the test that would have caught the bug it fixes?

If your change can answer those three honestly, it's the right shape.

## Working agreement

- **Branch.** Trunk-based on `main`. Short-lived feature branches named
  `v1/<area>-<slug>` (e.g. `v1/p1-percentile-fix`). Squash-merge.
- **Commits.** Conventional commits: `feat: …`, `fix: …`, `chore: …`,
  `test: …`, `docs: …`. Body explains *why*, not what.
- **Signed commits required.** GitHub will reject unsigned commits to `main`.
- **One feature per PR.** A PR that changes scoring math is not the PR that
  also updates the README's installation section.
- **Every PR ships with tests.** No exceptions. If you can't test it, say so
  in the PR description and we'll talk about how to make it testable.

## What every PR description needs

```markdown
## Summary
What changed in one sentence.

## Why
The user-visible reason or the bug this prevents.

## Impact on score
- Same score for the same input?  yes / no
- If no: what moves and by how much, on what fixture?

## Tests
- Which tests prove this?
- Coverage delta?

## Docs
- Any updates to README / docs/ / support-matrix.yaml?
```

The "Impact on score" line is non-negotiable. The product is the number — every
PR has to be honest about whether the number moved.

## What gets blocked

- Any change to `src/decibench/evaluators/score.py`,
  `src/decibench/evaluators/aggregate.py`, or
  `src/decibench/orchestrator.py` that does not include a property test
  and an explicit `## Impact on score` line.
- Any change to `docs/support-matrix.yaml` without a paired test update.
- Any new connector or evaluator without:
  - registration through the existing decorator,
  - a matrix entry with status `experimental` or higher,
  - a contract test.
- Any change that lowers coverage below the floor active for the current phase.

## Setup

```bash
git clone https://github.com/unforkopensource-org/decibench.git
cd decibench
make install
make test
```

`make` targets:

| Target | What it does |
|---|---|
| `make install` | Editable install with `[dev,all]`, plus the bridge sidecar |
| `make test` | `pytest -x --timeout=60` |
| `make cov` | Coverage report (HTML + terminal) |
| `make lint` | `ruff check` + `mypy --strict` |
| `make fmt` | `ruff format` |
| `make bridge` | Build and test the Node bridge sidecar |
| `make release-check` | Pre-release gate (`scripts/release-check.sh`) |

## Reporting bugs

Bug reports must include:

- Decibench version (`decibench version --verbose`).
- The exact command you ran.
- The `seal.json` from a `--output` directory if you have one.
- The expected behavior and the observed behavior.
- A minimal scenario that reproduces if possible.

## Reporting score regressions

If you observe a Decibench Score change you did not expect after upgrading:

1. Run `decibench compare <oldRunId> <newRunId>` and attach the output.
2. Include both `seal.json` files (they're secret-free).
3. Open the issue with the label `score-drift`.

A score-drift bug is treated as a P0 incident.

## License

By contributing, you agree to license your work under Apache-2.0 (see
`LICENSE`).
