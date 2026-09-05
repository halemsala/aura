# AURA_DIAGNOSTICO_ETAPAS_RAPIDO.ps1
# Coleta limitada e somente leitura. Evita varrer toda a árvore da AURA.
$ErrorActionPreference = 'Continue'
$root = 'C:\aura'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir = Join-Path $root "diagnostico_rapido_$stamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

function Run-Step($number, $title, $body) {
    Clear-Host
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "AURA - ETAPA $number/7 - $title" -ForegroundColor Cyan
    Write-Host "Escopo limitado; somente leitura; Ctrl+C interrompe." -ForegroundColor DarkGray
    Write-Host "============================================================" -ForegroundColor DarkCyan
    $safe = $title -replace '[^a-zA-Z0-9_-]', '_'
    $file = Join-Path $outDir ("{0:D2}_{1}.txt" -f $number, $safe)
    try { & $body 2>&1 | Tee-Object -FilePath $file; Write-Host "`n[OK] Etapa $number salva em $file" -ForegroundColor Green }
    catch { "ERRO: $($_.Exception.Message)" | Tee-Object -FilePath $file -Append; Write-Host "[ERRO] Etapa $number preservada" -ForegroundColor Red }
    if ($number -lt 7) { Read-Host "Pressione Enter para iniciar a etapa $($number + 1)" | Out-Null }
}

function Relevant-Files {
    $dirs = 'agents','skills','halem_control','logs_supervisor','scripts','config','configs','data','html','uploads','downloads'
    foreach ($name in $dirs) {
        $path = Join-Path $root $name
        if (Test-Path $path) {
            "--- $path ---"
            Get-ChildItem -LiteralPath $path -Force -File -Recurse -Depth 3 -ErrorAction SilentlyContinue |
                Select-Object -First 300 FullName,Length,Extension,LastWriteTime
        }
    }
}

Run-Step 1 'Raiz da AURA' {
    "Arquivos e pastas imediatamente na raiz; nenhuma varredura recursiva."
    Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue |
        Select-Object Mode,Name,Length,Extension,LastWriteTime | Format-Table -AutoSize
}

Run-Step 2 'HTML Flashscore SokkerPro' {
    $patterns = '*flash*','*score*','*sokker*','*bielefeld*','*pauli*','*.html','*.htm'
    foreach ($pattern in $patterns) {
        Get-ChildItem -LiteralPath $root -Force -File -Filter $pattern -ErrorAction SilentlyContinue |
            Select-Object FullName,Length,Extension,LastWriteTime
    }
    "Pastas operacionais, profundidade máxima 3:"
    Relevant-Files | Where-Object { $_.FullName -match '(?i)flash|score|sokker|bielefeld|pauli|html' }
}

Run-Step 3 'Processos relevantes' {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '(?i)ollama|python|aura|engine|bridge|voice|node|code' } |
        Select-Object Id,ProcessName,Path,StartTime | Format-Table -AutoSize
}

Run-Step 4 'Portas abertas' {
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
}

Run-Step 5 'Servicos e automacoes' {
    Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)aura|ollama|engine|bridge|voice|docker' -or $_.DisplayName -match '(?i)aura|ollama|engine|bridge|voice|docker' } |
        Select-Object Status,StartType,Name,DisplayName | Format-Table -AutoSize
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -match '(?i)aura|ollama|engine|bridge|voice|agent|automation' } |
        Select-Object TaskPath,TaskName,State | Format-Table -AutoSize
}

Run-Step 6 'Agentes skills e logs' {
    Relevant-Files | Format-Table -AutoSize
    Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)agent|skill|log|audit|control|config|script' } |
        Select-Object FullName,LastWriteTime | Format-Table -AutoSize
}

Run-Step 7 'Resumo sem abrir Ollama' {
    "Computador: $env:COMPUTERNAME"
    "Usuario: $env:USERNAME"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "Python: $((python --version 2>&1) -join ' ')"
    "Ollama não será aberto; apenas observação de processo e variáveis seguras."
    Get-Process -Name ollama -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-List
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(AURA|PAPER_TRADE|EXECUTION_ALLOWED|GLM_ADVISORY_ONLY)' } |
        Select-Object Name,Value | Format-Table -AutoSize
}

$manifest = [ordered]@{ generated_at=(Get-Date -Format o); root=$root; read_only=$true; limited_scope=$true; files=(Get-ChildItem $outDir -File | Select-Object -ExpandProperty Name) }
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $outDir 'MANIFEST.json')
$zip = "$outDir.zip"
Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $zip -Force
Write-Host "`nDIAGNOSTICO RAPIDO CONCLUIDO: $zip" -ForegroundColor Green
