# Operador Humano (WhatsApp/Telegram) + Multi-LLM Router
## AURA QUANT-X HERMES V37.3.38 — Addon C

---

## 1. Regra de ouro

> **O LLM NUNCA decide coordenadas, cliques ou navegação. Ele só decide INTENÇÃO.**
> Coordenadas e fluxos são **macros fixas** mapeadas uma vez.
> Nada é enviado sem **confirmação por voz** (anel 4).

```
❌ ERRADO: LLM → "clique em x=847, y=312..."
✅ CERTO:  LLM/intent → {"skill":"whatsapp_operator","action":"send_message",
                          "args":{"contato":"João","texto":"..."}}
```

---

## 2. Ficheiros novos

| Caminho | Função |
|---------|--------|
| `bridge/jarvis/skills/plugins/whatsapp_operator.py` | Skill modo humano (4 anéis) |
| `bridge/jarvis/skills/plugins/telegram_operator.py` | Idem, `WINDOW_KEYWORD=telegram` |
| `bridge/jarvis/core/llm_router.py` | Roteador de modelos por especialidade |
| `bridge/jarvis/router/voice_skill_bridge.py` | Ponte voz → skill + confirmação |
| `bridge/jarvis/tools/macro_recorder.py` | Grava latências reais da máquina |
| `AURA_ATIVAR_OPERADOR_HUMANO.bat` | Liga flags OPT-IN |

O `whatsapp_sender.py` antigo **permanece** (URI scheme, desligado por defeito). Não é removido.

---

## 3. Ativação (OPT-IN)

```bat
:: Uma vez por sessão (ou no launcher)
set AURA_SKILLS_ENABLED=1
set AURA_WHATSAPP_OPERATOR_ENABLED=1
set AURA_TELEGRAM_OPERATOR_ENABLED=1

:: Ollama — modo criativo com 2 modelos quentes (opcional)
setx OLLAMA_MAX_LOADED_MODELS 2
```

Ou execute: `AURA_ATIVAR_OPERADOR_HUMANO.bat`

Dependências Windows:
```
pip install pyautogui pygetwindow pyperclip pywin32
```

---

## 4. Os 4 anéis de segurança

1. **Foco de janela** — só WhatsApp/Telegram; escudo anti-aposta (bet365, etc.)
2. **Verificação de título** — após Ctrl+F + nome + Enter, o título da janela ativa **deve** conter o token do contato; senão ABORTA e Esc
3. **Clipboard nativo** — texto via pyperclip; arquivo via CF_HDROP (como Ctrl+C no Explorer)
4. **Two-man rule** — skill prepara tudo e devolve `PRONTO PARA ENVIAR...`; só envia se `args["_confirmado_pelo_operador"]=True` (voz: "confirmo" / "pode mandar")

---

## 5. Fluxo de voz

```
Utilizador: "manda pro João: reunião às 15h"
     ↓
VoiceSkillBridge (regex determinístico ou LLM intent)
     ↓
whatsapp_operator.run(send_message, {contato, texto})  # SEM confirmação
     ↓
[Anéis 1-3] → "PRONTO PARA ENVIAR para João..."
     ↓
TTS: "Pronto para enviar para João. Confirma dizendo confirmo, ou cancela."
     ↓
Utilizador: "confirmo"
     ↓
Re-executa com _confirmado_pelo_operador=True → Enter final
```

Integração no `jarvis_voice_server` (antes do VoiceRouter):

```python
from bridge.jarvis.router.voice_skill_bridge import SKILL_BRIDGE

def on_transcript(text: str) -> str:
    spoken = SKILL_BRIDGE.handle(text)
    if spoken is not None:
        return spoken
    from bridge.jarvis.router.voice_router import process_voice_command
    return process_voice_command(text)
```

---

## 6. Multi-LLM Router

```python
from bridge.jarvis.core.llm_router import LLM_ROUTER

model = LLM_ROUTER.select(
    text=user_transcript,
    needs_json=True,  # tool calls / agente
    system_prompt=system_prompt,
)
# keep_alive = LLM_ROUTER.keep_alive_for(model)
```

| Condição | Modelo |
|----------|--------|
| est_tokens > 24k | `llama3.2:3b` |
| needs_json / agente | `qwen2.5:3b-instruct` |
| instrução composta (2+ passos) | `llama3.2:3b` |
| modo trading | `hermes-aura` |
| modo creative | `qwen2.5:3b-instruct` |

VRAM 4050 6GB: em trading, llama sobe on-demand (`keep_alive=0`). Em creative (stack hibernado), `OLLAMA_MAX_LOADED_MODELS=2`.

---

## 7. Calibrar latências (obrigatório na 1ª vez)

```bat
cd C:\aura
python -m bridge.jarvis.tools.macro_recorder
```

Gera `bridge/jarvis/tools/macros_latencies.json` com os sleeps reais da sua máquina/Electron. Os operators leem automaticamente.

---

## 8. Checklist de segurança

- [ ] `AURA_SKILLS_ENABLED` e flags de operador só ligados sob supervisão
- [ ] WhatsApp/Telegram Desktop abertos e logados
- [ ] Nome do contato **exato** como na agenda (primeiro token no título)
- [ ] Nunca automatizar volume alto (risco comportamental)
- [ ] paper_trade / execution_allowed **intocados** por estas skills
- [ ] Anti-bet shield activo (BLOCKED_WINDOW_KEYWORDS)

---

## 9. Teste manual rápido

1. Ativar flags
2. Abrir WhatsApp Desktop
3. Python REPL:

```python
from bridge.jarvis.skills.plugins.whatsapp_operator import Skill
s = Skill()
print(s.run("send_message", {"contato": "SeuNomeTeste", "texto": "ping AURA"}))
# deve devolver PRONTO PARA ENVIAR...
print(s.run("send_message", {
    "contato": "SeuNomeTeste",
    "texto": "ping AURA",
    "_confirmado_pelo_operador": True,
}))
# deve enviar
```
