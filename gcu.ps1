$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONPATH = $Root

$serverFile = ".\gcu_v1\api\server.py"

# --- HARD PATCH: enforce enterprise status at return point ---
$patch = @"
# === NOVAPACT ENTERPRISE STATUS PATCH (AUTO) ===
def _np_enforce_status(resp: dict):
    if resp.get("hitl") and resp.get("status") == "ok":
        resp["status"] = "needs_review"
    return resp
"@

if (-not (Select-String $serverFile "_np_enforce_status" -Quiet)) {
    Add-Content $serverFile "`n$patch"
}

# replace final return of run endpoint (safe string replace)
(Get-Content $serverFile -Raw) `
  -replace "return result", "return _np_enforce_status(result)" |
  Set-Content $serverFile

Write-Host "[GCU] start server..."
$server = Start-Process python `
  -ArgumentList ".\gcu_v1\api\server.py" `
  -WorkingDirectory $Root `
  -PassThru

Start-Sleep -Seconds 3

Write-Host "[GCU] health..."
Invoke-RestMethod http://127.0.0.1:8000/health | Out-Host

Write-Host "[GCU] run..."
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/run `
  -ContentType "application/json" `
  -Body '{"capability":"gcu","payload":{"test":true},"hitl":"human"}' |
  Out-Host

Write-Host "[GCU] stop server..."
if (Get-Process -Id $server.Id -ErrorAction SilentlyContinue) {
    Stop-Process -Id $server.Id -Force
}
