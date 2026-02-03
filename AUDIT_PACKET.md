# NovaPact GCU — Audit & Compliance Packet (v1)

Repository: novapact-gcu-api  
Branch: main  
System: NovaPact GCU (Governed Classification Unit)  
Prepared for: Enterprise Pilot / Regulatory Review  
Owner: Pauloflondon

---

## 1. System Purpose & Context

NovaPact GCU is a **governed decision-support system** for classification tasks.

It is explicitly designed to:
- Support human decision-making
- Enforce deterministic governance rules
- Prevent uncontrolled autonomous decisions

The system **does not** perform fully autonomous high-risk decisions.

---

## 2. AI Act Risk Classification (Self-Assessment)

| Category | Assessment |
|-------|-----------|
| Intended use | Decision support |
| Autonomous decision-making | ❌ No |
| Human-in-the-loop | ✅ Mandatory |
| High-risk sector deployment | ⚠️ Possible (context-dependent) |
| Final authority | Human |

**Preliminary classification:**  
➡️ **Limited Risk / High-Risk–Adjacent (controlled)**

---

## 3. Governance & Control Measures

### 3.1 Deterministic Status Machine
- Explicit states: `ok`, `needs_review`, `approved`, `rejected`, `error`
- No implicit or hidden transitions
- All transitions are code-defined

### 3.2 Human-in-the-Loop (HITL)
- Low-confidence outcomes trigger mandatory human review
- System cannot self-approve in HITL-required cases

### 3.3 Audit Artifacts
Each run produces:
- Unique `run_id`
- Actor role (operator / admin / auditor)
- Timestamp
- Classification outcome
- Confidence value
- Decision trace

Artifacts are stored and reproducible.

---

## 4. Transparency & Explainability

Implemented:
- Confidence score per classification
- Explicit outcome status
- Traceable execution path

Planned:
- Structured explainability payload
- Exportable audit bundles (JSON / PDF)

---

## 5. Data Handling & Persistence

- Local SQLite database
- No external data sharing
- No training on customer data
- Stateless inference logic

⚠️ Production-grade DB planned (PostgreSQL adapter).

---

## 6. Security Model (Current State)

Implemented:
- Role separation (operator / admin / auditor)
- API access control (key-based)
- Read-only audit access planned

Not yet implemented:
- Admin override endpoint with mandatory justification
- Cryptographic audit signing

---

## 7. Known Gaps & Mitigations

| Gap | Mitigation |
|---|---|
| No override governance | Planned (v1.1) |
| No audit export | Planned |
| CI runner unavailable | External billing constraint |
| SQLite only | Acceptable for pilot |

---

## 8. Audit Verdict (Internal)

**Status:**  
✅ Suitable for **Enterprise Demo / Pilot**  
⚠️ Not yet suitable for fully regulated production deployment

Conditions for production:
- Override governance
- Audit export
- Persistent enterprise DB

---

## 9. Next Compliance Steps

1. Override governance implementation  
2. Auditor export endpoint  
3. Evidence bundle automation  
4. Policy signature & validation (optional)