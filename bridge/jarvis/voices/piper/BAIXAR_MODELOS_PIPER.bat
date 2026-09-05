@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Baixando modelos Piper pt-BR (Faber + Miro) do HuggingFace...
echo Isto demora 1-2 min (cerca de 120 MB).
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx' -OutFile 'pt_BR-faber-medium.onnx' -UseBasicParsing"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json' -OutFile 'pt_BR-faber-medium.onnx.json' -UseBasicParsing"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_miro/resolve/main/miro_pt-BR.onnx' -OutFile 'miro_pt-BR.onnx' -UseBasicParsing"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://huggingface.co/OpenVoiceOS/pipertts_pt-BR_miro/resolve/main/miro_pt-BR.onnx.json' -OutFile 'miro_pt-BR.onnx.json' -UseBasicParsing"
echo.
if exist pt_BR-faber-medium.onnx (echo Faber OK) else (echo Faber FALHOU)
if exist miro_pt-BR.onnx (echo Miro OK) else (echo Miro FALHOU)
pause
