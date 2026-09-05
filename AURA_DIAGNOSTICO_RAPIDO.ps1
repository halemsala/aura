# AURA_DIAGNOSTICO_RAPIDO.ps1
# Somente leitura; mostra progresso e não abre Ollama nem Docker.
$ErrorActionPreference = 'Continue'
$root = 'C:\aura'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir = Join-Path $root "diagnostico_rapido_$stamp"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

function Step($name, $script) {
    Write-Host "[INICIO] $name" -ForegroundColor Cyan
    $file = Join-Path $outDir "$name.txt"
    try { & $script 2>&1 | Out-File -Encoding UTF8 $file; Write-Host "[OK] $name" -ForegroundColor Green }
    catch { "ERRO: $($_.Exception.Message)" | Set-Content -Encoding UTF8 $file; Write-Host "[ERRO] $name" -ForegroundColor Red }
}

Step '01_RESUMO' {
    "Data: $(Get-Date -Format o)"
    "Computador: $env:COMPUTERNAME"
    "Usuario: $env:USERNAME"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "AURA existe: $(Test-Path $root)"
    "Python: $((python --version 2>&1) -join ' ')"
}
Step '02_PASTA_RAIZ' {
    Get-ChildItem -LiteralPath $root -Force -File -ErrorAction SilentlyContinue |
        Select-Object Name,Length,Extension,LastWriteTime | Sort-Object Name | Format-Table -AutoSize
}
Step '03_COMPONENTES_PRINCIPAIS' {
    Get-ChildItem -LiteralPath $root -Force -Directory -ErrorAction SilentlyContinue |
        Select-Object Name,FullName,LastWriteTime | Format-Table -AutoSize
    Get-ChildItem -LiteralPath $root -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.py','.ps1','.json','.html','.htm','.txt','.md' } |
        Select-Object Name,Length,Extension,LastWriteTime | Format-Table -AutoSize
}
Step '04_ARQUIVOS_FLASH_SOKKER' {
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)flash|score|sokker|bielefeld|pauli' -or $_.Extension -in '.html','.htm' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Select-Object -First 300 | Format-Table -AutoSize
}
Step '05_PROCESSOS_AURA' {
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '(?i)ollama|python|aura|engine|bridge|voice|node|code' } |
        Select-Object Id,ProcessName,Path,StartTime | Format-Table -AutoSize
}
Step '06_PORTAS' {
    Get-NetTCPConnection -ErrorAction SilentlyContinue |
        Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize
}
Step '07_SERVICOS_AURA' {
    Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)aura|ollama|engine|bridge|voice|docker' -or $_.DisplayName -match '(?i)aura|ollama|engine|bridge|voice|docker' } |
        Select-Object Status,StartType,Name,DisplayName | Format-Table -AutoSize
}
Step '08_AGENTES_SKILLS_AUTOMACOES' {
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)agent|skill|manifest|prompt|assistant|automation|task|workflow|boot_state|audit|plan' } |
        Select-Object FullName,Length,Extension,LastWriteTime | Select-Object -First 500 | Format-Table -AutoSize
}
Step '09_LOGS_RECENTES' {
    Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.log','.jsonl' -or $_.Name -match '(?i)log|error|report' } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 10 |
        ForEach-Object { "--- $($_.FullName) ---"; Get-Content $_.FullName -Tail 30 -ErrorAction SilentlyContinue }
}
Step '10_PORTAS_OLLAMA_SEM_ABRIR' {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:11434/api/tags | Select-Object StatusCode }
    catch { 'Ollama não consultado ou indisponível; nenhum aplicativo foi aberto.' }
}
$zip = "$outDir.zip"
Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $zip -Force
Write-Host "CONCLUIDO: $zip" -ForegroundColor Green
