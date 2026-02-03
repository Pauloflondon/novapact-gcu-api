from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
from ._utils import utc_now_iso, write_json

def _event(events, typ: str, detail: str) -> None:
    events.append({"ts": utc_now_iso(), "type": typ, "detail": detail})

def metadata_write(outputs_dir: Path, ctx: Dict[str, Any], metadata: Dict[str, Any], approval_id: str | None) -> Dict[str, Any]:
    # Only write metadata artefact to outputs (never touch input file).
    out = {
        "run_id": ctx["run_id"],
        "approval_id": approval_id,
        "metadata": metadata,
        "ts": utc_now_iso()
    }
    path = outputs_dir / ctx["run_id"] / "metadata.json"
    write_json(path, out)
    _event(ctx["events"], "metadata_written", f"path={path}")
    return out
