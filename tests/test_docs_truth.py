"""Docs-truth guard.

Per `plan.md` Track 3: README and `/docs` claims must match the real product
surface. The machine-readable source of truth is `docs/support-matrix.yaml`.

This test enforces three invariants:

1. Every `connector` listed in the matrix as `shipped` / `beta` / `experimental`
   has a real registered connector class behind it (planned-only entries are
   allowed to have no implementation).
2. Every required documentation file in plan.md's "Minimal Required Docs Set"
   exists on disk.
3. The README's status mentions for native Retell/Vapi do not silently flip to
   "shipped" without the matrix being updated first.

If any of these break, *update the docs/matrix together*, never just the code.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import decibench.connectors  # noqa: F401  — triggers registration
from decibench.connectors.registry import _connector_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def _load_matrix() -> dict:
    text = (DOCS_DIR / "support-matrix.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_support_matrix_parses_and_has_required_sections() -> None:
    matrix = _load_matrix()
    for section in ("connectors", "importers", "evaluators", "cli", "api", "dashboard"):
        assert section in matrix, f"support-matrix.yaml missing `{section}` section"


def _scheme_for(entry: dict, fallback: str) -> str:
    """Pick the URI scheme to look up against the registry.

    Matrix entries spell their connector by descriptive name (`websocket`,
    `process`) but the registry keys by URI scheme (`ws`, `exec`). When a
    `target_uri` field is present we trust it; otherwise the matrix-name is
    used directly so simple cases (`demo`, `http`, `retell`, `vapi`) just work.
    """
    target_uri = entry.get("target_uri")
    if not target_uri:
        return fallback
    if "://" in target_uri:
        return target_uri.split("://", 1)[0]
    if ":" in target_uri:
        return target_uri.split(":", 1)[0]
    return target_uri


def test_real_connectors_back_every_non_planned_matrix_entry() -> None:
    matrix = _load_matrix()
    for name, entry in matrix["connectors"].items():
        status = entry.get("status")
        if status == "planned":
            continue
        scheme = _scheme_for(entry, name)
        assert scheme in _connector_registry, (
            f"support-matrix.yaml lists connector `{name}` (scheme `{scheme}`) "
            f"as `{status}` but no class is registered under that scheme. "
            f"Either register it or flip its status to `planned`."
        )


def test_minimal_required_docs_exist() -> None:
    # Mirrors plan.md "Minimal Required Docs Set". If you delete one of these,
    # update plan.md first — they exist for a reason (user trust on day one).
    required = [
        "install.md",
        "quickstart.md",
        "websocket-testing.md",
        "exec-testing.md",
        "import-and-evaluate.md",
        "replay-to-regression.md",
        "native-connectors.md",
        "dashboard.md",
        "limitations.md",
    ]
    for name in required:
        path = DOCS_DIR / name
        assert path.is_file(), f"Missing required doc: docs/{name}"


def test_every_registered_connector_appears_in_matrix() -> None:
    """Inverse drift: code-registered connectors MUST be in the matrix.

    The forward check (matrix → code) catches "we listed something as
    shipped that doesn't exist." This inverse check catches the much more
    common failure: "we shipped a connector but forgot to flip the matrix
    out of `planned`." The README will market it; the matrix is the source
    of truth; drift kills user trust.
    """
    matrix = _load_matrix()
    matrix_schemes: dict[str, str] = {}
    for name, entry in matrix["connectors"].items():
        scheme = _scheme_for(entry, name)
        matrix_schemes[scheme] = entry.get("status", "planned")

    for scheme in _connector_registry:
        status = matrix_schemes.get(scheme)
        assert status is not None, (
            f"Connector scheme `{scheme}` is registered in code but is missing "
            f"from docs/support-matrix.yaml. Add it under `connectors:`."
        )
        assert status != "planned", (
            f"Connector scheme `{scheme}` is registered in code but the matrix "
            f"lists it as `planned`. Flip the status to `shipped`/`beta`/`experimental`."
        )


def test_every_evaluator_in_standard_stack_appears_in_matrix() -> None:
    """Same inverse-drift principle for the canonical evaluator set."""
    from decibench.evaluators import standard_stack

    matrix = _load_matrix()
    evaluator_section = matrix.get("evaluators", {})

    # Map evaluator.name → matrix-key. Most match directly; some matrix entries
    # group related metrics under a different key (wer/cer, mos, stoi).
    name_to_matrix_key = {
        "wer": ("wer",),
        "latency": ("latency",),
        "mos": ("mos",),
        "intelligibility_estimate": ("stoi",),
        "silence": ("silence",),
        "compliance": ("compliance",),
        "task_completion": ("task_completion",),
        "hallucination": ("hallucination",),
        "interruption": ("interruption",),
    }

    for ev in standard_stack(has_audio=True, has_events=True, has_judge=True):
        candidates = name_to_matrix_key.get(ev.name, (ev.name,))
        found = any(c in evaluator_section for c in candidates)
        assert found, (
            f"Evaluator `{ev.name}` is in the canonical standard_stack() but "
            f"no matching entry exists in docs/support-matrix.yaml `evaluators:` "
            f"(tried: {candidates})."
        )


def test_readme_does_not_reference_nonexistent_maintainer_docs() -> None:
    """Closes the 'README points at files that don't exist' drift class."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # If the README literally names a file like `architecture.md` in backticks,
    # that file must exist at the repo root or under docs/.
    import re

    referenced = set(re.findall(r"`([a-z][a-z0-9_-]*\.md)`", readme))
    # Exclude README itself and well-known repo files we explicitly check elsewhere.
    excluded = {"readme.md"}
    missing = [
        name for name in referenced
        if name.lower() not in excluded
        and not (REPO_ROOT / name).is_file()
        and not (DOCS_DIR / name).is_file()
    ]
    assert not missing, (
        f"README references files that don't exist on disk: {missing}. "
        f"Either add them or remove the references."
    )


def test_native_connectors_not_marketed_as_shipped() -> None:
    """Guard against silent drift: README must not call native Retell/Vapi shipped.

    The matrix is the source of truth — if those connectors flip to `shipped`
    there, this test will pick up the new wording in the README naturally and
    can be updated. But until then, the README must not over-promise.
    """
    matrix = _load_matrix()
    retell_status = matrix["connectors"]["retell"]["status"]
    vapi_status = matrix["connectors"]["vapi"]["status"]
    if retell_status == "shipped" and vapi_status == "shipped":
        return  # Both shipped — README is free to say so.

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    forbidden_phrases = [
        "native retell connector: shipped",
        "native vapi connector: shipped",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in readme, (
            f"README claims `{phrase}` but support-matrix says retell="
            f"{retell_status}, vapi={vapi_status}. Fix the matrix first."
        )
