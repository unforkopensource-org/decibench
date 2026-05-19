"""Three-gate validator for synthesized scenarios.

Gate 1 — Schema:    must satisfy ``Scenario.model_validate``.
Gate 2 — Grounding: every factual entity in caller turns must be reachable
                    in the retrieved chunks (configurable threshold).
Gate 3 — Safety:    no PII patterns (reuses ComplianceEvaluator's regex),
                    no prompt-injection markers, no forbidden phrases.

A synthesized scenario only lands on disk if all three gates pass. Failures
return a structured ``GateReport`` describing which gate complained and why,
so synthesis can retry-with-feedback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from decibench.evaluators.compliance import _PII_PATTERNS
from decibench.evaluators.hallucination import _is_entity_grounded
from decibench.models import Scenario

# Things we never want to see in a synthesized caller turn.
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "system:",
    "<|im_start|>",
    "<|endoftext|>",
    "ALL UPPERCASE INSTRUCTION",
)


@dataclass
class GateReport:
    schema_ok: bool = False
    grounding_ok: bool = False
    safety_ok: bool = False
    grounding_score: float = 0.0  # fraction of facts grounded (0-1)
    grounding_evidence: dict[str, list[str]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.schema_ok and self.grounding_ok and self.safety_ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "schema_ok": self.schema_ok,
            "grounding_ok": self.grounding_ok,
            "safety_ok": self.safety_ok,
            "grounding_score": self.grounding_score,
            "grounding_evidence": dict(self.grounding_evidence),
            "failures": list(self.failures),
        }


def _extract_facts(text: str) -> list[str]:
    """Same entity classes the HallucinationEvaluator uses."""
    facts: list[str] = []
    facts += re.findall(r"\$\d+(?:,\d{3})*(?:\.\d{2})?", text)
    facts += re.findall(r"\b[A-Z]{2,5}-\d{3,}\b", text)
    facts += re.findall(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b", text)
    facts += re.findall(
        r"\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2}\b",
        text,
        re.IGNORECASE,
    )
    facts += re.findall(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        text,
        re.IGNORECASE,
    )
    # Trim trivially small integers
    for n in re.findall(r"\b\d+(?:\.\d+)?\b", text):
        if n not in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "100"}:
            facts.append(n)
    return facts


def validate_scenario(
    scenario_json: dict[str, Any] | Scenario,
    *,
    grounding_corpus: str = "",
    grounding_threshold: float = 0.9,
) -> tuple[Scenario | None, GateReport]:
    """Run the three gates. Returns ``(parsed_scenario | None, GateReport)``.

    ``grounding_corpus`` should be the concatenated text of retrieved chunks
    so the grounding gate can confirm caller-turn facts are derivable from
    the source material.
    """
    report = GateReport()

    # ------------------------------- Gate 1: schema
    try:
        scenario = (
            scenario_json if isinstance(scenario_json, Scenario) else Scenario.model_validate(scenario_json)
        )
        report.schema_ok = True
    except Exception as exc:
        report.failures.append(f"schema: {exc}")
        return None, report

    # ------------------------------- Gate 2: grounding
    caller_text = " ".join(turn.text or "" for turn in scenario.conversation if turn.role == "caller")
    facts = _extract_facts(caller_text)
    if not facts:
        # No factual claims in caller turns → trivially grounded.
        report.grounding_ok = True
        report.grounding_score = 1.0
    else:
        ground_lower = grounding_corpus.lower()
        grounded_count = 0
        for fact in facts:
            if _is_entity_grounded(fact, ground_lower):
                grounded_count += 1
                report.grounding_evidence.setdefault(fact, []).append("matched")
            else:
                report.grounding_evidence.setdefault(fact, []).append("MISSING")
        report.grounding_score = grounded_count / len(facts) if facts else 1.0
        if report.grounding_score >= grounding_threshold:
            report.grounding_ok = True
        else:
            report.failures.append(
                f"grounding: {report.grounding_score:.2f} < threshold {grounding_threshold:.2f}; "
                f"unanchored facts: {[f for f in facts if 'MISSING' in report.grounding_evidence[f]]}"
            )

    # ------------------------------- Gate 3: safety
    safety_issues: list[str] = []
    for turn in scenario.conversation:
        if turn.role != "caller" or not turn.text:
            continue
        for pii_type, pattern in _PII_PATTERNS.items():
            if pattern.search(turn.text):
                safety_issues.append(f"PII in caller turn ({pii_type})")
        lower = turn.text.lower()
        for phrase in _FORBIDDEN_PHRASES:
            if phrase.lower() in lower:
                safety_issues.append(f"prompt-injection marker: {phrase!r}")
    if safety_issues:
        report.failures.append("safety: " + "; ".join(safety_issues))
    else:
        report.safety_ok = True

    if report.passed:
        return scenario, report
    return None, report
