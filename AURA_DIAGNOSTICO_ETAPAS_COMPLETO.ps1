# AURA_DIAGNOSTICO_ETAPAS_COMPLETO.ps1
# Coleta completa das áreas relevantes, sem limite artificial de arquivos.
# Somente leitura; exclui dependências pesadas que não representam a configuração da AURA.
$ErrorActionPreference = 'Continue'
$root = 'C:\aura'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir = Join-Path $root "diagnostico_completo_$stamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$excluded = '\\node_modules(\\|$)|\\.git(\\|$)|\\dist(\\|$)|\\build(\\|$)|\\.next(\\|$)|\\venv(\\|$)|\\__pycache__(\\|$)|\\diagnostico_[^\\]+(\\|$)|\\inventario_[^\\]+(\\|$)'

function All-RelevantFiles {
    $dirs = 'agents','skills','halem_control','logs_supervisor','scripts','config','configs','data','html','uploads','downloads','deepseek-harness'
    foreach ($name in $dirs) {
        $path = Join-Path $root $name
        if (Test-Path $path) {
            Get-ChildItem -LiteralPath $path -Force -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch $excluded }
        }
    }
}

function Save-Step($number, $title, $script) {
    $safe = $title -replace '[^a-zA-Z0-9_-]', '_'
    $file = Join-Path $outDir ("{0:D2}_{1}.txt" -f $number, $safe)
    Write-Host "[INICIO] ETAPA $number/7 - $title" -ForegroundColor Cyan
    try {
        & $script 2>&1 | Out-File -FilePath $file -Encoding UTF8
        $lines = (Get-Content -LiteralPath $file -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        $bytes = (Get-Item -LiteralPath $file).Length
        Write-Host "[OK] $lines linhas / $bytes bytes -> $file" -ForegroundColor Green
        Write-Host "Prévia final:" -ForegroundColor DarkGray
        Get-Content -LiteralPath $file -Tail 5 -ErrorAction SilentlyContinue
    } catch {
        "ERRO: $($_.Exception.Message)" | Set-Content -LiteralPath $file -Encoding UTF8
        Write-Host "[ERRO] $file" -ForegroundColor Red
    }
    if ($number -lt 7) { Read-Host "Pressione Enter para iniciar a etapa $($number + 1)" | Out-Null }
}

Save-Step 1 'Raiz e estrutura' {
    Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue |
        Select-Object Mode,Name,Length,Extension,LastWriteTime | Format-Table -AutoSize
    '--- PASTAS ---'
    Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
        Select-Object FullName,LastWriteTime | Format-Table -AutoSize
}

Save-Step 2 'Todos os arquivos Flashscore SokkerPro HTML' {
    All-RelevantFiles |
        Where-Object { $_.Name -match '(?i)flash|score|sokker|bielefeld|pauli' -or $_.Extension -in '.html','.htm' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Format-Table -AutoSize
}

Save-Step 3 'Processos relevantes' {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '(?i)ollama|python|aura|engine|bridge|voice|node|code|piper' } |
        Select-Object Id,ProcessName,Path,StartTime,CPU,WorkingSet64 | Format-Table -AutoSize
}

Save-Step 4 'Todas as portas TCP UDP' {
    '--- TCP ---'
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize
    '--- UDP ---'
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
}

Save-Step 5 'Servicos e automacoes' {
    '--- SERVICOS ---'
    Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)aura|ollama|engine|bridge|voice|docker|piper' -or $_.DisplayName -match '(?i)aura|ollama|engine|bridge|voice|docker|piper' } |
        Select-Object Status,StartType,Name,DisplayName | Format-Table -AutoSize
    '--- TAREFAS ---'
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -match '(?i)aura|ollama|engine|bridge|voice|agent|automation' -or $_.TaskPath -match '(?i)aura|ollama|engine|bridge|voice|agent|automation' } |
        Select-Object TaskPath,TaskName,State,Author | Format-Table -AutoSize
}

Save-Step 6 'Agentes skills configuracoes e logs' {
    All-RelevantFiles |
        Where-Object { $_.Name -match '(?i)agent|skill|manifest|prompt|assistant|automation|task|workflow|boot_state|audit|plan|config|\.log$|\.jsonl$' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Format-Table -AutoSize
}

Save-Step 7 'Variaveis e resumo' {
    "Computador: $env:COMPUTERNAME"
    "Usuario: $env:USERNAME"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "Python: $((python --version 2>&1) -join ' ')"
    "Ollama não será aberto; apenas processo e variáveis serão observados."
    Get-Process -Name ollama -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-List
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(AURA|PAPER_TRADE|EXECUTION_ALLOWED|GLM_ADVISORY_ONLY)' } |
        Select-Object Name,Value | Format-Table -AutoSize
}

$manifest = [ordered]@{ generated_at=(Get-Date -Format o); root=$root; read_only=$true; excluded=$excluded; files=(Get-ChildItem $outDir -File | Select-Object -ExpandProperty Name) }
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $outDir 'MANIFEST.json')
$zip = "$outDir.zip"
Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $zip -Force
Write-Host "`nDIAGNOSTICO COMPLETO CONCLUIDO: $zip" -ForegroundColor Green
