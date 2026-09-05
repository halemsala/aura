#Requires -Version 5.1
# AURA V37.3.49 — extrai este pack para C:\aura e sobe Hermes
$ErrorActionPreference = 'Continue'
$Src = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Dst = 'C:\aura'

Write-Host "Fonte: $Src" -ForegroundColor Cyan
Write-Host "Destino: $Dst" -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $Src 'hermes_v10\core\hermes_llm_engine.py'))) {
  Write-Host "ERRO: rode este script de DENTRO da pasta extraida do ZIP (onde esta hermes_v10)." -ForegroundColor Red
  Write-Host "Ou: Expand-Archive do ZIP para C:\aura e depois rode de novo." -ForegroundColor Yellow
  exit 1
}

New-Item -ItemType Directory -Force -Path $Dst | Out-Null
Write-Host "A copiar ficheiros para $Dst (pode demorar)..."
# robocopy preserva e e mais robusto
$rc = Start-Process -FilePath 'robocopy.exe' -ArgumentList @(
  $Src, $Dst, '/E', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS',
  '/XD', '.git', '__pycache__', 'node_modules'
) -Wait -PassThru -NoNewWindow
# robocopy exit 0-7 = success
Write-Host "robocopy exit=$($rc.ExitCode)"

$must = @(
  'hermes_v10\core\hermes_llm_engine.py',
  'hermes_v10\scripts\hermes_v10_chat_api.py',
  'hermes_v10\AURA_RUN_HERMES.py'
)
$ok = $true
foreach ($m in $must) {
  $p = Join-Path $Dst $m
  if (Test-Path $p) { Write-Host "[OK] $m" -ForegroundColor Green }
  else { Write-Host "[FALTA] $m" -ForegroundColor Red; $ok = $false }
}
if (-not $ok) {
  Write-Host "Copia incompleta. Extraia o ZIP manualmente para C:\aura" -ForegroundColor Red
  exit 2
}

# Patch f-string via Python
$py = $null
foreach ($c in @(
  'C:\AURA_V25\engine\venv\Scripts\python.exe',
  'C:\aura\engine\venv\Scripts\python.exe'
)) { if (Test-Path $c) { $py = $c; break } }
if (-not $py) { $py = 'py' }

$patch = @'
from pathlib import Path
ROOT = Path(r"C:\aura")
OLD = "f\"{('Memoria:\\n'+str(memory_ctx)[:800]) if memory_ctx else ''}\\n\""
NEW = "(f\"Memoria:\\n{str(memory_ctx)[:800]}\\n\" if memory_ctx else \"\"),"
for rel in ["hermes_v10/scripts/hermes_v10_chat_api.py", "scripts/hermes_v10_chat_api.py"]:
    p = ROOT / rel
    if not p.is_file():
        print("missing", p); continue
    t = p.read_text(encoding="utf-8")
    if OLD in t:
        t2 = t.replace(OLD, NEW)
        compile(t2, str(p), "exec")
        p.write_text(t2, encoding="utf-8", newline="\n")
        print("PATCHED", p)
    else:
        compile(t, str(p), "exec")
        print("OK", p)
'@
$tmp = Join-Path $env:TEMP 'aura_patch49.py'
Set-Content -Path $tmp -Value $patch -Encoding UTF8
if ($py -eq 'py') { & py -3.11 $tmp } else { & $py $tmp }
Remove-Item $tmp -Force -EA SilentlyContinue

# Start Hermes
$env:AURA_ROOT = $Dst
$env:PYTHONPATH = "$Dst;$Dst\hermes_v10;$Dst\engine;$Dst\bridge"
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Force -Path (Join-Path $Dst 'logs_supervisor') | Out-Null
$log = Join-Path $Dst 'logs_supervisor\hermes_v10.log'
try {
  Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }
} catch {}

$work = Join-Path $Dst 'hermes_v10'
$entry = Join-Path $work 'AURA_RUN_HERMES.py'
if ($py -eq 'py') {
  Start-Process -FilePath 'py.exe' -WorkingDirectory $work -WindowStyle Minimized `
    -ArgumentList @('-3.11','-u', $entry) -RedirectStandardOutput $log -RedirectStandardError "$log.err"
} else {
  Start-Process -FilePath $py -WorkingDirectory $work -WindowStyle Minimized `
    -ArgumentList @('-u', $entry) -RedirectStandardOutput $log -RedirectStandardError "$log.err"
}

Write-Host "A aguardar health..." -ForegroundColor Cyan
Start-Sleep 10
try {
  $r = Invoke-WebRequest 'http://127.0.0.1:8777/health' -UseBasicParsing -TimeoutSec 5
  Write-Host "HERMES ON — $($r.StatusCode)" -ForegroundColor Green
  Write-Host $r.Content
} catch {
  Write-Host "Hermes OFF. Log:" -ForegroundColor Yellow
  if (Test-Path $log) { Get-Content $log -Tail 25 }
  if (Test-Path "$log.err") { Get-Content "$log.err" -Tail 15 }
}
