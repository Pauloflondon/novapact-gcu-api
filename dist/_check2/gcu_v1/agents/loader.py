import json
from pathlib import Path
from typing import Dict, Any

AGENTS_DIR = Path(__file__).resolve().parent

_CAPABILITY_MAP = {
    "doc_triage": "agent_01_doc_triage",
}

def load_agent_bundle(capability: str) -> Dict[str, Any]:
    if capability not in _CAPABILITY_MAP:
        raise ValueError(f"Unknown capability: {capability}")

    base = AGENTS_DIR / _CAPABILITY_MAP[capability]

    def read_json(p: Path) -> Dict[str, Any]:
        return json.loads(p.read_text(encoding="utf-8"))

    return {
        "capability": capability,
        "base": str(base),
        "manifest": read_json(base / "manifest.json"),
        "policy": read_json(base / "policy.json"),
        "keywords": read_json(base / "keywords.json"),
        "schema": read_json(base / "schema.json"),
    }
