from __future__ import annotations

import os
import json
import time
import logging
from datetime import datetime
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from gcu_v1.persistence.status_store import init_db, load_run_state, persist_run_state

from gcu_v1.status_machine import (
    NovaPactStatusManager,
    ClassificationResult,
    SystemStatus,
    StatusTransitionError,
    AdminOverrideError,
)

# ==================== FASTAPI APP ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        DB_INIT_SUCCESS.set(1)
    except Exception:
        DB_INIT_SUCCESS.set(0)
        raise
    yield
app = FastAPI(title="NovaPact GCU API", version="1.0.0", lifespan=lifespan)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

status_manager = NovaPactStatusManager()

# ==================== CONFIG (update-safe) ====================

DEFAULT_CAPABILITY = "np_document_triage"
DEFAULT_THRESHOLD = 0.75  # fallback only
DEFAULT_MANIFEST_PATH = "gcu_v1/agents/agent_01_doc_triage/manifest.json"


def _env(key: str, default: str = "") -> str:
    v = os.getenv(key, default)
    return v.strip() if isinstance(v, str) else default


def _get_capability() -> str:
    return _env("NP_CAPABILITY", DEFAULT_CAPABILITY)


def _get_threshold() -> float:
    raw = _env("NP_CONFIDENCE_THRESHOLD", str(DEFAULT_THRESHOLD))
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid NP_CONFIDENCE_THRESHOLD=%r; using %s", raw, DEFAULT_THRESHOLD)
        return DEFAULT_THRESHOLD


def _get_manifest_path() -> str:
    mp = _env("NP_MANIFEST_PATH", DEFAULT_MANIFEST_PATH)
    mp = mp.replace("\\", "/").strip()
    if not os.path.isabs(mp):
        mp = os.path.abspath(mp).replace("\\", "/")
    return mp


# ==================== GOVERNANCE AUDIT (persistent, per-run) ====================

def _run_output_dir(run_id: str) -> str:
    base = os.path.join("gcu_v1", "outputs", run_id)
    os.makedirs(base, exist_ok=True)
    return base


def _governance_audit_path(run_id: str) -> str:
    return os.path.join(_run_output_dir(run_id), "governance_audit.jsonl")


def _append_governance_audit(run_id: str, event: str, payload: Dict[str, Any]) -> None:
    rec = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "run_id": run_id,
        "event": event,
        "payload": payload,
    }
    path = _governance_audit_path(run_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# ==================== PROMETHEUS METRICS ====================

HTTP_REQUESTS_TOTAL = Counter(
    "gcu_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "gcu_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

HTTP_EXCEPTIONS_TOTAL = Counter(
    "gcu_http_exceptions_total",
    "Unhandled exceptions in request handling",
    ["path", "exception_type"],
)

DB_INIT_SUCCESS = Gauge(
    "gcu_db_init_success",
    "1 if DB init succeeded on startup; 0 otherwise",
)

GOV_OUTCOME_TOTAL = Counter(
    "gcu_governance_outcome_total",
    "Governance outcomes produced by /run",
    ["outcome"],  # ok | needs_review | approved | rejected | error
)

GOV_HITL_REQUIRED_TOTAL = Counter(
    "gcu_governance_hitl_required_total",
    "Runs where HITL was required",
    ["required"],  # true|false
)

GOV_REVIEW_ACTION_TOTAL = Counter(
    "gcu_governance_review_action_total",
    "Manual review actions",
    ["action"],  # approve|reject
)

GOV_ADMIN_OVERRIDE_TOTAL = Counter(
    "gcu_governance_admin_override_total",
    "Admin overrides applied",
    ["target_status"],
)

RUN_PIPELINE_DURATION_SECONDS = Histogram(
    "gcu_run_pipeline_duration_seconds",
    "Pipeline execution duration for /run (run_capability)",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 60),
)

RUN_GOVERNANCE_DURATION_SECONDS = Histogram(
    "gcu_run_governance_duration_seconds",
    "Governance decision duration for /run (status machine + persistence)",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        method = request.method
        start = time.perf_counter()
        response = None

        # ---- stable path label (route template) ----
        path = request.url.path
        try:
            # Match against Starlette routes to extract template path
            for r in request.app.router.routes:
                match, _ = r.matches(request.scope)
                if getattr(match, "name", "") == "FULL":
                    if getattr(r, "path", None):
                        path = r.path
                    break
        except Exception:
            path = request.url.path
        # --------------------------------------------

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            HTTP_EXCEPTIONS_TOTAL.labels(path=path, exception_type=type(e).__name__).inc()
            raise
        finally:
            elapsed = time.perf_counter() - start
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(elapsed)
            status_code = str(getattr(response, "status_code", 500))
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()


app.add_middleware(PrometheusMiddleware)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)



# ==================== MODELS ====================

class RunRequest(BaseModel):
    capability: str
    payload: Dict[str, Any]
    actor: str = "system"
    role: str = "auto"
    auth_type: str = "api_key"


class ReviewRequest(BaseModel):
    action: str  # "approve" | "reject"
    actor: str
    role: str
    auth_type: str
    reason: Optional[str] = None


class AdminOverrideRequest(BaseModel):
    target_status: str
    actor: str
    role: str
    auth_type: str
    reason: str


# ==================== ENDPOINTS ====================

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/config")
def debug_config() -> Dict[str, Any]:
    return {
        "NP_CAPABILITY": _get_capability(),
        "NP_CONFIDENCE_THRESHOLD": _get_threshold(),
        "NP_MANIFEST_PATH": _get_manifest_path(),
    }


@app.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    """
    NP â€“ Document Triage v1.0
    Governance-first execution endpoint.
    """
    capability_expected = _get_capability()
    threshold = _get_threshold()
    manifest_path = _get_manifest_path()

    if req.capability != capability_expected:
        raise HTTPException(status_code=400, detail=f"Invalid capability. Expected '{capability_expected}'.")

    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=500, detail=f"Manifest not found: {manifest_path}")

    try:
        from gcu_v1.api.run import run_capability
    except ImportError:
        raise HTTPException(status_code=500, detail="run_capability not found")

    try:
        logger.debug("=== RUN START ===")
        logger.debug(
            "CONFIG: capability_expected=%s threshold=%s manifest=%s",
            capability_expected,
            threshold,
            manifest_path,
        )

        # 1) Execute pipeline
        t0 = time.perf_counter()
        pipeline_result = run_capability(
            capability=req.capability,
            payload=req.payload,
            manifest=manifest_path,
        )
        RUN_PIPELINE_DURATION_SECONDS.observe(time.perf_counter() - t0)

        logger.debug("PIPELINE RESULT:")
        for k, v in pipeline_result.items():
            logger.debug("  %s: %s", k, v)

        pipeline_status = pipeline_result.get("status", "error")
        if pipeline_status not in ["ok", "needs_review"]:
            GOV_OUTCOME_TOTAL.labels(outcome=str(pipeline_status)).inc()
            return pipeline_result

        run_id = pipeline_result.get("run_id", "unknown")

        # Governance audit: config snapshot
        _append_governance_audit(run_id, "GOV_CONFIG", {
            "capability_expected": capability_expected,
            "threshold": threshold,
            "manifest_path": manifest_path,
        })

        # 2) GOVERNANCE (DB-backed Source of Truth)
        g0 = time.perf_counter()

        confidence = float(pipeline_result.get("confidence", 0.0))
        human_required = confidence < threshold

        # Enforced for v1.0 â€“ no auto-approval
        approval_provided = False

        classification_result = ClassificationResult(
            confidence=confidence,
            hitl_required=human_required,
            approval=approval_provided,
            admin_override=False,
            error_occurred=False,
        )

        status = status_manager.process_classification(
            request_id=run_id,
            classification_result=classification_result,
            actor=req.actor,
            role=req.role,
            auth_type=req.auth_type,
        )

        _append_governance_audit(run_id, "GOV_STATUS_COMPUTED", {
            "status": str(status),
            "confidence": confidence,
            "hitl_required": human_required,
            "approval_provided": approval_provided,
            "actor": req.actor,
            "role": req.role,
            "auth_type": req.auth_type,
        })

        # HARD RULE: HITL required + no approval => needs_review (never ok)
        if human_required and (not approval_provided):
            status = SystemStatus.NEEDS_REVIEW
            _append_governance_audit(run_id, "GOV_HARD_RULE_APPLIED", {
                "rule": "hitl_required_and_no_approval => needs_review",
                "status": "needs_review",
            })

        pipeline_result["status"] = str(status)
        pipeline_result["needs_review"] = (status == SystemStatus.NEEDS_REVIEW)

        persist_run_state(
            run_id=run_id,
            status=str(status),
            hitl_required=human_required,
            approval_required=True,
            approval_provided=approval_provided,
        )

        _append_governance_audit(run_id, "GOV_DB_PERSISTED", {
            "status": str(status),
            "hitl_required": human_required,
            "approval_required": True,
            "approval_provided": approval_provided,
        })

        RUN_GOVERNANCE_DURATION_SECONDS.observe(time.perf_counter() - g0)

        # Prometheus governance counters
        GOV_OUTCOME_TOTAL.labels(outcome=str(status)).inc()
        GOV_HITL_REQUIRED_TOTAL.labels(required=str(human_required).lower()).inc()

        pipeline_result["governance_audit"] = _governance_audit_path(run_id).replace("\\", "/")

        logger.debug("FINAL STATUS: %s", pipeline_result["status"])
        logger.debug("=== RUN END ===")
        return pipeline_result

    except Exception as e:
        logger.error("RUN ERROR", exc_info=True)
        GOV_OUTCOME_TOTAL.labels(outcome="error").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review/{run_id}")
def review(run_id: str, review_req: ReviewRequest) -> Dict[str, Any]:
    try:
        if review_req.action not in ["approve", "reject"]:
            raise HTTPException(status_code=400, detail="Invalid review action")

        new_status = status_manager.manual_review_action(
            request_id=run_id,
            action=review_req.action,
            actor=review_req.actor,
            role=review_req.role,
            auth_type=review_req.auth_type,
            reason=review_req.reason,
        )

        prev = load_run_state(run_id) or {
            "hitl_required": True,
            "approval_required": True,
            "approval_provided": False,
        }
        approval_now = True if review_req.action == "approve" else False

        persist_run_state(
            run_id=run_id,
            status=str(new_status),
            hitl_required=bool(prev.get("hitl_required", True)),
            approval_required=bool(prev.get("approval_required", True)),
            approval_provided=approval_now,
        )

        _append_governance_audit(run_id, "GOV_REVIEW_ACTION", {
            "action": review_req.action,
            "new_status": str(new_status),
            "actor": review_req.actor,
            "role": review_req.role,
            "auth_type": review_req.auth_type,
            "reason": review_req.reason,
            "approval_provided": approval_now,
        })

        GOV_REVIEW_ACTION_TOTAL.labels(action=review_req.action).inc()
        GOV_OUTCOME_TOTAL.labels(outcome=str(new_status)).inc()

        return {
            "run_id": run_id,
            "status": str(new_status),
            "action": review_req.action,
            "actor": review_req.actor,
        }

    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found")
    except StatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("REVIEW ERROR", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/override/{run_id}")
def admin_override(run_id: str, override_req: AdminOverrideRequest) -> Dict[str, Any]:
    try:
        try:
            target_status = SystemStatus(override_req.target_status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid target_status")

        new_status = status_manager.admin_override(
            request_id=run_id,
            target_status=target_status,
            actor=override_req.actor,
            role=override_req.role,
            auth_type=override_req.auth_type,
            reason=override_req.reason,
        )

        prev = load_run_state(run_id) or {
            "hitl_required": True,
            "approval_required": True,
            "approval_provided": False,
        }

        persist_run_state(
            run_id=run_id,
            status=str(new_status),
            hitl_required=bool(prev.get("hitl_required", True)),
            approval_required=bool(prev.get("approval_required", True)),
            approval_provided=bool(prev.get("approval_provided", False)),
        )

        _append_governance_audit(run_id, "GOV_ADMIN_OVERRIDE", {
            "target_status": override_req.target_status,
            "new_status": str(new_status),
            "actor": override_req.actor,
            "role": override_req.role,
            "auth_type": override_req.auth_type,
            "reason": override_req.reason,
        })

        GOV_ADMIN_OVERRIDE_TOTAL.labels(target_status=override_req.target_status).inc()
        GOV_OUTCOME_TOTAL.labels(outcome=str(new_status)).inc()

        return {
            "run_id": run_id,
            "status": str(new_status),
            "actor": override_req.actor,
            "role": override_req.role,
            "admin_override": True,
        }

    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found")
    except (StatusTransitionError, AdminOverrideError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error("ADMIN OVERRIDE ERROR", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/status/{run_id}")
def debug_status(run_id: str) -> Dict[str, Any]:
    row = load_run_state(run_id)
    status = row["status"] if row else None
    return {
        "run_id": run_id,
        "status": str(status) if status else "NOT_FOUND",
        "exists": status is not None,
    }


@app.get("/debug/audit/{run_id}")
def debug_audit(run_id: str) -> Dict[str, Any]:
    gov_path = _governance_audit_path(run_id)
    gov = _read_jsonl(gov_path)

    mem = status_manager.get_audit_trail(run_id) or []

    combined: List[Dict[str, Any]] = []
    if gov:
        combined.extend(gov)
    if mem:
        combined.extend(mem)

    if not combined:
        raise HTTPException(status_code=404, detail="No audit trail")

    return {
        "run_id": run_id,
        "governance_audit_path": gov_path.replace("\\", "/"),
        "audit_trail": combined,
        "count": len(combined),
    }


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("GCU_HOST", "127.0.0.1")
    port = int(os.environ.get("GCU_PORT", "8000"))

    uvicorn.run(
        "gcu_v1.api.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="debug",
    )
