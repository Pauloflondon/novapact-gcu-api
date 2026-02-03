from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from ._utils import write_json, utc_now_iso

def _event(events, typ: str, detail: str) -> None:
    events.append({"ts": utc_now_iso(), "type": typ, "detail": detail})

def finalize_audit(outputs_dir: Path, audit: Dict[str, Any], ctx: Dict[str, Any]) -> Path:
    path = outputs_dir / ctx["run_id"] / "audit.json"
    write_json(path, audit)
    _event(ctx["events"], "audit_written", f"path={path}")
    return path
