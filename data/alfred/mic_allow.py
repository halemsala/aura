# -*- coding: utf-8 -*-
import subprocess
ps = r"""
$paths = @(
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged'
)
foreach($p in $paths){
  if(Test-Path $p){ Set-ItemProperty -Path $p -Name Value -Value 'Allow' -EA SilentlyContinue }
}
Write-Output 'privacy=Allow'
"""
subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], timeout=15)
print("ok")
