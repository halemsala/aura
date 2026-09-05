# AURA - test Ollama REST (tags / generate / chat / stream with error handling)
param(
  [string]$Model = "llama3.2:3b",
  [string]$BaseUrl = "http://127.0.0.1:11434",
  [switch]$Stream,
  [string]$Prompt = "Responde em uma frase: o que e paper trade?"
)
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Write-Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red }
function Write-Info($m) { Write-Host "[..] $m" -ForegroundColor Cyan }

Write-Info "BaseUrl=$BaseUrl Model=$Model"

# 1) tags
try {
  $tags = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -TimeoutSec 5
  $names = @($tags.models | ForEach-Object { $_.name })
  Write-Ok ("models: " + ($names -join ", "))
  if ($names -notcontains $Model -and -not ($names | Where-Object { $_ -like "$Model*" })) {
    Write-Fail "Model '$Model' not in list. Pull first: ollama pull $Model"
  }
} catch {
  Write-Fail "GET /api/tags failed: $($_.Exception.Message)"
  Write-Info "Is Ollama running? Start Ollama app or: ollama serve"
  exit 1
}

# 2) generate non-stream
try {
  $body = @{ model = $Model; prompt = $Prompt; stream = $false } | ConvertTo-Json
  $r = Invoke-RestMethod -Uri "$BaseUrl/api/generate" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 120
  Write-Ok ("generate: " + [string]$r.response)
} catch {
  Write-Fail "POST /api/generate: $($_.Exception.Message)"
}

# 3) chat non-stream
try {
  $chat = @{
    model = $Model
    messages = @(@{ role = "user"; content = $Prompt })
    stream = $false
  } | ConvertTo-Json -Depth 5
  $r = Invoke-RestMethod -Uri "$BaseUrl/api/chat" -Method POST -Body $chat -ContentType "application/json" -TimeoutSec 120
  Write-Ok ("chat: " + [string]$r.message.content)
} catch {
  Write-Fail "POST /api/chat: $($_.Exception.Message)"
}

# 4) stream with error handling
if ($Stream) {
  Write-Info "Streaming /api/generate ..."
  try {
    $payload = (@{ model = $Model; prompt = $Prompt; stream = $true } | ConvertTo-Json)
    $req = [System.Net.HttpWebRequest]::Create("$BaseUrl/api/generate")
    $req.Method = "POST"
    $req.ContentType = "application/json"
    $req.Timeout = 120000
    $req.ReadWriteTimeout = 120000
    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    $req.ContentLength = $bytes.Length
    $rs = $req.GetRequestStream()
    $rs.Write($bytes, 0, $bytes.Length)
    $rs.Close()
    $resp = $req.GetResponse()
    $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
    $sb = New-Object System.Text.StringBuilder
    $chunks = 0
    while ($null -ne ($line = $reader.ReadLine())) {
      if ([string]::IsNullOrWhiteSpace($line)) { continue }
      try {
        $o = $line | ConvertFrom-Json
        if ($o.error) {
          Write-Fail ("stream error field: " + $o.error)
          break
        }
        if ($o.response) {
          [void]$sb.Append([string]$o.response)
          Write-Host -NoNewline ([string]$o.response)
          $chunks++
        }
        if ($o.done -eq $true) {
          Write-Host ""
          break
        }
      } catch {
        Write-Fail ("bad stream line: $line | $($_.Exception.Message)")
        break
      }
    }
    $reader.Close()
    $resp.Close()
    Write-Ok ("stream done chunks=$chunks chars=$($sb.Length)")
  } catch [System.Net.WebException] {
    $ex = $_.Exception
    $code = $null
    if ($ex.Response) { $code = [int]$ex.Response.StatusCode }
    Write-Fail ("stream WebException status=$code msg=$($ex.Message)")
    if ($ex.Response) {
      try {
        $sr = New-Object IO.StreamReader($ex.Response.GetResponseStream())
        Write-Host $sr.ReadToEnd()
        $sr.Close()
      } catch {}
    }
  } catch {
    Write-Fail ("stream failed: $($_.Exception.Message)")
  }
}

Write-Info "Done. AURA Engine uses same REST at 11434 when services_health.ollama=True"
