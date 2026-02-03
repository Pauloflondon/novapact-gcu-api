import pytest
import importlib

# --- Helpers: Robust imports / attribute discovery ---

def _import_status_machine_module():
    # häufigster Pfad in eurem Projekt
    return importlib.import_module("gcu_v1.status_machine")

def _get_attr_any(obj, names):
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    raise AttributeError(f"None of {names} found on {obj}")

def _make_manager(mod):
    # typische Namen
    cls = _get_attr_any(mod, ["NovaPactStatusManager", "StatusManager", "GCUStatusManager"])
    return cls()

def _make_result(mod, **kwargs):
    # typische Result-Klasse
    Result = _get_attr_any(mod, ["ClassificationResult", "Result", "RunResult"])
    return Result(**kwargs)

def _status_enum(mod):
    # typische Enum
    return _get_attr_any(mod, ["SystemStatus", "Status", "GCUStatus"])

def _status_value(s):
    # Enum vs str
    return s.value if hasattr(s, "value") else s

def _call_process(manager, request_id, result, actor="system", role="auto", auth_type="api_key"):
    # method name variations
    if hasattr(manager, "process_classification"):
        return manager.process_classification(request_id, result, actor, role, auth_type)
    if hasattr(manager, "process"):
        return manager.process(request_id, result, actor=actor, role=role, auth_type=auth_type)
    raise AttributeError("No process method found on manager")

def _call_review_action(manager, request_id, action, actor="admin@example.com", role="admin", auth_type="session", reason="test"):
    if hasattr(manager, "manual_review_action"):
        return manager.manual_review_action(request_id, action, actor, role, auth_type, reason)
    if hasattr(manager, "review_action"):
        return manager.review_action(request_id, action=action, actor=actor, role=role, auth_type=auth_type, reason=reason)
    raise AttributeError("No review action method found on manager")

@pytest.fixture
def sm():
    mod = _import_status_machine_module()
    manager = _make_manager(mod)
    Status = _status_enum(mod)
    return mod, manager, Status

# --- Tests: Governance invariants ---

def test_high_confidence_yields_ok(sm):
    mod, manager, Status = sm

    result = _make_result(
        mod,
        confidence=0.95,
        hitl_required=False,
        approval=False,
        admin_override=False,
        error_occurred=False,
    )

    status = _call_process(manager, "t-ok-1", result)
    assert _status_value(status) in (_status_value(Status.OK), "ok"), status

def test_low_confidence_requires_needs_review(sm):
    mod, manager, Status = sm

    result = _make_result(
        mod,
        confidence=0.60,
        hitl_required=True,
        approval=False,
        admin_override=False,
        error_occurred=False,
    )

    status = _call_process(manager, "t-review-1", result)
    assert _status_value(status) in (_status_value(Status.NEEDS_REVIEW), "needs_review"), status

def test_invariant_never_ok_when_hitl_required(sm):
    mod, manager, Status = sm

    # selbst wenn confidence hoch wäre: hitl_required muss gewinnen
    result = _make_result(
        mod,
        confidence=0.99,
        hitl_required=True,
        approval=False,
        admin_override=False,
        error_occurred=False,
    )

    status = _call_process(manager, "t-guard-1", result)
    assert _status_value(status) not in (_status_value(Status.OK), "ok"), status

def test_manual_approve_transitions_to_approved(sm):
    mod, manager, Status = sm

    # zuerst needs_review erzeugen
    result = _make_result(
        mod,
        confidence=0.60,
        hitl_required=True,
        approval=False,
        admin_override=False,
        error_occurred=False,
    )
    _call_process(manager, "t-approve-1", result)

    # dann approve
    new_status = _call_review_action(manager, "t-approve-1", action="approve")
    assert _status_value(new_status) in (_status_value(Status.APPROVED), "approved"), new_status

def test_manual_reject_transitions_to_rejected(sm):
    mod, manager, Status = sm

    # zuerst needs_review erzeugen
    result = _make_result(
        mod,
        confidence=0.60,
        hitl_required=True,
        approval=False,
        admin_override=False,
        error_occurred=False,
    )
    _call_process(manager, "t-reject-1", result)

    # dann reject
    new_status = _call_review_action(manager, "t-reject-1", action="reject")
    assert _status_value(new_status) in (_status_value(Status.REJECTED), "rejected"), new_status

def test_error_path_forces_error_status(sm):
    mod, manager, Status = sm

    result = _make_result(
        mod,
        confidence=0.90,
        hitl_required=False,
        approval=False,
        admin_override=False,
        error_occurred=True,
    )

    status = _call_process(manager, "t-error-1", result)
    assert _status_value(status) in (_status_value(Status.ERROR), "error"), status
