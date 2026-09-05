# ============================================================
# AURA QUANT-X - Subir Engine com diagnostico (V25T15-FIX2)
# Rode quando a porta 8765 estiver livre / Engine OFF
# ============================================================
$ErrorActionPreference = "Continue"
$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
$VenvPy = Join-Path $Root "engine\venv\Scripts\python.exe"
$EnginePy = Join-Path $Root "engine\server.py"
$LogPath = Join-Path $Root "engine\runtime_engine.log"
$Port = 8765

function Log($m, $c = "White") { Write-Host $m -ForegroundColor $c }

Log ""
Log "======================================================" "Cyan"
Log " AURA - START ENGINE FORTE (porta $Port)" "Cyan"
Log "======================================================" "Cyan"
Log "ROOT = $Root"

# 1) Pre-checks
if (-not (Test-Path $VenvPy)) {
    Log "[ERRO] Venv ausente: $VenvPy" "Red"
    Log "Rode: powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1" "Yellow"
    exit 1
}
if (-not (Test-Path $EnginePy)) {
    Log "[ERRO] Falta engine\server.py" "Red"
    exit 1
}

# 2) Liberar porta 8765
Log "[1/5] Liberando porta $Port..." "Yellow"
try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess) {
            Log "  Kill PID $($c.OwningProcess)" "Yellow"
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}
try {
    $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split '\s+') | Where-Object { $_ -ne '' }
        $pidVal = $parts[-1]
        if ($pidVal -match '^\d+$') {
            Log "  Kill PID $pidVal (netstat)" "Yellow"
            Stop-Process -Id ([int]$pidVal) -Force -ErrorAction SilentlyContinue
        }
    }
} catch {}
Start-Sleep -Seconds 1
Log "  OK" "Green"

# 3) Testar imports criticos no venv
Log "[2/5] Testando imports no venv..." "Yellow"
$importTest = @"
import sys
sys.path.insert(0, r'$Root')
sys.path.insert(0, r'$Root\engine')
sys.path.insert(0, r'$Root\bridge')
errors = []
for mod in ['fastapi', 'uvicorn', 'pydantic', 'httpx']:
    try:
        __import__(mod)
        print('OK', mod)
    except Exception as e:
        errors.append(mod + ': ' + str(e))
        print('FAIL', mod, e)
try:
    import engine_core
    print('OK engine_core')
except Exception as e:
    print('WARN engine_core', type(e).__name__, e)
if errors:
    sys.exit(2)
sys.exit(0)
"@
$tmpPy = Join-Path $env:TEMP "aura_engine_precheck.py"
$importTest | Set-Content $tmpPy -Encoding UTF8
& $VenvPy $tmpPy
$importCode = $LASTEXITCODE
Remove-Item $tmpPy -ErrorAction SilentlyContinue
if ($importCode -eq 2) {
    Log "[ERRO] Dependencias basicas faltando no venv. Repara o venv." "Red"
    Log "powershell -ExecutionPolicy Bypass -File .\scripts\AURA_REPARAR_VENV_ENGINE.ps1" "Yellow"
    exit 1
}
Log "  Imports basicos OK" "Green"

# 4) Teste de import do server (captura traceback sem subir servidor)
Log "[3/5] Testando import de engine/server.py (pode demorar 10-30s)..." "Yellow"
$loadTest = @"
import sys, os, traceback
sys.path.insert(0, r'$Root')
sys.path.insert(0, r'$Root\engine')
sys.path.insert(0, r'$Root\bridge')
os.chdir(r'$Root\engine')
os.environ['PAPER_TRADE'] = 'true'
os.environ['EXECUTION_ALLOWED'] = 'false'
os.environ['GLM_ADVISORY_ONLY'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location('aura_engine_server', r'$EnginePy')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print('IMPORT_OK')
    if hasattr(mod, 'app'):
        print('APP_OK')
except Exception:
    traceback.print_exc()
    sys.exit(3)
"@
$tmpLoad = Join-Path $env:TEMP "aura_engine_load.py"
$loadTest | Set-Content $tmpLoad -Encoding UTF8
$loadOut = & $VenvPy $tmpLoad 2>&1 | Out-String
$loadCode = $LASTEXITCODE
Remove-Item $tmpLoad -ErrorAction SilentlyContinue
Write-Host $loadOut
if ($loadCode -ne 0) {
    Log ""
    Log "[ERRO] engine/server.py falhou no import. Traceback acima." "Red"
    Log "Cole esse traceback no chat para analise." "Yellow"
    $loadOut | Set-Content $LogPath -Encoding UTF8
    exit 1
}
Log "  Import do server OK" "Green"

# 5) Subir Engine via cmd e esperar health
Log "[4/5] Subindo Engine (background + log)..." "Yellow"
"" | Set-Content $LogPath -Encoding UTF8

$envBlock = "set PYTHONPATH=$Root;$Root\engine;$Root\bridge&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set GLM_ADVISORY_ONLY=1&& set CUDA_VISIBLE_DEVICES=0&& set PYTHONUNBUFFERED=1"
$cmdLine = "$envBlock&& `"$VenvPy`" -u `"$EnginePy`" --host 127.0.0.1 --port $Port >> `"$LogPath`" 2>&1"
Start-Process -FilePath "$env:ComSpec" -ArgumentList "/d","/c",$cmdLine -WindowStyle Minimized

Log "[5/5] Aguardando health http://127.0.0.1:$Port/api/health (ate 90s)..." "Yellow"

$ok = $false
for ($i = 1; $i -le 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 -ErrorAction Stop
        Log ""
        Log "  HEALTH OK em ~$($i*2)s  status=$($r.status)" "Green"
        $ok = $true
        break
    } catch {
        Write-Host -NoNewline "."
    }
}
Write-Host ""

if (-not $ok) {
    Log "[FALHA] Engine nao respondeu health em 90s." "Red"
    Log "--- ultimas linhas do log ($LogPath) ---" "Yellow"
    if (Test-Path $LogPath) {
        Get-Content $LogPath -Tail 50 -ErrorAction SilentlyContinue
    } else {
        Log "(log vazio / ausente)" "Red"
    }
    Log ""
    Log "Tente modo VISIVEL para ver o erro na tela:" "Yellow"
    Log "  cd $Root" "Cyan"
    Log "  .\AURA_SUBIR_ENGINE_VISIVEL.bat" "Cyan"
    Log "Ou cole o conteudo do runtime_engine.log no chat." "Yellow"
    exit 1
}

try {
    $ui = Invoke-RestMethod "http://127.0.0.1:$Port/api/ui/state" -TimeoutSec 3
    Log "  fixtureId    = $($ui.fixtureId)" "Cyan"
    Log "  jarvis_state = $($ui.jarvis_state)" "Cyan"
    Log "  paper_trade  = $($ui.paper_trade)" "Cyan"
} catch {}

Log ""
Log "======================================================" "Green"
Log " ENGINE ONLINE  http://127.0.0.1:$Port/api/health" "Green"
Log " Log = $LogPath" "Green"
Log " NAO feche a janela minimizada / processos python do Engine." "Yellow"
Log "======================================================" "Green"
exit 0
