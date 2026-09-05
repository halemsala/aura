# -*- coding: utf-8 -*-
import json
import subprocess
import sys
from pathlib import Path

ps = r"""
$out = @{}
try {
  $desk = (Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone' -Name Value -EA SilentlyContinue).Value
  $out.desktop_apps = $desk
} catch { $out.desktop_apps = $_.Exception.Message }
try {
  $non = (Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged' -Name Value -EA SilentlyContinue).Value
  $out.nonpackaged = $non
} catch { $out.nonpackaged = $_.Exception.Message }
$devs = @()
Get-CimInstance Win32_PnPEntity -EA SilentlyContinue | Where-Object {
  $_.PNPClass -match 'Audio|Camera|MEDIA' -or $_.Name -match 'mic|Microfone|Array|Webcam|Headset'
} | ForEach-Object {
  $devs += [pscustomobject]@{ name = $_.Name; status = $_.Status; class = $_.PNPClass }
}
$out.devices = $devs
try {
  Add-Type -AssemblyName System.Speech
  $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine
  $r.SetInputToDefaultAudioDevice()
  $out.sapi_default_ok = $true
} catch {
  $out.sapi_default_ok = $false
  $out.sapi_error = $_.Exception.Message
}
$out | ConvertTo-Json -Depth 5
"""
p = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps],
    capture_output=True, timeout=30)
out = (p.stdout or b"").decode("utf-8", "replace")
err = (p.stderr or b"").decode("utf-8", "replace")
print("RC", p.returncode)
print(out)
if err:
    print("ERR", err[:800])
