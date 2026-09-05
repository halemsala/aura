$ErrorActionPreference = 'Stop'
$root = 'C:\aura'
$vscode = Join-Path $root '.vscode'
New-Item -ItemType Directory -Path $vscode -Force | Out-Null

$tasks = @'
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "AURA: Diagnostico somente leitura",
      "type": "shell",
      "command": "python",
      "args": ["${workspaceFolder}\\engine\\diagnostico_aura_definitivo.py", "--json", "--output", "${workspaceFolder}\\state\\diagnostico_latest.json"],
      "options": {"cwd": "${workspaceFolder}"},
      "problemMatcher": []
    },
    {
      "label": "AURA: Ver relatorio atual",
      "type": "shell",
      "command": "powershell",
      "args": ["-NoProfile", "-Command", "Get-Content -LiteralPath '${workspaceFolder}\\state\\diagnostico_latest.json' -Raw"],
      "options": {"cwd": "${workspaceFolder}"},
      "problemMatcher": []
    },
    {
      "label": "AURA: Iniciar harness",
      "type": "shell",
      "command": "python",
      "args": ["${workspaceFolder}\\AURA_HARNESS_CORE.py"],
      "options": {
        "cwd": "${workspaceFolder}",
        "env": {
          "PYTHONPATH": "${workspaceFolder};${workspaceFolder}\\scripts",
          "NO_PROXY": "127.0.0.1,localhost",
          "no_proxy": "127.0.0.1,localhost"
        }
      },
      "isBackground": false,
      "problemMatcher": []
    },
    {
      "label": "AURA: Reparar Ollama",
      "type": "shell",
      "command": "python",
      "args": ["${workspaceFolder}\\AURA_HARNESS_CORE.py", "--reparar"],
      "options": {
        "cwd": "${workspaceFolder}",
        "env": {
          "PYTHONPATH": "${workspaceFolder};${workspaceFolder}\\scripts",
          "NO_PROXY": "127.0.0.1,localhost",
          "no_proxy": "127.0.0.1,localhost"
        }
      },
      "problemMatcher": []
    },
    {
      "label": "AURA: Monitorar GPU",
      "type": "shell",
      "command": "nvidia-smi",
      "args": ["-l", "2"],
      "options": {"cwd": "${workspaceFolder}"},
      "isBackground": true,
      "problemMatcher": []
    },
    {
      "label": "AURA: Testar API Ollama",
      "type": "shell",
      "command": "curl.exe",
      "args": ["--noproxy", "*", "--max-time", "5", "-sS", "http://127.0.0.1:11434/api/tags"],
      "options": {"cwd": "${workspaceFolder}"},
      "problemMatcher": []
    }
  ]
}
'@

$settings = @'
{
  "python.defaultInterpreterPath": "python",
  "terminal.integrated.defaultProfile.windows": "PowerShell",
  "terminal.integrated.cwd": "C:\\aura",
  "files.encoding": "utf8",
  "files.autoGuessEncoding": true
}
'@

Set-Content -LiteralPath (Join-Path $vscode 'tasks.json') -Value $tasks -Encoding UTF8
Set-Content -LiteralPath (Join-Path $vscode 'settings.json') -Value $settings -Encoding UTF8
New-Item -ItemType Directory -Path (Join-Path $root 'state') -Force | Out-Null

Write-Host 'Configuracao do VS Code criada:' -ForegroundColor Green
Write-Host (Join-Path $vscode 'tasks.json')
Write-Host (Join-Path $vscode 'settings.json')
Write-Host ''
Write-Host 'Abra a pasta C:\aura no VS Code e use Ctrl+Shift+P > Tasks: Run Task.' -ForegroundColor Cyan
Write-Host 'Nenhum agente, Bridge, Engine ou Voice foi iniciado automaticamente.' -ForegroundColor Yellow
