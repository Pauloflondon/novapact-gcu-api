# ================================
# GCU STATUS CHECK (OFFICIAL)
# ================================
$HostAddr = "127.0.0.1"
$Port     = 8000
$BaseUrl  = "http://$HostAddr`:$Port"
$Health   = "$BaseUrl/health"

$OutputsRoot = "$PSScriptRoot\gcu_v1\outputs"

Write-Host "=== GCU STATUS CHECK ===" -ForegroundColor Cyan

# 1) Port / Process
$listenPid = $null
try {
    $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    if ($c) { $listenPid = $c.OwningProcess }
} catch {}

if ($listenPid) {
    Write-Host " Server LISTENING auf Port $Port (PID $listenPid)" -ForegroundColor Green
} else {
    Write-Host " Kein Server auf Port $Port" -ForegroundColor Red
}

# 2) Health
if ($listenPid) {
    try {
        $h = Invoke-RestMethod -Method Get -Uri $Health -TimeoutSec 2
        if ($h.status -eq "ok") {
            Write-Host " /health OK" -ForegroundColor Green
        } else {
            Write-Host " /health antwortet, Status != ok" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " ℹ /health nicht erreichbar (nicht kritisch)" -ForegroundColor DarkYellow
    }
}

# 3) Letzter echter Run
if (Test-Path $OutputsRoot) {
    $runs = Get-ChildItem $OutputsRoot -Directory |
        Where-Object { $_.Name -ne "_dev" } |
        Sort-Object LastWriteTime -Descending

    if ($runs.Count -gt 0) {
        $last = $runs[0]
        Write-Host " Letzter echter Run:" -ForegroundColor Green
        Write-Host "  Run-ID : $($last.Name)"
        Write-Host "  Zeit   : $($last.LastWriteTime)"

        $audit = Join-Path $last.FullName "audit.json"
        if (Test-Path $audit) {
            Write-Host "  Audit  : vorhanden" -ForegroundColor DarkGreen
        } else {
            Write-Host "  Audit  : FEHLT" -ForegroundColor Red
        }
    } else {
        Write-Host " Keine echten Runs gefunden" -ForegroundColor Yellow
    }
} else {
    Write-Host " Output-Verzeichnis fehlt" -ForegroundColor Red
}

Write-Host "=== STATUS CHECK ENDE ===" -ForegroundColor Cyan
