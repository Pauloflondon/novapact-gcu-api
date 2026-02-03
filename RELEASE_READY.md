# NovaPact GCU — Audit Packet (v1)

This document summarizes governance, auditability, and evidence for NovaPact GCU (Governed Classification Unit).

---

## 1. System Purpose

NovaPact GCU is a governed classification service with:
- deterministic status transitions
- human oversight (HITL) gating
- audit artifacts per run
- metrics for monitoring outcomes

---

## 2. Governance Model (Implemented)

### Roles (conceptual)
- operator: executes /run
- auditor: reads audit artifacts (planned to be strict read-only)
- admin: governance override (planned; must be audited)

### Deterministic Status Machine
Statuses:
- ok
- needs_review
- approved
- rejected
- error

Key governance rule:
- low confidence triggers needs_review (HITL required)

Evidence:
- Status machine unit tests pass
- API test verifies needs_review behavior

---

## 3. Audit Artifacts (Implemented)

Per run, the system emits:
- run_id
- timestamp
- actor role + auth type (as provided by API key layer)
- input metadata (path/hash/size where applicable)
- classification + confidence
- explainability trace (if available)
- final status

Evidence:
- /debug/audit endpoints (if present)
- audit files written in outputs directory
- test_debug_audit_smoke passes

---

## 4. Human Oversight (HITL)

HITL trigger:
- confidence < threshold -> requires review

Behavior:
- final status becomes needs_review when review required

Evidence:
- test_run_needs_review_path_* passes
- server logs show final status needs_review

---

## 5. Observability / Monitoring

- Prometheus metrics endpoint exposed
- Counters track outcomes (ok / needs_review / etc.)

Evidence:
- /metrics reachable
- tests validate outcome counter increments

---

## 6. Data Handling / Persistence

Current storage:
- SQLite state store (PoC / dev / demo)
- Isolation for tests confirmed

Evidence:
- test_persistence suite passes (4 tests)

Planned:
- PostgreSQL adapter for production deployments

---

## 7. Controls Not Yet Implemented (Gap List)

1) Admin override endpoint with mandatory reason + dual-control option
2) Read-only audit export (JSON + PDF bundle)
3) Config integrity (signing/version pinning) for policies/manifests
4) Secrets management hardening for production (CI secrets, etc.)

---

## 8. Evidence Index (How to reproduce)

Local validation:
1) Install deps
2) Run:
   `pytest -v`
3) Confirm coverage gate passes (>=70%)

Artifacts:
- repo: contains workflow + tests + policy/manifest structure
- commits: include CI workflow and docs

---

## 9. Audit Verdict (v1)

✅ Suitable for:
- enterprise demo
- pilot deployment in controlled environment
- evaluation by compliance teams

⚠️ Not yet suitable for:
- regulated production deployment without override governance + audit export hardening