from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
from ._utils import sha256_file, utc_now_iso

def intake(input_path: Path) -> Dict[str, Any]:
    sha, size = sha256_file(input_path)
    return {
        "ts": utc_now_iso(),
        "input": {
            "path": str(input_path),
            "ext": input_path.suffix.lower().lstrip("."),
            "sha256": sha,
            "bytes": size
        }
    }
