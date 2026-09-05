# Captura ecras da AURA (Mesa live / Desktop) para o auditor IA.
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\AURA_CAPTURE_VISUAL.ps1
param([string]$OutDir = "")
$ErrorActionPreference = "Continue"
$Root = if (Test-Path "C:\aura\AURA_QUANT_X_12.7.0") { "C:\aura\AURA_QUANT_X_12.7.0" } else { (Get-Location).Path }
if (-not $OutDir) { $OutDir = Join-Path $Root "logs_instalacao\visual" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$path = Join-Path $OutDir ("aura_screen_" + $stamp + ".png")
$bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
# manifesto simples
$meta = @{ ts = (Get-Date).ToString("o"); file = $path; w = $screen.Width; h = $screen.Height }
($meta | ConvertTo-Json) | Set-Content (Join-Path $OutDir "latest_visual.json") -Encoding UTF8
Write-Output $path
