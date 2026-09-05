# Validação Grok — Aura/Hermes/Alfred

Backup: `C:\aura\backups\grok_20260902_162418`
Checkpoint: `C:\aura\data\alfred\checkpoints\ckpt-20260902-163658.zip`

## Testes

| Suite | Resultado |
|---|---|
| tests/test_alfred_offline.py + test_grok_audit.py | 29 passed |
| tests/test_alfred_acceptance.py | 3 passed (Ollama real) |
| compileall alfred/tests/hermes patches | OK |

## Serviços após `python -m alfred.boot start`

| Serviço | Endpoint | Estado |
|---|---|---|
| Ollama | 127.0.0.1:11434 | qwen3:8b presente |
| Alfred | 127.0.0.1:8791/health | ok, model qwen3:8b |
| Hermes | 127.0.0.1:8777/health | ok, model qwen3:8b |

Browser não foi aberto pelo arranque.
