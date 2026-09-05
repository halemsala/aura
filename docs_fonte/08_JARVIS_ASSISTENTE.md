# JARVIS — Assistente Pessoal (Camada 3b+)

CPU-only. Ollama :11434 intocável. paper_trade / execution_allowed **não são tools**.

## Ficheiros

| Path | Papel |
|------|--------|
| `bridge/jarvis/security/safe_executor.py` | Mouse/teclado + Anti-Bet Shield |
| `bridge/jarvis/vision/face_id_manager.py` | FaceID Haar/LBPH CPU |
| `bridge/jarvis/router/voice_router.py` | Roteador v1.2 + gates |
| `tools/register_face.py` | Cadastro facial |

## Pipeline

1. Pânico (`para de mexer`) → 60s bloqueio falado  
2. Intents determinísticos  
3. LLM JSON (`llama3.2:3b`)  
4. Gates: whitelist → AUTORIZO → Anti-Bet → FaceID  
5. Execução SafeExecutor  
6. Auditoria `logs_supervisor/aura_jarvis_actions.jsonl`  
7. **Sempre fala** o resultado (nunca silêncio)

## Deps

```bat
C:\aura\engine\venv\Scripts\pip.exe install opencv-contrib-python pyautogui pygetwindow
python tools\register_face.py --name Admin
```

## Integração voz

```python
from bridge.jarvis.router.voice_router import process_voice_command
spoken = process_voice_command(transcript)
# trigger_tts(spoken)
```
