[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [switch]$NoRestartHermes
)

$ErrorActionPreference = "Continue"
if ([string]::IsNullOrWhiteSpace($Root)) { $Root = $PSScriptRoot }
$Root = ([string]$Root).Trim().Trim('"').Trim("'").Trim()
if ($Root.Length -gt 3) { $Root = $Root.TrimEnd('\') }
try {
    $resolvedRoot = Resolve-Path -LiteralPath $Root -ErrorAction Stop
    $Root = $resolvedRoot.Path
} catch {
    Write-Host ("[ERRO] Raiz invalida: {0}" -f $Root)
    Write-Host "Use o BAT dentro da pasta que contem engine, bridge e hermes_v10."
    exit 2
}
$LogDir = Join-Path $Root "logs_supervisor"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $Root ("backups\aura_max_" + $Stamp)
$PatchLog = Join-Path $LogDir "aura_max_fix.log"
$BootReport = Join-Path $LogDir "AURA_MAX_BOOT_LATEST.json"
$NoBrowser = $true
$Model = "qwen3:8b"

function Write-Log {
    param([string]$Message, [ValidateSet("INFO","WARN","ERROR")] [string]$Level = "INFO")
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -LiteralPath $PatchLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Set-ProcessEnv {
    param([string]$Name, [string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Persist-SafeEnv {
    param([string]$Name, [string]$Value)
    try {
        & setx $Name $Value | Out-Null
    } catch {
        Write-Log ("Nao foi possivel persistir {0}: {1}" -f $Name, $_.Exception.Message) "WARN"
    }
}

function Backup-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $relative = $Path.Substring($Root.Length).TrimStart('\')
    $dest = Join-Path $BackupDir $relative
    $parent = Split-Path -Parent $dest
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Path -Destination $dest -Force
}

function Patch-TextOnce {
    param(
        [string]$Path,
        [string]$Needle,
        [string]$Replacement,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Log ("Patch skip {0}: ficheiro ausente" -f $Label) "WARN"
        return $false
    }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $needleToUse = $Needle
    $replacementToUse = $Replacement
    if (-not $text.Contains($Replacement) -and $text.Contains($Replacement.Replace("`n", [Environment]::NewLine))) {
        Write-Log ("Patch ja aplicado: {0}" -f $Label)
        return $true
    }
    if (-not $text.Contains($needleToUse) -and $Needle.Contains("`n")) {
        $candidate = $Needle.Replace("`n", [Environment]::NewLine)
        if ($text.Contains($candidate)) {
            $needleToUse = $candidate
            $replacementToUse = $Replacement.Replace("`n", [Environment]::NewLine)
        }
    }
    if (-not $text.Contains($needleToUse)) {
        Write-Log ("Patch skip {0}: alvo nao encontrado" -f $Label) "WARN"
        return $false
    }
    Backup-File $Path
    $text = $text.Replace($needleToUse, $replacementToUse)
    Set-Content -LiteralPath $Path -Value $text -Encoding UTF8 -NoNewline
    Write-Log ("Patch aplicado: {0}" -f $Label)
    return $true
}

function Patch-RegexOnce {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Replacement,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Log ("Regex patch skip {0}: ficheiro ausente" -f $Label) "WARN"
        return $false
    }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ($text -match [regex]::Escape($Replacement)) {
        Write-Log ("Regex patch ja aplicado: {0}" -f $Label)
        return $true
    }
    if (-not [regex]::IsMatch($text, $Pattern)) {
        Write-Log ("Regex patch skip {0}: alvo nao encontrado" -f $Label) "WARN"
        return $false
    }
    Backup-File $Path
    $text = [regex]::Replace($text, $Pattern, $Replacement, 1)
    Set-Content -LiteralPath $Path -Value $text -Encoding UTF8 -NoNewline
    Write-Log ("Regex patch aplicado: {0}" -f $Label)
    return $true
}

function Test-Port {
    param([int]$Port)
    try {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    } catch {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $task = $client.ConnectAsync("127.0.0.1", $Port)
            $ok = $task.Wait(400)
            $client.Close()
            return $ok -and ($task.Status -eq 'RanToCompletion')
        } catch { return $false }
    }
}

function Wait-Port {
    param([int]$Port, [int]$Seconds = 30)
    for ($i = 0; $i -lt ($Seconds * 2); $i++) {
        if (Test-Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-KnownHermes {
    $connections = @(Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        $ownerPid = [int]$connection.OwningProcess
        if ($ownerPid -le 4) { continue }
        $process = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ownerPid) -ErrorAction SilentlyContinue
        $commandLine = [string]$process.CommandLine
        if ($commandLine -match "(?i)(hermes_v10_chat_api\\.py|AURA_RUN_HERMES\\.py)") {
            Write-Log ("A parar Hermes conhecido PID={0} para carregar o novo modelo" -f $ownerPid)
            Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        } else {
            Write-Log ("Porta 8777 pertence a processo nao reconhecido; nao foi terminado" ) "WARN"
        }
    }
}

function Start-AuraService {
    param(
        [string]$Name,
        [string]$Script,
        [string[]]$Arguments,
        [int]$Port,
        [string]$WorkDir = $Root
    )
    if (-not (Test-Path -LiteralPath $Script)) {
        Write-Log ("{0}: script ausente: {1}" -f $Name, $Script) "WARN"
        return $false
    }
    if (Test-Port $Port) {
        Write-Log ("{0}: ja activo em :{1}; sem duplicar" -f $Name, $Port)
        return $true
    }
    $safe = ($Name -replace '[^A-Za-z0-9_-]', '_').ToLowerInvariant()
    $stdout = Join-Path $LogDir ($safe + ".out.log")
    $stderr = Join-Path $LogDir ($safe + ".err.log")
    $argumentList = @("-u", ('"' + $Script + '"')) + @($Arguments)
    try {
        $proc = Start-Process -FilePath $Python -ArgumentList $argumentList -WorkingDirectory $WorkDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        Write-Log ("{0}: iniciado PID={1}, porta :{2}" -f $Name, $proc.Id, $Port)
        if (Wait-Port $Port 30) {
            Write-Log ("{0}: ONLINE :{1}" -f $Name, $Port)
            return $true
        }
        Write-Log ("{0}: nao abriu :{1}; consultar {2}" -f $Name, $Port, $stderr) "WARN"
        return $false
    } catch {
        Write-Log ("{0}: falha ao iniciar: {1}" -f $Name, $_.Exception.Message) "ERROR"
        return $false
    }
}

Write-Log "AURA MAX fix iniciado; nenhum navegador sera aberto"
Write-Log ("ROOT={0}" -f $Root)

$envValues = [ordered]@{
    AURA_ROOT = $Root
    PYTHONUTF8 = "1"
    PYTHONUNBUFFERED = "1"
    PYTHONPATH = ($Root + ";" + (Join-Path $Root "engine") + ";" + (Join-Path $Root "bridge") + ";" + (Join-Path $Root "hermes_v10"))
    PAPER_TRADE = "true"
    EXECUTION_ALLOWED = "false"
    AURA_EXECUTION_ALLOWED = "0"
    AURA_UNLOCK_LIVE = "0"
    GLM_ADVISORY_ONLY = "true"
    AURA_GLM_ENABLED = "0"
    HERMES_ALLOW_CLOUD = "0"
    AURA_SAFE_EXECUTOR = "1"
    AURA_LLM_BACKEND = "ollama"
    OLLAMA_MODEL = $Model
    AURA_OLLAMA_MODEL = $Model
    AURA_JARVIS_MODEL = $Model
    CORNERAI_CHAT_MODEL = $Model
    OLLAMA_KEEP_ALIVE = "20m"
    OLLAMA_NUM_GPU = "99"
    AURA_OLLAMA_NUM_CTX = "4096"
    AURA_OLLAMA_NUM_PREDICT = "1024"
    AURA_OLLAMA_TEMPERATURE = "0.20"
    AURA_NO_BROWSER = "1"
    AURA_AUTO_OPEN_UI = "0"
    AURA_TECHNICAL_MODE = "1"
}
foreach ($item in $envValues.GetEnumerator()) {
    Set-ProcessEnv $item.Key ([string]$item.Value)
}
Persist-SafeEnv "AURA_NO_BROWSER" "1"
Persist-SafeEnv "AURA_AUTO_OPEN_UI" "0"
Persist-SafeEnv "AURA_OLLAMA_MODEL" $Model
Persist-SafeEnv "OLLAMA_MODEL" $Model
Persist-SafeEnv "PAPER_TRADE" "true"
Persist-SafeEnv "EXECUTION_ALLOWED" "false"

$pythonCandidates = @(
    (Join-Path $Root "engine\venv\Scripts\python.exe"),
    (Join-Path $Root "venv\Scripts\python.exe")
)
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pythonCommand) { $pythonCandidates += $pythonCommand.Source }
$pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyCommand) { $pythonCandidates += $pyCommand.Source }
$Python = $pythonCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Python) {
    Write-Log "Python 3 nao encontrado; corrija o ambiente e execute novamente" "ERROR"
    exit 2
}
Write-Log ("Python={0}" -f $Python)

$programmer = Join-Path $Root "scripts\aura_programmer_agent.py"
$llmEngine = Join-Path $Root "hermes_v10\core\hermes_llm_engine.py"
$chatApi = Join-Path $Root "hermes_v10\scripts\hermes_v10_chat_api.py"
$modelRouter = Join-Path $Root "hermes_v10\core\hermes_model_router.py"
$ultraBat = Join-Path $Root "AURA_HERMES_V10_ULTRA.bat"

$nl = [char]10
$browserNeedle = '    if not path.exists():' + $nl + '        return "relatorio ausente"'
$browserReplacement = $browserNeedle + $nl + '    if os.getenv("AURA_NO_BROWSER", "1").strip().lower() in ("1", "true", "yes", "on"):' + $nl + '        return "guardado sem abrir: " + str(path)'
Patch-TextOnce $programmer $browserNeedle $browserReplacement "bloqueio de abertura automatica do relatorio"

$engineNeedle = '            "options": {"temperature": 0.35, "num_predict": 512, "num_ctx": 4096},'
$engineReplacement = '            "options": {"temperature": float(os.getenv("AURA_OLLAMA_TEMPERATURE", "0.20")), "num_predict": int(os.getenv("AURA_OLLAMA_NUM_PREDICT", "1024")), "num_ctx": int(os.getenv("AURA_OLLAMA_NUM_CTX", "4096")), "num_gpu": int(os.getenv("OLLAMA_NUM_GPU", "99"))},'
Patch-TextOnce $llmEngine $engineNeedle $engineReplacement "parametros Ollama para 6 GB VRAM"
$engineModelNeedle = '        ollama_model: str = "llama3.2:3b",'
$engineModelReplacement = '        ollama_model: str = "qwen3:8b",'
Patch-TextOnce $llmEngine $engineModelNeedle $engineModelReplacement "modelo default do motor Hermes"

$chatModelNeedle = ' or "qwen2.5:3b-instruct"'
$chatModelReplacement = ' or "qwen3:8b"'
Patch-TextOnce $chatApi $chatModelNeedle $chatModelReplacement "fallback do chat para Qwen3"
if (Test-Path -LiteralPath $chatApi) {
    $chatText = Get-Content -LiteralPath $chatApi -Raw -Encoding UTF8
    $oldModelLiteral = '"qwen2.5:3b-instruct"'
    if ($chatText.Contains($oldModelLiteral)) {
        Backup-File $chatApi
        $chatText = $chatText.Replace($oldModelLiteral, '"qwen3:8b"')
        Set-Content -LiteralPath $chatApi -Value $chatText -Encoding UTF8 -NoNewline
        Write-Log "Referencias restantes do chat actualizadas para Qwen3"
    }
}

$routerNeedle = 'REGISTRY: Dict[str, ModelSpec] = {'
$routerReplacement = 'REGISTRY: Dict[str, ModelSpec] = {' + $nl + '    "qwen3:8b": ModelSpec("qwen3:8b", "ollama", 0.0, 1100, 32768, True, 0.85),'
Patch-TextOnce $modelRouter $routerNeedle $routerReplacement "catalogo de modelos com Qwen3"

if (Test-Path -LiteralPath $ultraBat) {
    $ultraText = Get-Content -LiteralPath $ultraBat -Raw -Encoding UTF8
    $oldUiLines = @(
        ('start "" ' + [string]::Concat('http://', '127.0.0.1:8777/chat')),
        ('start "" ' + [string]::Concat('http://', '127.0.0.1:8778/'))
    )
    $changed = $false
    foreach ($line in $oldUiLines) {
        $guarded = 'if /I not "!NO_UI!"=="1" ' + $line
        if (-not $ultraText.Contains($guarded) -and $ultraText.Contains($line)) {
            $ultraText = $ultraText.Replace($line, $guarded)
            $changed = $true
        }
    }
    $modeNeedle = 'if not defined MODE set "MODE=bg"'
    $modeReplacement = $modeNeedle + $nl + 'set "NO_UI=0"' + $nl + 'if /I "%AURA_NO_BROWSER%"=="1" set "NO_UI=1"'
    if (-not $ultraText.Contains('set "NO_UI=0"') -and $ultraText.Contains($modeNeedle)) {
        $ultraText = $ultraText.Replace($modeNeedle, $modeReplacement)
        $changed = $true
    }
    if ($changed) {
        Backup-File $ultraBat
        Set-Content -LiteralPath $ultraBat -Value $ultraText -Encoding UTF8 -NoNewline
        Write-Log "BAT ultra corrigido para respeitar AURA_NO_BROWSER=1"
    } else {
        Write-Log "BAT ultra ja protegido ou sem chamadas UI"
    }
}

$compileTargets = @($programmer, $llmEngine, $chatApi, $modelRouter) | Where-Object { Test-Path -LiteralPath $_ }
$compileOk = $true
foreach ($target in $compileTargets) {
    & $Python -m py_compile $target 2>> $PatchLog
    if ($LASTEXITCODE -ne 0) {
        $compileOk = $false
        Write-Log ("Falha de sintaxe: {0}" -f $target) "ERROR"
    }
}
if (-not $compileOk) {
    Write-Log "Os patches nao foram iniciados por falha de compilacao; restaure a pasta backups/aura_max_*" "ERROR"
    exit 3
}
Write-Log "Smoke de sintaxe Python OK"

if (-not $NoRestartHermes) { Stop-KnownHermes }

$started = [ordered]@{}
$started.bridge = Start-AuraService "Bridge" (Join-Path $Root "bridge\server.py") @("--host", "127.0.0.1", "--port", "8080") 8080 $Root
$started.engine = Start-AuraService "Engine" (Join-Path $Root "engine\server.py") @("--host", "127.0.0.1", "--port", "8765") 8765 $Root
$matrix = Join-Path $Root "scripts\aura_serve_matriz.py"
if (Test-Path -LiteralPath $matrix) {
    $started.matriz = Start-AuraService "Matriz" $matrix @() 8766 $Root
} else { $started.matriz = $false }
$control = Join-Path $Root "scripts\aura_tools_control_api.py"
if (Test-Path -LiteralPath $control) {
    $started.control = Start-AuraService "Control" $control @() 8790 $Root
} else { $started.control = $false }
$voice = Join-Path $Root "bridge\jarvis_voice_server.py"
if (Test-Path -LiteralPath $voice) {
    $started.voice = Start-AuraService "Voice" $voice @("--host", "127.0.0.1", "--port", "8099", "--lazy") 8099 $Root
} else { $started.voice = $false }
$hermes = Join-Path $Root "hermes_v10\AURA_RUN_HERMES.py"
if (Test-Path -LiteralPath $hermes) {
    $started.hermes = Start-AuraService "Hermes" $hermes @() 8777 (Join-Path $Root "hermes_v10")
} else { $started.hermes = $false }

$ollamaOk = $false
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 5
    $available = @($tags.models | ForEach-Object { [string]$_.name })
    if ($available -notcontains $Model) {
        Write-Log ("Ollama activo, mas {0} nao aparece em /api/tags" -f $Model) "WARN"
    } else {
        $payload = @{
            model = $Model
            prompt = "Responde apenas OK."
            stream = $false
            keep_alive = "20m"
            options = @{ num_predict = 4; num_ctx = 2048; num_gpu = 99 }
        } | ConvertTo-Json -Depth 5
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 120
        $ollamaOk = $true
        Write-Log ("Ollama warmup OK: {0}, keep_alive=20m" -f $Model)
    }
} catch {
    Write-Log ("Ollama warmup falhou: {0}" -f $_.Exception.Message) "WARN"
}

$serviceStatus = [ordered]@{}
foreach ($item in @(@("bridge",8080), @("engine",8765), @("matriz",8766), @("control",8790), @("voice",8099), @("hermes",8777), @("ollama",11434))) {
    $serviceStatus[$item[0]] = Test-Port ([int]$item[1])
}
$report = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    root = $Root
    model = $Model
    no_browser = $NoBrowser
    paper_trade = $true
    execution_allowed = $false
    ollama_warmup = $ollamaOk
    services = $serviceStatus
    started = $started
    backup_dir = $BackupDir
    note = "Arranque idempotente; nao chama AURA_HERMES_V10_ULTRA.bat e nao abre HTML."
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $BootReport -Encoding UTF8
Write-Log ("Relatorio de boot guardado em {0}" -f $BootReport)

$coreOk = $serviceStatus.bridge -and $serviceStatus.engine -and $serviceStatus.hermes
if ($coreOk) {
    Write-Log "AURA MAX ONLINE: Bridge + Engine + Hermes"
    exit 0
}
Write-Log "AURA MAX parcial: consultar logs_supervisor/aura_max_fix.log e os logs por servico" "WARN"
exit 1
