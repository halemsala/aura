# AURA_INVENTARIO_TOTAL_SOMENTE_LEITURA.ps1
# Inventário somente leitura. Não inicia, encerra, instala, remove ou altera nada.
$ErrorActionPreference = 'Continue'
$root = 'C:\aura'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$out = Join-Path $root "inventario_total_$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null

function Collect($name, $block) {
    $file = Join-Path $out "$name.txt"
    "===== $name =====" | Set-Content -Encoding UTF8 $file
    try { & $block 2>&1 | Out-File -Append -Encoding UTF8 $file }
    catch { "ERRO: $($_.Exception.Message)" | Out-File -Append -Encoding UTF8 $file }
}

Collect '00_RESUMO_SISTEMA' {
    Get-ComputerInfo -Property CsName,WindowsProductName,WindowsVersion,OsBuildNumber,OsArchitecture,CsTotalPhysicalMemory,WindowsInstallDateFromRegistry | Format-List
    "Usuario: $env:USERNAME"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "AURA_ROOT existe: $(Test-Path $root)"
    "Python: $((python --version 2>&1) -join ' ')"
    "Ollama: $((ollama --version 2>&1) -join ' ')"
    "Git: $((git --version 2>&1) -join ' ')"
    "Docker: $((docker --version 2>&1) -join ' ')"
}

Collect '01_ARQUIVOS_AURA_COMPLETOS' {
    if (Test-Path $root) {
        Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '\\inventario_total_[^\\]+\\' } |
            Select-Object FullName,Length,Extension,CreationTime,LastWriteTime | Format-Table -AutoSize
    }
}

Collect '02_PASTAS_E_COMPONENTES' {
    if (Test-Path $root) { Get-ChildItem -LiteralPath $root -Force -Directory -Recurse -ErrorAction SilentlyContinue | Select-Object FullName,CreationTime,LastWriteTime | Format-Table -AutoSize }
}

Collect '03_PORTAS_TCP_UDP_TODAS' {
    '--- TCP ---'
    Get-NetTCPConnection -ErrorAction SilentlyContinue | Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess | Format-Table -AutoSize
    '--- UDP ---'
    Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Sort-Object LocalPort | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
}

Collect '04_SERVICOS_WINDOWS_TODOS' {
    Get-Service | Sort-Object Status,DisplayName | Select-Object Status,StartType,Name,DisplayName | Format-Table -AutoSize
}

Collect '05_PROCESSOS_TODOS' {
    Get-Process -ErrorAction SilentlyContinue | Sort-Object ProcessName | Select-Object Id,ProcessName,Path,StartTime,CPU,WorkingSet64 | Format-Table -AutoSize
}

Collect '06_PROCESSOS_AURA_RELEVANTES' {
    Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '(?i)ollama|python|aura|engine|bridge|voice|node|docker|powershell|code' } | Select-Object Id,ProcessName,Path,StartTime,CPU,WorkingSet64 | Format-List
}

Collect '07_FERRAMENTAS_COMANDOS_INSTALADOS' {
    Get-Command -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object Name,CommandType,Source,Version | Format-Table -AutoSize
}

Collect '08_APLICATIVOS_INSTALADOS' {
    $keys = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object DisplayName | Select-Object DisplayName,DisplayVersion,Publisher,InstallLocation | Sort-Object DisplayName | Format-Table -AutoSize
}

Collect '09_TAREFAS_AUTOMACOES_AGENDADAS' {
    Get-ScheduledTask -ErrorAction SilentlyContinue | Sort-Object TaskPath,TaskName | Select-Object TaskPath,TaskName,State,Author,Description | Format-List
}

Collect '10_INICIALIZACAO_E_AUTORUNS' {
    Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | Select-Object Name,Command,Location,User | Format-List
}

Collect '11_REDE_ADAPTADORES_ROTAS_DNS' {
    Get-NetAdapter -ErrorAction SilentlyContinue | Select-Object Name,InterfaceDescription,Status,MacAddress,LinkSpeed | Format-Table -AutoSize
    Get-NetIPConfiguration -ErrorAction SilentlyContinue | Format-List
    Get-NetRoute -ErrorAction SilentlyContinue | Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric | Format-Table -AutoSize
}

Collect '12_AURA_AGENTES_SKILLS_MANIFESTOS' {
    if (Test-Path $root) {
        Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '(?i)agents?|skills?|manifest|prompt|assistant|automation|task|workflow|boot_state' } |
            Select-Object FullName,Length,Extension,LastWriteTime | Format-Table -AutoSize
    }
}

Collect '13_CONFIGURACOES_NAO_SECRETAS' {
    if (Test-Path $root) {
        Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '(?i)config|manifest|boot_state|requirements|package|docker|compose|settings|state' -and $_.Length -lt 2MB } |
            ForEach-Object {
                "--- $($_.FullName) ---"
                Get-Content $_.FullName -TotalCount 250 -ErrorAction SilentlyContinue |
                    Where-Object { $_ -notmatch '(?i)api.?key|token|secret|password|senha|credential|private.?key' }
            }
    }
}

Collect '14_LOGS_E_RELATORIOS_RECENTES' {
    if (Test-Path $root) {
        Get-ChildItem -LiteralPath $root -Force -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.log','.jsonl' -or $_.Name -match '(?i)log|error|report|audit' } |
            Sort-Object LastWriteTime -Descending | Select-Object -First 50 |
            ForEach-Object { "--- $($_.FullName) | $($_.LastWriteTime) ---"; Get-Content $_.FullName -Tail 100 -ErrorAction SilentlyContinue }
    }
}

Collect '15_OLLAMA_SEM_BLOQUEIO' {
    "Consulta HTTP com timeout de 3 segundos; nenhum comando ollama é executado."
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:11434/api/tags | Select-Object StatusCode,Content }
    catch { "Ollama API indisponivel ou fechado: $($_.Exception.Message)" }
    Get-Process -Name ollama -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-List
}
Collect '16_DOCKER_SEM_BLOQUEIO' {
    "Nenhum comando docker é executado. Apenas processos e portas são observados."
    Get-Process -Name docker,dockerd -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime | Format-List
}
Collect '17_PORTAS_AURA_HEALTH' {
    foreach ($port in 11434,8765,8080,8099) {
        "--- PORTA $port ---"
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$port/api/health" | Select-Object StatusCode,Content } catch { "health indisponivel" }
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$port/health" | Select-Object StatusCode,Content } catch { "health raiz indisponivel" }
    }
}

Collect '18_VARIAVEIS_SEGURAS' {
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(AURA|PAPER_TRADE|EXECUTION_ALLOWED|GLM_ADVISORY_ONLY)' } |
        Select-Object Name,Value | Format-Table -AutoSize
    'Variaveis potencialmente secretas: nomes encontrados, valores omitidos'
    Get-ChildItem Env: | Where-Object { $_.Name -match '(?i)key|token|secret|password|senha|credential' } | Select-Object -ExpandProperty Name
}

Collect '19_GIT_AURA' {
    if (Test-Path (Join-Path $root '.git')) { git -C $root status --short; git -C $root branch --show-current; git -C $root log -5 --oneline } else { 'AURA nao possui .git na raiz' }
}

$manifest = [ordered]@{ generated_at=(Get-Date -Format o); root=$root; read_only=$true; files=(Get-ChildItem $out -File | Select-Object -ExpandProperty Name) }
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $out 'MANIFEST.json')
$zip = "$out.zip"
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -Force
Write-Host "INVENTARIO TOTAL CONCLUIDO" -ForegroundColor Green
Write-Host "Relatorio: $zip" -ForegroundColor Cyan
