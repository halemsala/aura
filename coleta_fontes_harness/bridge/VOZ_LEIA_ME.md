# Assistente de Voz (Jarvis) — integrado ao AURA QUANT X

## Arquitetura
A extensão do Chrome não roda GPU/Python diretamente. A voz funciona em duas partes:

1. **bridge/jarvis_voice_server.py** — roda na sua máquina (Python): STT Whisper `base` em CPU/int8 para preservar a RTX 4050, LLM local pelo Ollama/GLM-4 e TTS Edge Neural `pt-BR-AntonioNeural`, com fallback controlado.
2. **extensao/visao/voice-assistant.js** — botão 🎙 no chat do sidepanel; escuta
   contínua automática (sem apertar botão), envia por streaming, toca a resposta
   frase por frase conforme fica pronta.

## Otimizações implementadas
- **Preload**: modelos carregam no start do servidor (`iniciar_voz.bat`), não na
  primeira pergunta. Use `--lazy` se preferir carregar sob demanda.
- **Escuta automática (VAD)**: clique no 🎙 uma vez para ativar "sempre ouvindo".
  Detecta início/fim da fala sozinho (nível de áudio via Web Audio API).
- **Streaming por frase**: a resposta do LLM é sintetizada e tocada frase a
  frase, sem esperar o texto completo — latência percebida bem menor.
- **Wake word opcional**: marque "exigir jarvis" no sidepanel para só responder
  quando a fala começar com a palavra configurada (clique na palavra p/ editar).
- **Sessão isolada por partida**: o histórico de conversa do LLM é mantido por
  `fixtureId` — trocar de partida no capturador não mistura contexto anterior.
- **Perfil GLM-4 explícito para 6 GB**: o `config.yaml` usa `glm4:9b-chat-q4_0`, `num_ctx: 2048` e não baixa modelos automaticamente. Instale conscientemente com `ollama pull glm4:9b-chat-q4_0`. Se a VRAM livre for insuficiente, execute o diagnóstico antes de escolher um fallback menor.

## Instalação (tudo em um só passo)
Não é preciso instalar a voz separadamente. Na raiz do pacote, rode:

  **AURA_INSTALAR_E_INICIAR_TUDO.bat**

Isso instala e sobe Bridge (8080), Engine (8765) e Voz/Jarvis (8099) usando `engine\venv`. A janela **AURA-Voice-8099** precisa ficar aberta enquanto você usa o microfone. O launcher executa `bridge\voice_preflight.py` antes de iniciar e grava falhas em `bridge\runtime_voice.log`; ele não mascara dependências ausentes.

(Opcional) coloque `bridge/jarvis/voices/reference.wav` para clonar uma voz
específica antes de rodar o instalador.

Depois: recarregue a extensão em `chrome://extensions` → sidepanel → CHAT IA →
clique no 🎙 uma vez → fale naturalmente.

## Fluxo
Mic (VAD automático) → WAV → `/api/voice/talk` (streaming) → Whisper (STT) →
Ollama (LLM, por delta) → frase pronta → XTTS (TTS) → áudio tocado → repete até
o fim da resposta.

## Portas usadas
- `8099` — servidor de voz (novo)
- `8080` — bridge de dados existente (inalterado)
- `11434` — Ollama

## Diagnóstico e correção de "IA não responde por voz" (12.5.10+)
Causas reais encontradas e corrigidas nesta versão:
1. **CORS bloqueava a extensão**: o servidor só aceitava a origem
   `https://sokkerpro.com`, mas o sidepanel roda em `chrome-extension://<id>`
   (ID que muda por instalação). O navegador descartava a resposta antes do
   JS ver qualquer coisa → aparecia como "servidor offline" mesmo rodando.
   Corrigido: qualquer origem `chrome-extension://` agora é aceita.
2. **Servidor não escutava durante o carregamento dos modelos**: o preload de
   Whisper+XTTS (1-3 min) rodava ANTES do servidor abrir a porta 8099 —
   `/api/voice/health` dava "conexão recusada" o tempo todo, indistinguível
   de "não está rodando". Corrigido: a porta abre primeiro, os modelos
   carregam em background, e o health responde `loading:true` nesse meio-tempo.
3. **Launchers divergentes usavam venvs diferentes**. O fluxo canônico agora usa `engine\venv\Scripts\python.exe`, e `AURA_RUN_VOICE.bat` executa o preflight de `edge_tts`, `faster_whisper`, `ctranslate2`, `sounddevice`, PyYAML e demais dependências antes de abrir a porta.
4. **Erro de carregamento travava o servidor pra sempre**: se o Ollama não
   estava de pé no exato momento do preload, o servidor marcava erro
   permanente sem tentar de novo. Agora existe `POST /api/voice/reload`
   (também acessível pelo botão **🩺 Testar Voz** no chat) para forçar nova
   tentativa sem reiniciar o processo.

## Botão de teste e diagnóstico (novo)
No chat do sidepanel, clique em **🩺 Testar Voz** para rodar:
- microfone do navegador (permissão + nível de áudio captado);
- alto-falante (toca um bipe de teste);
- servidor de voz (`/api/voice/diagnostic`): STT, TTS, Ollama alcançável,
  modelo LLM instalado, voz de referência.
O resultado aparece como checklist no chat, com sugestão de correção para
cada item que falhar (e o botão **Recarregar motores** quando aplicável).

## Personalização de humor (novo)
Seletor **Humor: Baixo / Médio / Alto** nas configurações de voz do chat:
- **Baixo** — respostas sóbrias, curtas, sem humor, fala mais lenta.
- **Médio** (padrão) — tom cordial, humor leve ocasional.
- **Alto** — tom animado e espirituoso, fala um pouco mais rápida.
A preferência fica salva no navegador e é reenviada em cada requisição de
voz (`mood` no corpo de `/api/voice/talk`, `/chat` e `/tts`) — pode trocar a
qualquer momento, inclusive no meio de uma sessão.

## Solução de problemas
- **"Servidor de voz offline"**: execute `AURA_INSTALAR_E_INICIAR_TUDO.bat` e leia `bridge\runtime_voice.log`; se houver `VOICE_PREFLIGHT_FAIL`, o BAT mestre tenta reparar `engine\venv` automaticamente.
- **Sem áudio de resposta**: verifique se o Ollama está ativo (ícone na
  bandeja) e se o modelo configurado foi baixado (`ollama list`).
- **VAD disparando com ruído de fundo**: ajuste `VAD_THRESHOLD` em
  `voice-assistant.js` (padrão 0.02 — aumente para ambientes ruidosos)
- **Latência alta**: troque `llm.model` em `bridge/jarvis/config.yaml` por um
  modelo menor (`llama3.1:8b` já é leve) ou `stt.model` para `medium`
- **Reset de contexto de uma partida**: `POST /api/voice/reset_session` com
  `{"session_id":"fixture:<id>"}`
- **Erro ficou "preso"**: `POST /api/voice/reload` força nova tentativa de
  carregar os motores sem reiniciar o processo.


## Modo FAST 12.6.3
A rota principal não carrega XTTS-v2. A primeira frase do LLM é enviada imediatamente ao SpeechSynthesis do navegador. XTTS é opcional e não bloqueia o servidor. Na RTX 4050 6 GB isso evita disputa de VRAM entre LLM, Whisper e TTS.


## Ambiente Python oficial (GPU hardened)

Use exclusivamente `engine\venv\Scripts\python.exe` no Windows. Execute `AURA_INSTALAR_E_INICIAR_TUDO.bat`, que instala `requirements.txt` e `bridge\requirements_voice.txt` na mesma venv, valida os imports reais do Voice, verifica o Ollama/GLM-4 e inicia os serviços na ordem. Os launchers individuais ficam em `ARQUIVO_LEGADO\BAT_PS1` e não são necessários para a primeira execução.

Diagnóstico sem modificar o sistema:

```bat
engine\venv\Scripts\python.exe bridge\voice_preflight.py
```
