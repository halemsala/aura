# ============================================================
# AURA QUANT-X - Free Ports Melhorado
# Versão: V25T15-CORRECAO
# Mais robusto que o original - mata por porta e por nome
# ============================================================

$ErrorActionPreference = "Continue"

Write-Host "[PORT] Liberando portas e processos AURA..." -ForegroundColor Yellow

$ports = @(8080, 8765, 8099, 8000, 5000)
foreach ($port in $ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $pid = $c.OwningProcess
            if ($pid -and $pid -gt 4) {
                try {
                    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                    Write-Host "[PORT] kill PID $pid ($($proc.ProcessName)) on :$port"
                } catch {
                    Write-Host "[PORT] kill PID $pid on :$port"
                }
            }
        }
    } catch {}
}

# Matar por nome de processo também
$names = @("Aura.QuantX.Desktop", "python", "node", "Aura*", "bridge", "engine")
foreach ($n in $names) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "[PROC] kill $($_.ProcessName) PID $($_.Id)"
        } catch {}
    }
}

Start-Sleep -Seconds 2
Write-Host "[PORT] done" -ForegroundColor Green
