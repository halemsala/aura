# ============================================================
# AURA QUANT-X - Injetar live_latest.json no formato CORRETO
# Versão: V25T15-FINAL
# Resolve: Bridge 500 / Engine BLOCKED_BY_DATA quando o arquivo
#          está ausente ou com schema inválido
# ============================================================

$ErrorActionPreference = "Continue"
$Root = "C:\aura\AURA_QUANT_X_12.7.0"
$LatestPath = Join-Path $Root "bridge\live_latest.json"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " AURA - INJETAR live_latest.json (formato válido)" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# Usa a partida atual do SokkerPRO se o usuário informar, senão usa template
# NOTA: NÃO usar $home - é variável automática somente-leitura no PowerShell
$homeTeam = "Aldosivi"
$awayTeam = "Independiente Rivadavia · Copa Argentina"
$fid  = "19764966"
$minute = 30
$scoreH = 0
$scoreA = 1

Write-Host "Usando template de partida:" -ForegroundColor Yellow
Write-Host "  $homeTeam x $awayTeam (fixture $fid)"
Write-Host ""

$now = Get-Date
$receivedAt = $now.ToString("yyyy-MM-ddTHH:mm:ss-03:00")
$exportedAt = $now.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
$ts = [long]([DateTimeOffset]$now).ToUnixTimeMilliseconds()

$json = @"
{
  "received_at": "$receivedAt",
  "view": {
    "schema": "cornerai-analyst-1",
    "fixture_id": "$fid",
    "league": null,
    "home": "$homeTeam",
    "away": "$awayTeam",
    "minute": $minute,
    "extra": 0,
    "period": null,
    "status": "live",
    "score_home": $scoreH,
    "score_away": $scoreA,
    "corners_home": 3,
    "corners_away": 1,
    "attacks_home": 50,
    "attacks_away": 45,
    "dangerous_home": 15,
    "dangerous_away": 20,
    "xg_home": 0.5,
    "xg_away": 0.6,
    "possession_home": null,
    "possession_away": null,
    "shots_on_home": 2,
    "shots_on_away": 2,
    "corner_events": [],
    "cpi_home": null,
    "cpi_away": null,
    "pred": null,
    "raw_ts": $ts,
    "quality": 0.85
  },
  "payload": {
    "schema": "cornerai-analyst-1",
    "source": "aura-capture-webview2",
    "exportedAt": "$exportedAt",
    "ts": $ts,
    "fixture": {
      "id": "$fid",
      "home": "$homeTeam",
      "away": "$awayTeam",
      "minute": $minute,
      "extra": 0,
      "status": "live",
      "score": { "home": $scoreH, "away": $scoreA }
    },
    "pressure": {
      "gauge": null,
      "attacks": { "home": 50, "away": 45 },
      "dangerous": { "home": 15, "away": 20 },
      "xg": { "home": 0.5, "away": 0.6 },
      "shotsOn": { "home": 2, "away": 2 }
    },
    "corners": {
      "total": { "home": 3, "away": 1 },
      "events": []
    },
    "stats": {
      "attacks": { "home": 50, "away": 45 },
      "dangerous": { "home": 15, "away": 20 },
      "xg": { "home": 0.5, "away": 0.6 },
      "shotsOn": { "home": 2, "away": 2 },
      "corners": { "home": 3, "away": 1 }
    },
    "corner_events": [],
    "quality": { "score": 0.85 }
  },
  "fingerprint": "$fid|$minute|$scoreH|$scoreA|3|1|15|20"
}
"@

# Garantir pasta bridge
if (-not (Test-Path (Join-Path $Root "bridge"))) {
    New-Item -ItemType Directory -Path (Join-Path $Root "bridge") -Force | Out-Null
}

$json | Set-Content $LatestPath -Encoding UTF8
Write-Host "Arquivo gravado: $LatestPath" -ForegroundColor Green

Start-Sleep -Seconds 3

# Testar Bridge
Write-Host ""
Write-Host "[Teste] GET /api/cornerai/latest ..." -NoNewline
try {
    $r = Invoke-RestMethod "http://127.0.0.1:8080/api/cornerai/latest" -TimeoutSec 5
    Write-Host " OK" -ForegroundColor Green
    Write-Host "  home=$($r.view.home)  away=$($r.view.away)  min=$($r.view.minute)"
} catch {
    Write-Host " FALHOU" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
}

# Testar Engine
Write-Host ""
Write-Host "[Teste] Estado do Engine ..." -NoNewline
try {
    $ui = Invoke-RestMethod "http://127.0.0.1:8765/api/ui/state" -TimeoutSec 5
    Write-Host " OK" -ForegroundColor Green
    Write-Host "  fixtureId     = $($ui.fixtureId)"
    Write-Host "  jarvis_state  = $($ui.jarvis_state)"
    Write-Host "  capture_stale = $($ui.capture_stale)"
    Write-Host "  source        = $($ui.source)"

    if ($ui.fixtureId) {
        Write-Host ""
        Write-Host "  ENGINE ENGATOU NO FIXTURE!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "  Engine ainda sem fixtureId (pode levar mais alguns segundos)" -ForegroundColor Yellow
    }
} catch {
    Write-Host " FALHOU" -ForegroundColor Red
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""
