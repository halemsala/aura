# AURA_DIAGNOSTICO_ETAPAS_ENTER.ps1
# Um único comando; cada etapa roda após Enter. Somente leitura.
$ErrorActionPreference = 'Continue'
$root = 'C:\aura'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir = Join-Path $root "diagnostico_etapas_$stamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

function Run-Step($number, $title, $body) {
    Clear-Host
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "AURA - ETAPA $number/7 - $title" -ForegroundColor Cyan
    Write-Host "Somente leitura. Pressione Ctrl+C para interromper." -ForegroundColor DarkGray
    Write-Host "============================================================" -ForegroundColor DarkCyan
    $file = Join-Path $outDir ("{0:D2}_{1}.txt" -f $number, ($title -replace '[^a-zA-Z0-9_-]', '_'))
    try {
        & $body 2>&1 | Tee-Object -FilePath $file
        Write-Host "`nEtapa $number concluida. Resultado salvo em $file" -ForegroundColor Green
    } catch {
        "ERRO: $($_.Exception.Message)" | Tee-Object -FilePath $file -Append
        Write-Host "Etapa $number terminou com erro; o relatório foi preservado." -ForegroundColor Red
    }
    if ($number -lt 7) { Read-Host "Pressione Enter para iniciar a etapa $($number + 1)" | Out-Null }
}

Run-Step 1 'Pasta e arquivos principais' {
    "Raiz: $root"
    "Existe: $(Test-Path $root)"
    Get-ChildItem -LiteralPath $root -Force -File -ErrorAction SilentlyContinue |
        Select-Object Name,Length,Extension,LastWriteTime | Sort-Object Name | Format-Table -AutoSize
    Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
        Select-Object Name,LastWriteTime | Format-Table -AutoSize
}

Run-Step 2 'HTML e dados Flashscore SokkerPro' {
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)flash|score|sokker|bielefeld|pauli' -or $_.Extension -in '.html','.htm' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Select-Object -First 500 | Format-Table -AutoSize
}

Run-Step 3 'Processos relevantes' {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '(?i)ollama|python|aura|engine|bridge|voice|node|code' } |
        Select-Object Id,ProcessName,Path,StartTime | Format-Table -AutoSize
}

Run-Step 4 'Portas TCP e UDP' {
    '--- TCP ---'
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize
    '--- UDP ---'
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
}

Run-Step 5 'Servicos e automacoes' {
    '--- SERVICOS AURA ---'
    Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)aura|ollama|engine|bridge|voice|docker' -or $_.DisplayName -match '(?i)aura|ollama|engine|bridge|voice|docker' } |
        Select-Object Status,StartType,Name,DisplayName | Format-Table -AutoSize
    '--- TAREFAS AGENDADAS RELACIONADAS ---'
    Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -match '(?i)aura|ollama|engine|bridge|voice|agent|automation' -or $_.TaskPath -match '(?i)aura|ollama|engine|bridge|voice|agent|automation' } |
        Select-Object TaskPath,TaskName,State,Author | Format-Table -AutoSize
}

Run-Step 6 'Agentes skills configuracoes e logs' {
    '--- COMPONENTES ---'
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)agent|skill|manifest|prompt|assistant|automation|task|workflow|boot_state|audit|plan|config' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Select-Object -First 700 | Format-Table -AutoSize
    '--- LOGS RECENTES ---'
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.log','.jsonl' -or $_.Name -match '(?i)log|error|report' } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 10 |
        ForEach-Object { "--- $($_.FullName) ---"; Get-Content $_.FullName -Tail 30 -ErrorAction SilentlyContinue }
}

Run-Step 7 'Resumo final e Ollama sem abrir aplicativo' {
    "Computador: $env:COMPUTERNAME"
    "Usuario: $env:USERNAME"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "Python: $((python --version 2>&1) -join ' ')"
    "Ollama nao sera aberto. Apenas consulta HTTP com timeout de 2 segundos:"
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags | Select-Object StatusCode,Content }
    catch { "Ollama indisponivel ou fechado: $($_.Exception.Message)" }
    "Variaveis de seguranca:"
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(AURA|PAPER_TRADE|EXECUTION_ALLOWED|GLM_ADVISORY_ONLY)' } |
        Select-Object Name,Value | Format-Table -AutoSize
}

$manifest = [ordered]@{ generated_at=(Get-Date -Format o); root=$root; read_only=$true; files=(Get-ChildItem $outDir -File | Select-Object -ExpandProperty Name) }
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $outDir 'MANIFEST.json')
$zip = "$outDir.zip"
Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $zip -Force
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "DIAGNOSTICO CONCLUIDO" -ForegroundColor Green
Write-Host "Relatorio ZIP: $zip" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
