#Requires -Version 5.1
# Injects AURA LAB overlay into AURA_HARNESS_UNICO_CONSOLIDADO.py
# Run in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   cd C:\aura\aura_lab
#   .\tools\INSTALL_HARNESS_OVERLAY.ps1

[CmdletBinding()]
param(
    [string]$LabRoot = "C:\aura\aura_lab",
    [string]$HarnessPath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== AURA LAB -> Harness overlay installer ===" -ForegroundColor Cyan

# Env for current + user
[System.Environment]::SetEnvironmentVariable("AURA_LAB_ROOT", $LabRoot, "User")
$env:AURA_LAB_ROOT = $LabRoot
Write-Host "AURA_LAB_ROOT = $LabRoot"

$vision = Join-Path $LabRoot "harness\harness_lab_vision.py"
if (-not (Test-Path -LiteralPath $vision)) {
    throw "Missing: $vision"
}

# Find harness file
$candidates = @()
if ($HarnessPath) { $candidates += $HarnessPath }
$candidates += @(
    "C:\aura\AURA_HARNESS_UNICO_CONSOLIDADO.py",
    (Join-Path $LabRoot "..\AURA_HARNESS_UNICO_CONSOLIDADO.py"),
    "C:\aura\halem_control\AURA_HARNESS_UNICO_CONSOLIDADO.py",
    "C:\aura\scripts\AURA_HARNESS_UNICO_CONSOLIDADO.py"
)

$harness = $null
foreach ($c in $candidates) {
    $full = [System.IO.Path]::GetFullPath($c)
    if (Test-Path -LiteralPath $full) {
        $harness = $full
        break
    }
}

if (-not $harness) {
    Write-Host "Harness file not found automatically." -ForegroundColor Yellow
    Write-Host "Pass path: .\tools\INSTALL_HARNESS_OVERLAY.ps1 -HarnessPath 'C:\caminho\AURA_HARNESS_UNICO_CONSOLIDADO.py'"
    throw "AURA_HARNESS_UNICO_CONSOLIDADO.py not found"
}

Write-Host "Harness: $harness"

$text = [System.IO.File]::ReadAllText($harness)

if ($text -match "apply_lab_vision") {
    Write-Host "Overlay already present (apply_lab_vision found). Nothing to paste." -ForegroundColor Green
    Write-Host "Just restart Harness and type: ajuda / visao / ops / experiencias"
    exit 0
}

$marker = 'if __name__ == "__main__":'
$idx = $text.LastIndexOf($marker)
if ($idx -lt 0) {
    $marker = "if __name__ == '__main__':"
    $idx = $text.LastIndexOf($marker)
}
if ($idx -lt 0) {
    throw "Could not find if __name__ == '__main__' in harness file"
}

$block = @'

# --- AURA LAB + Visao ampliada (auto-install) ---
try:
    import sys
    import os
    from pathlib import Path
    _lab_candidates = [
        Path(os.environ.get("AURA_LAB_ROOT", "")),
        Path(__file__).resolve().parent / "aura_lab",
        Path(__file__).resolve().parent,
        Path(r"C:\aura\aura_lab"),
    ]
    for _lab in _lab_candidates:
        if not _lab or str(_lab) in ("", "."):
            continue
        _hv = _lab / "harness" / "harness_lab_vision.py"
        if _hv.is_file():
            import importlib.util
            _spec = importlib.util.spec_from_file_location("harness_lab_vision", _hv)
            _mod = importlib.util.module_from_spec(_spec)
            assert _spec.loader is not None
            _spec.loader.exec_module(_mod)
            print(_mod.apply_lab_vision(globals()))
            break
    else:
        print("[INFO] AURA LAB nao encontrado — visao ampliada desativada.")
except Exception as _lab_exc:
    print("[WARN] LAB/Visao nao aplicados:", _lab_exc)
# --- fim LAB ---

'@

$backup = $harness + ".bak_before_lab"
[System.IO.File]::Copy($harness, $backup, $true)
Write-Host "Backup: $backup"

$newText = $text.Substring(0, $idx) + $block + $text.Substring($idx)
[System.IO.File]::WriteAllText($harness, $newText)

Write-Host "OK - overlay injected into harness." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1) Close this window and open a NEW PowerShell"
Write-Host "  2) Start Harness the same way you always do"
Write-Host "  3) Look for: LAB+Visao aplicados"
Write-Host "  4) In Harness chat type: ajuda"
Write-Host "     then: visao"
Write-Host "     then: ops"
Write-Host "     then: experiencias"
