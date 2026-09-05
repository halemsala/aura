# -*- coding: utf-8 -*-
from pathlib import Path
import os
import winreg

root = Path(r"C:\aura")
cmd = f'"{root / "AURA_ALFRED_SEMPRE_LIGADO.bat"}" silent'
startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
startup.mkdir(parents=True, exist_ok=True)
bat = startup / "AURA_Alfred.bat"
bat.write_text(
    "@echo off\r\n"
    f'cd /d "{root}"\r\n'
    f'start "" /MIN "{root / "AURA_ALFRED_SEMPRE_LIGADO.bat"}" silent\r\n',
    encoding="utf-8",
)
key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")
winreg.SetValueEx(key, "AURA_Alfred", 0, winreg.REG_SZ, cmd)
winreg.CloseKey(key)
print("startup", bat)
print("exists", bat.is_file())
print("run_key", cmd)
