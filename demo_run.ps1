param(
  [string]$HostUrl = "http://127.0.0.1:8000",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Say($msg, $color="Gray") { Write-Host $msg -ForegroundColor $color }

Say "=== NovaPact GCU Demo Run (v2) ===" "Cyan"
$repoRoot = (Get-Location).Path
Say ("Repo: " + $repoRoot) "DarkGray"

if (-not (Test-Path ".\gcu.ps1")) {
  Say "FAIL: gcu.ps1 not found in current directory." "Red"
  exit 1
}

Say "1) Execute lifecycle demo via gcu.ps1 start (this will STARTHEALTHRUNSTOP)..." "Yellow"
$startOut = & powershell -NoProfile -ExecutionPolicy Bypass -File ".\gcu.ps1" "start" 2>&1
$exit = $LASTEXITCODE

if ($startOut) {
  Say "gcu.ps1 output:" "DarkGray"
  $startOut | ForEach-Object { Write-Host $_ }
}

if ($exit -ne 0) {
  Say "FAIL: gcu.ps1 returned exit code $exit" "Red"
  if (Test-Path ".\check_gcu_status.ps1") { .\check_gcu_status.ps1 }
  exit $exit
}

Say "2) Collect artefacts (latest output + audit)..." "Yellow"

# Prefer _dev output file if present
$devDir = Join-Path $repoRoot "gcu_v1\outputs\_dev"
$devLatest = $null
if (Test-Path $devDir) {
  $devLatest = Get-ChildItem $devDir -File -Filter "run_*.json" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

# Also locate latest real run dir
$outRoot = Join-Path $repoRoot "gcu_v1\outputs"
$realLatestDir = $null
if (Test-Path $outRoot) {
  $dirs = Get-ChildItem $outRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne "_dev" } |
    Sort-Object LastWriteTime -Descending
  if ($dirs -and $dirs.Count -gt 0) { $realLatestDir = $dirs[0].FullName }
}

if ($devLatest) {
  Say ("Latest _dev run file: " + $devLatest.FullName) "Cyan"
  try {
    $j = Get-Content $devLatest.FullName -Raw | ConvertFrom-Json
    if ($j.run_id) { Say ("Run-ID: " + $j.run_id) "Green" }
    if ($j.status) { Say ("Status: " + $j.status) "Green" }
    if ($j.hitl)   { Say ("HITL : " + $j.hitl) "Green" }
    if ($j.audit)  { Say ("Audit: " + $j.audit) "Cyan" }
  } catch {
    Say "WARN: Could not parse _dev run json." "Yellow"
  }
} else {
  Say "WARN: No _dev run file found under gcu_v1\outputs\_dev." "Yellow"
}

if ($realLatestDir) {
  Say ("Latest real run dir: " + $realLatestDir) "Cyan"
  $auditJson = Join-Path $realLatestDir "audit.json"
  if (Test-Path $auditJson) {
    try {
      $a = Get-Content $auditJson -Raw | ConvertFrom-Json
      if ($a.status) { Say ("Audit status: " + $a.status) "Green" }
    } catch {
      Say "Audit exists (parse failed)." "Yellow"
    }
  } else {
    Say "No audit.json found in latest run dir (ok if audit path differs)." "Yellow"
  }
} else {
  Say "WARN: No real run dir found (excluding _dev)." "Yellow"
}

Say "3) Status snapshot (server likely DOWN by design after gcu.ps1)..." "Yellow"
if (Test-Path ".\check_gcu_status.ps1") { .\check_gcu_status.ps1 } else { Say "check_gcu_status.ps1 not found." "Yellow" }

Say "=== Demo complete ===" "Cyan"
