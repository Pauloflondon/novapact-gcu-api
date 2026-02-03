from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Tuple
from ._utils import GovernanceDecision, env_truthy, utc_now_iso

def _event(events, typ: str, detail: str) -> None:
    events.append({"ts": utc_now_iso(), "type": typ, "detail": detail})

def validate_policy(manifest: Dict[str, Any], policy: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[bool, str | None]:
    ext = ctx["input"]["ext"]
    allowed_inputs = set(policy.get("allowed_inputs", []))
    if ext and ext not in allowed_inputs:
        return False, f"Input extension '{ext}' not allowed by policy"

    # Hard forbiddens are conceptual here; enforced by our own code.
    # If you later add tools, check them against policy["forbidden"].

    # Content modification forbidden is enforced by manifest.
    if manifest.get("content_modification", False) is True:
        return False, "Manifest violates content_modification=false requirement"

    return True, None

def decide_governance(manifest: Dict[str, Any], policy: Dict[str, Any], ctx: Dict[str, Any]) -> GovernanceDecision:
    events = ctx["events"]

    kill_enabled = bool(manifest.get("kill_switch", True))
    kill_triggered = kill_enabled and env_truthy("GCU_KILL")
    if kill_triggered:
        _event(events, "kill_switch", "Kill-switch triggered via env GCU_KILL")
        return GovernanceDecision(
            policy_ok=True,
            blocked_reason=None,
            hitl="human",
            threshold=float(manifest.get("confidence_threshold", 0.85)),
            approval_required=True,
            approval_provided=False,
            approval_id=None,
            kill_enabled=kill_enabled,
            kill_triggered=True
        )

    ok, reason = validate_policy(manifest, policy, ctx)
    if not ok:
        _event(events, "policy_block", reason or "Policy blocked execution")
        return GovernanceDecision(
            policy_ok=False,
            blocked_reason=reason,
            hitl="human",
            threshold=float(manifest.get("confidence_threshold", 0.85)),
            approval_required=True,
            approval_provided=False,
            approval_id=None,
            kill_enabled=kill_enabled,
            kill_triggered=False
        )

    _event(events, "policy_ok", "Policy validated")
    return GovernanceDecision(
        policy_ok=True,
        blocked_reason=None,
        hitl="auto",  # may be changed after threshold step
        threshold=float(manifest.get("confidence_threshold", 0.85)),
        approval_required=bool(policy.get("approval", {}).get("required_for", []) and "metadata_write" in policy["approval"]["required_for"]),
        approval_provided=False,
        approval_id=None,
        kill_enabled=kill_enabled,
        kill_triggered=False
    )
