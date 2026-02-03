from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Tuple
from ._utils import read_text_best_effort, utc_now_iso

# Simple keyword-based classifier (deterministic, auditable).
RISK_KEYWORDS = {
    "gdpr": 0.18, "dsgvo": 0.18, "personal data": 0.18, "personenbezogen": 0.18,
    "sanction": 0.14, "sanktion": 0.14, "bribery": 0.16, "korruption": 0.16,
    "aml": 0.14, "money laundering": 0.14, "wäsche": 0.14,
    "confidential": 0.12, "vertraulich": 0.12, "nda": 0.12,
    "audit": 0.10, "revision": 0.10, "investigation": 0.14, "untersuchung": 0.14,
    "termination": 0.10, "kündigung": 0.10, "liability": 0.12, "haftung": 0.12
}

LOW_RISK_KEYWORDS = {
    "marketing": -0.05, "newsletter": -0.05, "press": -0.04, "presse": -0.04
}

def _event(events, typ: str, detail: str) -> None:
    events.append({"ts": utc_now_iso(), "type": typ, "detail": detail})

def classify(input_path: Path, ctx: Dict[str, Any]) -> Dict[str, Any]:
    text = read_text_best_effort(input_path)
    t = text.lower()

    score = 0.50
    explain: List[str] = []

    for k, w in RISK_KEYWORDS.items():
        if k in t:
            score += w
            explain.append(f"risk_signal:{k}")

    for k, w in LOW_RISK_KEYWORDS.items():
        if k in t:
            score += w
            explain.append(f"low_risk_signal:{k}")

    # Clamp 0..1
    score = max(0.0, min(1.0, score))

    label = "risk" if score >= 0.60 else "non-risk"

    _event(ctx["events"], "classified", f"classification={label}, confidence={score:.2f}")

    # Keep explainability short and readable
    explain = explain[:12] if explain else ["no_strong_signals"]

    return {
        "classification": label,
        "confidence": round(score, 4),
        "explainability": explain
    }
