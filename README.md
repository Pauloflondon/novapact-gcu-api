# novapact-gcu-api

**Governance & Control Unit (GCU)**  
Deterministische Ausführungsschicht für KI-/Agenten-Runs mit Audit-Trail, Policy-Enforcement und Health-Monitoring.

---

## Überblick

Minimalistische, kontrollierte API für KI-/Agenten-Runs mit:
- deterministischer Pipeline
- Governance & Policy Enforcement
- vollständigem Audit-Trail
- reproduzierbarem PowerShell-Workflow

---

## Quickstart

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\gcu.ps1 start
.\check_gcu_status.ps1
```

---

## API

### Health
GET /health

Antwort:
```json
{ "status": "ok" }
```

### Run
POST /run

Beispiel:
```json
{
  "capability": "demo",
  "payload": { "text": "hello world" }
}
```

---

## Outputs & Audit

- Outputs: `gcu_v1/outputs/<RUN_ID>/`
- Audit (append-only): `gcu_v1/audit/audit.json`

---

## Governance

- Confidence Threshold: **0.85**
- Unter Threshold  Human-in-the-Loop
- Kill-Switch:
```powershell
$env:GCU_KILL=1
```

---

## Status

**Repo-ready / stabil**

---

## Lizenz

Proprietary  All rights reserved
