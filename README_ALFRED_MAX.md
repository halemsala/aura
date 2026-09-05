# ALFRED MAX para Aura/Hermes

Este pacote implementa uma camada local inspirada nas capacidades descritas publicamente na página do ALFRED VISION: comandos por voz/texto, execução de várias tarefas, memória local, captura de tela/câmara, escrita na janela activa e automações Windows. A página é promocional e não revela o código interno; este pacote implementa capacidades equivalentes de forma independente e não copia aulas, código ou materiais protegidos.

## Conteúdo

| Ficheiro | Função |
|---|---|
| `alfred_capabilities.py` | Núcleo local, parser, memória, API HTTP e executores seguros. |
| `alfred_install.py` | Integra o prefixo `Alfred` no router `scripts/aura_chat_agents.py`, com backup. |
| `AURA_ALFRED_MAX.bat` | Verifica, instala a ponte e inicia a API em `127.0.0.1:8791`; não abre navegador. |
| `AURA_ALFRED_STOP.bat` | Termina apenas o processo ALFRED registado pelo próprio pacote. |
| `alfred_config.json` | Configuração declarativa de modelo, limites e allowlist. |

## Instalação

Copie os ficheiros para a raiz de `C:\aura`, mantendo `alfred_capabilities.py` e `alfred_install.py` ao lado de `engine`, `bridge`, `hermes_v10` e `scripts`. Execute `AURA_ALFRED_MAX.bat`. Em sucesso a janela fecha-se; em erro permanece aberta para leitura. O BAT não abre o chat nem qualquer página web. Antes de iniciar o serviço, verifica `/api/tags` e executa uma inferência real com `qwen3:8b`; se o modelo falhar, o arranque é interrompido e a janela fica aberta com o diagnóstico.

O resultado do teste fica em `logs_supervisor\\alfred_qwen3_test.json`. A ponte deve ser carregada reiniciando o Hermes depois da instalação. O processo ALFRED fica apenas em loop HTTP, não faz polling do navegador nem abre relatórios. Para parar, execute `AURA_ALFRED_STOP.bat`.

## Exemplos directos

Sem `--execute`, o núcleo faz apenas plano/dry-run:

```bat
python alfred_capabilities.py --command "Alfred, cria uma pasta chamada Curso e abre três pesquisas sobre automação"
```

Para executar os efeitos explicitamente:

```bat
python alfred_capabilities.py --command "Alfred, cria uma pasta chamada Curso e abre três pesquisas sobre automação" --execute
```

A API local usa JSON:

```bat
curl -X POST http://127.0.0.1:8791/command -H "Content-Type: application/json" -d "{\"command\":\"Alfred, cria uma pasta chamada Curso\",\"execute\":true}"
```

No chat Hermes, use comandos começados por `Alfred`. Um comando que abre uma URL é explícito e pode executá-la; criação de pastas, organização do Desktop, escrita na janela activa e memória exigem palavras explícitas como `executa`, `faz agora`, `pode fazer` ou `AUTORIZO`. Sem essas palavras, o assistente devolve o plano e não altera o computador.

## Capacidades e limites

A organização do Desktop só move ficheiros directamente no Desktop para `Desktop\Organizado_AURA`, não apaga ficheiros e limita o plano a 100 itens. A escrita usa clipboard e `pyautogui`, se esses pacotes estiverem instalados. A captura de tela usa `pyautogui`; a câmara usa OpenCV. A captura não é automaticamente interpretada pelo Qwen3 porque `qwen3:8b` é um modelo de texto. Para interpretação visual real, é necessário instalar um modelo Ollama multimodal que caiba na VRAM e defini-lo em `alfred_config.json`; o núcleo não inventa uma descrição quando não existe modelo de visão.

A memória fica em `data\alfred\memory.json` e as acções em `data\alfred\actions.jsonl`. Tudo fica local. Não são recolhidas credenciais, não há shell arbitrário, não há eliminação de ficheiros, não há compras, apostas, transferências nem modo live.

> O ALFRED MAX amplia a capacidade operacional do Aura/Hermes, mas não torna um modelo local de 8B omnisciente. A qualidade conversacional e a visão dependem dos modelos instalados; os limites de segurança são deliberados para impedir que um comando mal interpretado altere o sistema inteiro.

## Integração e rollback

O instalador cria um backup ao lado de `scripts\aura_chat_agents.py` com sufixo `.alfred-backup-AAAAMMDD_HHMMSS`. Para remover a integração, pare o ALFRED, restaure o backup mais recente e reinicie o Hermes. Os logs ficam em `logs_supervisor\alfred_install.log` e `data\alfred\actions.jsonl`.
