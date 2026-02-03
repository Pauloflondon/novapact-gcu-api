from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import Status Machine
from gcu_v1.status_machine import (
    NovaPactStatusManager,
    ClassificationResult,
    SystemStatus,
    StatusTransitionError,
    AdminOverrideError
)

# ==================== FASTAPI APP ====================

app = FastAPI(title="NovaPact GCU API", version="1.0.0")

# Initialize Status Manager (for production, replace with Redis/Database storage)
status_manager = NovaPactStatusManager()


# ==================== REQUEST MODELS ====================

class RunRequest(BaseModel):
    capability: str
    payload: Dict[str, Any]
    actor: str = "system"      # Default: system actor
    role: str = "auto"         # Default: automatic processing
    auth_type: str = "api_key" # Default: API key authentication


class ReviewRequest(BaseModel):
    action: str                # "approve" or "reject"
    actor: str
    role: str
    auth_type: str
    reason: Optional[str] = None


class AdminOverrideRequest(BaseModel):
    target_status: str  # "approved" or "rejected" - als String
    actor: str
    role: str
    auth_type: str
    reason: str


# ==================== ENDPOINTS ====================

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    """
    Main execution endpoint with integrated Status Machine.
    Replaces the old auto-patch with proper state management.
    """
    # Lazy import to avoid import-time side effects
    try:
        from gcu_v1.api.run import run_capability
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="run_capability() not found. Please ensure gcu_v1.api.run is properly configured."
        )

    try:
        # 1. Execute pipeline (existing logic)
        pipeline_result = run_capability(
            capability=req.capability,
            payload=req.payload
        )
        
        # Extract pipeline status
        pipeline_status = pipeline_result.get("status", "error")
        hitl = pipeline_result.get("hitl", "auto")
        
        # 2. Skip status machine for non-"ok" pipeline results
        if pipeline_status not in ["ok", "needs_review"]:
            return pipeline_result
        
        # 3. Determine if HITL is required based on pipeline result
        # Note: The pipeline already decides hitl in apply_threshold
        # We need to check if approval was provided
        approval_provided = pipeline_result.get("approval_provided", False)
        
        # 4. Create classification result for status machine
        classification_result = ClassificationResult(
            confidence=0.0,  # Not used for status resolution, but required
            hitl_required=(hitl == "human"),
            approval=approval_provided,
            admin_override=False,
            error_occurred=False
        )
        
        # 5. Process with status machine (Single Source of Truth)
        # Use run_id from pipeline as request_id
        request_id = pipeline_result.get("run_id", "unknown")
        
        status = status_manager.process_classification(
            request_id=request_id,
            classification_result=classification_result,
            actor=req.actor,
            role=req.role,
            auth_type=req.auth_type
        )
        
        # 6. Update result with correct status
        pipeline_result["status"] = str(status)
        
        # 7. Add needs_review flag for backward compatibility
        pipeline_result["needs_review"] = (status == SystemStatus.NEEDS_REVIEW)
        
        return pipeline_result

    except Exception as e:
        # Log error with context
        import logging
        logging.error(f"Run endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review/{run_id}")
def review(run_id: str, review_req: ReviewRequest) -> Dict[str, Any]:
    """
    Manual review endpoint for HITL actions.
    """
    try:
        # Validate action
        if review_req.action not in ["approve", "reject"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action: {review_req.action}. Must be 'approve' or 'reject'."
            )
        
        # Process manual review
        new_status = status_manager.manual_review_action(
            request_id=run_id,
            action=review_req.action,
            actor=review_req.actor,
            role=review_req.role,
            auth_type=review_req.auth_type,
            reason=review_req.reason
        )
        
        return {
            "status": str(new_status),
            "run_id": run_id,
            "action": review_req.action,
            "actor": review_req.actor
        }
        
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Request {run_id} not found")
    except StatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Review endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/override/{run_id}")
def admin_override(run_id: str, override_req: AdminOverrideRequest) -> Dict[str, Any]:
    """
    Admin override endpoint with strict role enforcement.
    """
    try:
        # Convert string to SystemStatus enum
        try:
            target_status = SystemStatus(override_req.target_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target_status: {override_req.target_status}. Must be 'approved' or 'rejected'."
            )
        
        # Process admin override
        new_status = status_manager.admin_override(
            request_id=run_id,
            target_status=target_status,
            actor=override_req.actor,
            role=override_req.role,
            auth_type=override_req.auth_type,
            reason=override_req.reason
        )
        
        return {
            "status": str(new_status),
            "run_id": run_id,
            "actor": override_req.actor,
            "role": override_req.role,
            "admin_override": True
        }
        
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Request {run_id} not found")
    except (StatusTransitionError, AdminOverrideError) as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Admin override error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SERVER STARTUP ====================

if __name__ == "__main__":
    import uvicorn
    
    # Configure logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Start server
    host = os.environ.get("GCU_HOST", "127.0.0.1")
    port = int(os.environ.get("GCU_PORT", "8000"))
    
    uvicorn.run(
        "gcu_v1.api.server:app",
        host=host,
        port=port,
        reload=False,
        log_config=None
    )