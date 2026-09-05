#Requires -Version 5.1
# AURA QUANT-X V37.3.48 — REPARAR + SUBIR HERMES (fix ModuleNotFound + SyntaxError f-string 3.11)
# paper_trade=true | execution_allowed=false
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Ok($m)   { Write-Host "[OK]    $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[WARN]  $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL]  $m" -ForegroundColor Red }
function Info($m) { Write-Host "[INFO]  $m" -ForegroundColor Cyan }

# --- 0. Raiz ---
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Root = $null
foreach ($c in @('C:\aura', 'C:\AURA_V25', (Split-Path -Parent $ScriptDir), $ScriptDir)) {
  if ((Test-Path (Join-Path $c 'hermes_v10\core\hermes_llm_engine.py')) -or
      (Test-Path (Join-Path $c 'engine\server.py'))) {
    $Root = $c
    break
  }
}
if (-not $Root) {
  Fail 'Nao encontrei C:\aura nem C:\AURA_V25 com hermes_v10. Extraia o ZIP em C:\aura'
  exit 1
}
Info "ROOT=$Root"
Set-Location $Root

$LogDir = Join-Path $Root 'logs_supervisor'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'hermes_v10.log'
$LogErr = Join-Path $LogDir 'hermes_v10.log.err'

# --- 1. Python 3.11 ---
$py = $null
$usePyLauncher = $false
$cands = @(
  (Join-Path $Root 'engine\venv\Scripts\python.exe'),
  'C:\AURA_V25\engine\venv\Scripts\python.exe',
  'C:\aura\engine\venv\Scripts\python.exe',
  (Join-Path $Root 'venv\Scripts\python.exe')
)
foreach ($c in $cands) {
  if (Test-Path $c) {
    try {
      $ver = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($ver -match '^3\.11') { $py = $c; break }
      if ($ver -match '^3\.(9|10|11)') { $py = $c }
    } catch {}
  }
}
if (-not $py) {
  try {
    $null = & py -3.11 -c "import sys; print(sys.version)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = 'py'; $usePyLauncher = $true }
  } catch {}
}
if (-not $py) {
  Fail 'Python 3.11 nao encontrado. Instale Python 3.11 (nao use 3.12+/3.14).'
  exit 2
}
if ($usePyLauncher) {
  $verFull = & py -3.11 -c "import sys; print(sys.version)" 2>$null
} else {
  $verFull = & $py -c "import sys; print(sys.version)" 2>$null
}
Ok "Python: $py  |  $verFull"

# --- 2. Estrutura ---
$Hv10 = Join-Path $Root 'hermes_v10'
$CoreEngine = Join-Path $Hv10 'core\hermes_llm_engine.py'
$ChatApi1 = Join-Path $Hv10 'scripts\hermes_v10_chat_api.py'
$ChatApi2 = Join-Path $Root 'scripts\hermes_v10_chat_api.py'
$RunHermes = Join-Path $Hv10 'AURA_RUN_HERMES.py'

if (-not (Test-Path $CoreEngine)) {
  Fail "FALTA $CoreEngine"
  Fail 'Extraia o ZIP COMPLETO (pasta hermes_v10 com core\) por cima de C:\aura'
  exit 3
}
Ok "core/hermes_llm_engine.py presente"

# Copia ficheiros corrigidos se estiverem ao lado deste script
$FixedChat = Join-Path $ScriptDir 'hermes_v10_chat_api.py'
$FixedRun  = Join-Path $ScriptDir 'AURA_RUN_HERMES.py'
# tambem procura na raiz C:\aura
if (-not (Test-Path $FixedChat)) {
  $alt = Join-Path $Root 'hermes_v10_chat_api.py'
  if (Test-Path $alt) { $FixedChat = $alt }
}
if (Test-Path $FixedChat) {
  New-Item -ItemType Directory -Force -Path (Join-Path $Hv10 'scripts') | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $Root 'scripts') | Out-Null
  Copy-Item -Force $FixedChat $ChatApi1
  Copy-Item -Force $FixedChat $ChatApi2
  Ok "chat_api corrigido copiado para hermes_v10\scripts e scripts\"
} else {
  Info "Ficheiro hermes_v10_chat_api.py corrigido nao ao lado do .ps1 — a fazer patch in-place se necessario"
}

if (Test-Path $FixedRun) {
  Copy-Item -Force $FixedRun $RunHermes
  Ok "AURA_RUN_HERMES.py atualizado"
} elseif (Test-Path (Join-Path $Root 'AURA_RUN_HERMES.py')) {
  Copy-Item -Force (Join-Path $Root 'AURA_RUN_HERMES.py') $RunHermes -ErrorAction SilentlyContinue
}

# --- 3. Patch in-place do f-string proibido no Python 3.11 ---
function Patch-ChatApi([string]$path) {
  # Versao in-place desativada: escaping de f-string Python dentro de PS e fragil.
  # Use sempre Patch-ChatApiViaPython (abaixo).
  return $false
}

# Patch mais simples e fiavel via Python (evita dor de cabeca de escaping no PS)
function Patch-ChatApiViaPython([string]$path, [string]$pythonExe, [bool]$launcher) {
  if (-not (Test-Path $path)) { return $false }
  $pyCode = @'
import sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    raw = f.read()
old = "f\"{('Memoria:\\n'+str(memory_ctx)[:800]) if memory_ctx else ''}\\n\""
new = "(f\"Memoria:\\n{str(memory_ctx)[:800]}\\n\" if memory_ctx else \"\"),"
if old not in raw:
    # ja ok
    print("SKIP")
    sys.exit(0)
raw2 = raw.replace(old, new)
with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(raw2)
print("PATCHED")
'@
  $tmpPy = Join-Path $env:TEMP 'aura_patch_chat_api.py'
  [System.IO.File]::WriteAllText($tmpPy, $pyCode, [System.Text.UTF8Encoding]::new($false))
  try {
    if ($launcher) {
      $out = & py -3.11 $tmpPy $path 2>&1 | Out-String
    } else {
      $out = & $pythonExe $tmpPy $path 2>&1 | Out-String
    }
    if ($out -match 'PATCHED') { return $true }
    return $false
  } finally {
    Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue
  }
}

$patchedAny = $false
foreach ($p in @($ChatApi1, $ChatApi2)) {
  if (Patch-ChatApiViaPython $p $py $usePyLauncher) {
    Ok "Patched f-string 3.11: $p"
    $patchedAny = $true
  }
}
if (-not $patchedAny) {
  # verificar se ja esta bom
  if (Test-Path $ChatApi1) {
    $t = [System.IO.File]::ReadAllText($ChatApi1)
    if ($t -match "Memoria:\\n'\+str\(memory_ctx\)") {
  # Padrao antigo (quebra no 3.11): f-string Memoria+str(memory_ctx) slice — ver needle abaixo
    } else {
      Ok "chat_api sem padrao f-string proibido (3.11)"
    }
  }
}

# --- 4. Syntax check ---
$checkTarget = if (Test-Path $ChatApi1) { $ChatApi1 } else { $ChatApi2 }
if (Test-Path $checkTarget) {
  $checkCode = "import ast; ast.parse(open(r'''$checkTarget''', encoding='utf-8').read()); print('SYNTAX_OK')"
  if ($usePyLauncher) {
    $syn = & py -3.11 -c $checkCode 2>&1 | Out-String
  } else {
    $syn = & $py -c $checkCode 2>&1 | Out-String
  }
  if ($syn -match 'SYNTAX_OK') {
    Ok "Syntax check OK: $checkTarget"
  } else {
    Fail "Syntax ainda falha em $checkTarget"
    Write-Host $syn
    Fail "Substitua pelo hermes_v10_chat_api.py do pack V37.3.48"
  }
}

# --- 5. Libertar 8777 ---
Info 'A libertar porta 8777...'
try {
  Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    Ok "PID $($_.OwningProcess) terminado"
  }
} catch {}
Start-Sleep -Seconds 1

# --- 6. Env ---
$env:AURA_ROOT = $Root
$env:PYTHONPATH = "$Root;$Root\hermes_v10;$Root\engine;$Root\bridge"
$env:PAPER_TRADE = 'true'
$env:EXECUTION_ALLOWED = 'false'
$env:AURA_EXECUTION_ALLOWED = '0'
$env:AURA_UNLOCK_LIVE = '0'
$env:GLM_ADVISORY_ONLY = 'true'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$workDir = $Hv10
$entryScript = $null
if (Test-Path $RunHermes) {
  $entryScript = $RunHermes
} elseif (Test-Path $ChatApi1) {
  $entryScript = $ChatApi1
} else {
  Fail 'Nenhum entrypoint Hermes encontrado'
  exit 4
}

Info "Entry: $entryScript"
Info "WorkDir: $workDir"
Info "PYTHONPATH=$($env:PYTHONPATH)"

# --- 7. Arranque ---
if (Test-Path $Log) { Move-Item -Force $Log "$Log.bak" -ErrorAction SilentlyContinue }

try {
  if ($usePyLauncher) {
    $proc = Start-Process -FilePath 'py.exe' -WorkingDirectory $workDir -WindowStyle Minimized `
      -ArgumentList @('-3.11', '-u', $entryScript) `
      -RedirectStandardOutput $Log -RedirectStandardError $LogErr -PassThru
  } else {
    $proc = Start-Process -FilePath $py -WorkingDirectory $workDir -WindowStyle Minimized `
      -ArgumentList @('-u', $entryScript) `
      -RedirectStandardOutput $Log -RedirectStandardError $LogErr -PassThru
  }
  Ok "Processo iniciado PID=$($proc.Id)"
} catch {
  Fail "Start-Process falhou: $_"
  $cmdLine = "set AURA_ROOT=$Root&& set PYTHONPATH=$($env:PYTHONPATH)&& set PAPER_TRADE=true&& set EXECUTION_ALLOWED=false&& set PYTHONUTF8=1&& "
  if ($usePyLauncher) {
    $cmdLine += "py -3.11 -u `"$entryScript`" >> `"$Log`" 2>&1"
  } else {
    $cmdLine += "`"$py`" -u `"$entryScript`" >> `"$Log`" 2>&1"
  }
  Start-Process -FilePath 'cmd.exe' -WorkingDirectory $workDir -WindowStyle Minimized -ArgumentList @('/c', $cmdLine)
  Ok 'Fallback cmd.exe usado'
}

# --- 8. Health ---
Info 'A aguardar health :8777 ...'
$ok = $false
for ($i = 1; $i -le 12; $i++) {
  Start-Sleep -Seconds 2
  try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8777/health' -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
      Ok "Hermes ON — HTTP $($r.StatusCode)  (tentativa $i)"
      try { Write-Host ($r.Content.Substring(0, [Math]::Min(200, $r.Content.Length))) } catch {}
      $ok = $true
      break
    }
  } catch {
    Write-Host "  ... ainda a subir ($i/12)"
  }
}

if (-not $ok) {
  Fail 'Hermes OFF apos espera'
  Write-Host '--- tail log ---' -ForegroundColor Yellow
  if (Test-Path $Log) { Get-Content $Log -Tail 30 -ErrorAction SilentlyContinue }
  if (Test-Path $LogErr) {
    Write-Host '--- tail log.err ---' -ForegroundColor Yellow
    Get-Content $LogErr -Tail 30 -ErrorAction SilentlyContinue
  }
  Write-Host ''
  Write-Host 'Checklist:' -ForegroundColor Cyan
  Write-Host '  1. Python 3.11 (nao 3.12/3.14)'
  Write-Host '  2. hermes_v10\core\hermes_llm_engine.py existe'
  Write-Host '  3. Substitua scripts\hermes_v10_chat_api.py pelo ficheiro do pack V37.3.48'
  Write-Host '  4. Rode de novo este script'
  exit 5
}

Write-Host ''
Ok 'HERMES V10 pronto em http://127.0.0.1:8777'
Ok 'Invariantes: PAPER_TRADE=true EXECUTION_ALLOWED=false'
Write-Host "Log: $Log"
