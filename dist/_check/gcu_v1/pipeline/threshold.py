from __future__ import annotations
from typing import Any, Dict
from ._utils import utc_now_iso

def _event(events, typ: str, detail: str) -> None:
    events.append({"ts": utc_now_iso(), "type": typ, "detail": detail})

def apply_threshold(ctx: Dict[str, Any], confidence: float, threshold: float) -> str:
    if confidence >= threshold:
        _event(ctx["events"], "hitl_auto", f"confidence {confidence:.2f} >= threshold {threshold:.2f}")
        return "auto"
    _event(ctx["events"], "hitl_human", f"confidence {confidence:.2f} < threshold {threshold:.2f}")
    return "human"
