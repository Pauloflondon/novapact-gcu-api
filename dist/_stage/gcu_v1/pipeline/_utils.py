from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> Tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            h.update(chunk)
    return h.hexdigest(), total


def read_text_best_effort(path: Path, max_chars: int = 200_000) -> str:
    # Simple best-effort reader without OCR.
    # For PDF/DOCX you can later add extractors; for now treat as bytes->latin1 fallback.
    try:
        data = path.read_text(encoding='utf-8-sig', errors="replace")
    except Exception:
        data = path.read_bytes().decode("latin-1", errors="replace")
    return data[:max_chars]


def load_json(path: Path) -> Dict[str, Any]:
    # Robust against UTF-8 BOM written by some editors/tools
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    """
    Atomic JSON write: write into temp file then replace target.
    Prevents partial/corrupt artefacts (audit, metadata, traces) on crashes.
    """
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8-sig')
    tmp.replace(path)


def env_truthy(name: str) -> bool:
    v = os.getenv(name, "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


@dataclass
class GovernanceDecision:
    policy_ok: bool
    blocked_reason: str | None
    hitl: str  # "auto" or "human"
    threshold: float
    approval_required: bool
    approval_provided: bool
    approval_id: str | None
    kill_enabled: bool
    kill_triggered: bool


def new_run_id() -> str:
    return uuid.uuid4().hex
