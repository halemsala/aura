# AURA/HERMES install v2 — execute no PowerShell do Windows (C:\aura)
# Rode fase a fase OU tudo de uma vez. Nunca mata Ollama :11434.
$ErrorActionPreference = "Continue"
$Root = "C:\aura"
$vpy = "$Root\engine\venv\Scripts\python.exe"
$date = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "$Root\install_log.md"

function Log($m) {
  Add-Content -Path $log -Value $m -Encoding UTF8
  Write-Host $m
}

# ========== FASE 0 ==========
Log "`n## FASE 0 — $(Get-Date -Format o) — running"
$ok0 = $true
foreach ($p in @(
  "$Root\hermes_v10\scripts\hermes_v10_chat_api.py",
  "$Root\engine\venv\Scripts\python.exe",
  "$Root\logs_supervisor"
)) {
  $t = Test-Path $p
  Log "Test-Path $p = $t"
  if (-not $t) { $ok0 = $false }
}
# aura_chat_agents optional soft
Log "Test-Path agents = $(Test-Path "$Root\scripts\aura_chat_agents.py")"
if (-not $ok0) { Log "FASE 0 FAIL — pilares em falta"; return }
Copy-Item "$Root\hermes_v10\scripts\hermes_v10_chat_api.py" "$Root\hermes_v10\scripts\hermes_v10_chat_api.py.bak_$date" -Force
Log "backup chat_api ok"
Log "FASE 0 — pass"

# ========== FASE 1 ==========
Log "`n## FASE 1 — modelo qwen2.5 — running"
if (Get-Command ollama -EA SilentlyContinue) {
  ollama pull qwen2.5:3b-instruct
  ollama list
} else { Log "AVISO: ollama nao no PATH" }
# env persistente + runtime
setx OLLAMA_MODEL "qwen2.5:3b-instruct" | Out-Null
setx AURA_OLLAMA_MODEL "qwen2.5:3b-instruct" | Out-Null
$env:OLLAMA_MODEL = "qwen2.5:3b-instruct"
$env:AURA_OLLAMA_MODEL = "qwen2.5:3b-instruct"
$envFile = "$Root\config\AURA_RUNTIME.env"
if (Test-Path $envFile) {
  $txt = Get-Content $envFile -Raw
  if ($txt -notmatch "OLLAMA_MODEL=") { Add-Content $envFile "OLLAMA_MODEL=qwen2.5:3b-instruct" }
  else { $txt = $txt -replace "OLLAMA_MODEL=.*","OLLAMA_MODEL=qwen2.5:3b-instruct"; Set-Content $envFile $txt -Encoding UTF8 }
}
Log "FASE 1 — pass (reinicio Hermes na fase 4)"

# ========== FASE 2 ==========
Log "`n## FASE 2 — catalogo — running"
New-Item -ItemType Directory -Force -Path "$Root\core","$Root\logs_supervisor" | Out-Null
# Se ja veio do ZIP, nao sobrescrever com menos entradas — so garantir existencia
if (-not (Test-Path "$Root\core\aura_error_catalog.py")) {
  Log "FAIL: falta core\aura_error_catalog.py — extraia o ZIP V37.3.38 COMPLETE atualizado"
  return
}
if (-not (Test-Path "$Root\core\__init__.py")) { Set-Content "$Root\core\__init__.py" "" }
& $vpy -c "import sys; sys.path.insert(0,r'$Root'); from core.aura_error_catalog import ErrorCatalog; c=ErrorCatalog(r'$Root'); print([h['code'] for h in c.match_text('o engine 8765 ta off e bridge off')])"
Log "FASE 2 — pass se imprimiu E-NET-004 e E-NET-003"

# ========== FASE 3 ==========
Log "`n## FASE 3 — mapa — running"
if (Test-Path "$Root\scripts\aura_generate_map.py") {
  & $vpy "$Root\scripts\aura_generate_map.py"
}
Log "mapa existe=$(Test-Path "$Root\AURA_MAPA_DO_SISTEMA.md")"
Log "FASE 3 — pass se mapa existe"

# ========== FASE 4 — restart Hermes com env ==========
Log "`n## FASE 4 — restart Hermes — running"
Get-NetTCPConnection -LocalPort 8777 -State Listen -EA SilentlyContinue | ForEach-Object {
  Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue
}
Start-Sleep 2
$hDir = "$Root\hermes_v10"
$logH = "$Root\logs_supervisor\hermes_v10.log"
$cmd = @"
Set-Location '$hDir'
`$env:AURA_ROOT='$Root'
`$env:PYTHONPATH='$Root;$hDir;$Root\core;$Root\scripts'
`$env:OLLAMA_MODEL='qwen2.5:3b-instruct'
`$env:AURA_OLLAMA_MODEL='qwen2.5:3b-instruct'
`$env:PAPER_TRADE='true'
`$env:EXECUTION_ALLOWED='false'
`$env:PYTHONUTF8='1'
& '$vpy' -u scripts\hermes_v10_chat_api.py 2>&1 | Tee-Object -FilePath '$logH' -Append
"@
Start-Process powershell -ArgumentList @("-NoExit","-Command",$cmd) -WindowStyle Minimized
Start-Sleep 10
try {
  $live = Invoke-RestMethod "http://127.0.0.1:8777/health/live" -TimeoutSec 5
  Log "health/live = $($live | ConvertTo-Json -Compress)"
} catch { Log "health/live FAIL: $_" }
try {
  $d = Invoke-RestMethod "http://127.0.0.1:8777/api/diagnose" -TimeoutSec 15
  Log "diagnose ok keys=$($d.PSObject.Properties.Name -join ',')"
} catch { Log "diagnose FAIL (pode faltar no build antigo): $_" }
function Chat($m) {
  $body = @{ message = $m } | ConvertTo-Json
  try {
    $r = Invoke-RestMethod "http://127.0.0.1:8777/api/chat" -Method Post -Body $body -ContentType "application/json; charset=utf-8" -TimeoutSec 90
    Log "CHAT [$m] model=$($r.model) reply=$($r.reply.Substring(0,[Math]::Min(200,$r.reply.Length)))"
  } catch { Log "CHAT FAIL $m : $_" }
}
Chat "status"
Chat "qual seu nome?"
Chat "o engine caiu de novo"
Log "FASE 4 — revisar testes acima"

# ========== FASE 5 ==========
Log "`n## FASE 5 — dataset — running"
$gen = @("$Root\scripts\aura_build_training_dataset.py","$Root\scripts\aura_build_dataset.py") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($gen) { & $vpy $gen }
Log "dataset=$(Test-Path "$Root\training\hermes_dataset.json")"
Log "FASE 5 — pass se dataset existe"

# ========== FASE 6 ==========
Log "`n## FASE 6 — receita Colab (manual)"
Log "1. Colab GPU T4 + Unsloth Qwen2.5 3B"
Log "2. Upload training\hermes_dataset.json"
Log "3. Export GGUF Q4_K_M -> C:\aura\training\hermes-aura-Q4_K_M.gguf"
Log "4. ollama create hermes-aura -f training\Modelfile.hermes-aura"
Log "5. setx OLLAMA_MODEL hermes-aura + restart Hermes"
Log "FASE 6 — pending (Colab)"

# ========== FASE 7 ==========
Log "`n## FASE 7 — promptfoo (opcional Node)"
if (Get-Command npx -EA SilentlyContinue) {
  if (Test-Path "$Root\evals\promptfoo.yaml") {
    Push-Location $Root; npx --yes promptfoo@latest eval -c evals/promptfoo.yaml; Pop-Location
  }
} else { Log "Node/npx ausente — promptfoo pendente" }
Log "FASE 7 — done/pending"

Log "`n## RELATORIO FINAL"
Log "| Fase | Status |"
Log "| 0 | ver acima |"
Log "| 1 | qwen2.5 |"
Log "| 2 | catalogo |"
Log "| 3 | mapa |"
Log "| 4 | chat |"
Log "| 5 | dataset |"
Log "| 6 | Colab manual |"
Log "| 7 | promptfoo |"
Log "Rollback: restaurar hermes_v10_chat_api.py.bak_* e setx OLLAMA_MODEL llama3.2:3b"
Log "NUNCA matar porta 11434"
Write-Host "`nLog: $log" -ForegroundColor Green
