from typing import Dict, Any, List, Tuple

def _score_text(text: str, keywords: Dict[str, Any]) -> Tuple[float, List[Dict[str, Any]]]:
    t = (text or "").lower()
    explain: List[Dict[str, Any]] = []
    score = 0.0

    for item in keywords.get("high_risk_signals", []):
        sig = (item.get("signal") or "").lower()
        w = float(item.get("weight", 0.0))
        if sig and sig in t:
            score += w
            explain.append({"rule": "HIGH_RISK_SIGNAL", "signal": sig, "weight": w})

    for item in keywords.get("potential_risk_signals", []):
        sig = (item.get("signal") or "").lower()
        w = float(item.get("weight", 0.0))
        if sig and sig in t:
            score += w
            explain.append({"rule": "POTENTIAL_RISK_SIGNAL", "signal": sig, "weight": w})

    for item in keywords.get("safe_signals", []):
        sig = (item.get("signal") or "").lower()
        w = float(item.get("weight", 0.0))
        if sig and sig in t:
            score += w
            explain.append({"rule": "SAFE_SIGNAL", "signal": sig, "weight": w})

    score = max(0.0, min(1.0, score))
    return score, explain


def _apply_policy(score: float, confidence: float) -> Dict[str, Any]:
    classification = "non-risk"
    needs_human = False
    status = "ok"
    primary_rule = "R3_LOW_RISK"
    gate_rule = None

    if score >= 0.75:
        classification = "high-risk"
        needs_human = True
        status = "needs_review"
        primary_rule = "R1_HIGH_RISK"
    elif score >= 0.45:
        classification = "potential-risk"
        needs_human = True
        status = "needs_review"
        primary_rule = "R2_POTENTIAL_RISK"

    # HITL gate: forces needs_review
    if confidence < 0.6:
        needs_human = True
        status = "needs_review"
        gate_rule = "R4_HITL_CONFIDENCE_GATE"

    return {
        "classification": classification,
        "needs_human": needs_human,
        "status": status,
        "primary_rule": primary_rule,
        "gate_rule": gate_rule,
    }


def run_doc_triage(text: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
    keywords = bundle["keywords"]

    score, explain = _score_text(text, keywords)

    # Deterministic confidence v1
    confidence = float(score)

    decision = _apply_policy(score, confidence)

    explain.append({"rule": "POLICY_PRIMARY", "signal": decision["primary_rule"], "weight": 0.0})
    if decision["gate_rule"]:
        explain.append({"rule": "POLICY_GATE", "signal": decision["gate_rule"], "weight": 0.0})

    return {
        "classification": decision["classification"],
        "confidence": confidence,
        "needs_human": decision["needs_human"],
        "explainability": explain,
        "status": decision["status"],
        "meta": {"score": score, "capability": bundle.get("capability")},
    }
