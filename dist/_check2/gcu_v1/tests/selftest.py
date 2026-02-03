from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

# __file__ = .../gcu_v1/tests/selftest.py
# project_root = .../NOVAPACT_DATABASE
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PY = (PROJECT_ROOT / "gcu_v1" / "api" / "run.py").resolve()

def run(cmd: str):
    env = dict(os.environ)
    # Make sure project root is visible to Python for imports inside run.py
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    p = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        shell=True,
        env=env
    )
    return p.returncode, p.stdout, p.stderr

def main() -> int:
    assert RUN_PY.exists(), f"run.py not found at {RUN_PY}"

    # 1) Policy violation: extension not allowed (simulate .exe)
    tmp = PROJECT_ROOT / "gcu_v1" / "outputs" / "tmp.exe"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(b"dummy")

    code, out, err = run(f'"{sys.executable}" "{RUN_PY}" --input "{tmp}"')
    assert code != 0, "Policy violation should not be ok"

    # 2) Low confidence => human
    txt = PROJECT_ROOT / "gcu_v1" / "outputs" / "lowconf.txt"
    txt.write_text("random text with no strong signals", encoding="utf-8")

    code, out, err = run(f'"{sys.executable}" "{RUN_PY}" --input "{txt}"')
    assert code == 0, out + err
    j = json.loads(out)
    assert j["hitl"] == "human", "Expected HITL human for low confidence"

    # 3) Metadata write without approval => should still ok but log approval_missing
    txt2 = PROJECT_ROOT / "gcu_v1" / "outputs" / "risk.txt"
    txt2.write_text("GDPR confidential liability audit investigation", encoding="utf-8")

    code, out, err = run(f'"{sys.executable}" "{RUN_PY}" --input "{txt2}" --write-metadata')
    assert code == 0, out + err
    j2 = json.loads(out)
    audit_path = Path(j2["audit"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    types = [e["type"] for e in audit["events"]]
    assert "approval_missing" in types, "Expected approval_missing event when write-metadata without approval"

    print("SELFTEST OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
