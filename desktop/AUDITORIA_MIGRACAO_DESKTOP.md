# Auditoria da migração AURA QUANT-X para Windows Desktop

**Build:** AURA-WINDOWS-DESKTOP-PREP-1  
**Escopo:** preparar o sistema para um aplicativo Windows local com navegador embutido e futuro instalador EXE; não gerar o EXE nesta etapa.

## Conclusão executiva

A base desktop foi preparada sem remover a extensão Chrome legada. O novo caminho usa um shell WinForms .NET 8 x64 com WebView2, host virtual local `https://aura.local`, perfil de usuário isolado, ponte de mensagens e capturador sem `chrome.runtime`. Bridge, Engine e Voice continuam como serviços locais e são supervisionados por health checks.

A expressão “baseado no Opera” foi convertida em uma decisão técnica segura: usar uma experiência compatível com Chromium, sem redistribuir executáveis, marca, serviços ou código proprietário da Opera. A Opera informa que usa Chromium desde 2013 [1]. Para o primeiro caminho Windows, WebView2 reduz a quantidade de código nativo de navegador; CEF permanece alternativa quando for necessário distribuir e controlar um Chromium próprio [2].

## Matriz de estado

| Área | Estado | Evidência |
|---|---|---|
| Manual mestre TXT | Implementado | `MANUAL_SISTEMA_AURA.txt` e `desktop/update_manual.py` |
| Registro permanente | Implementado | `desktop/MANUAL_UPDATE_POLICY.txt` e `desktop/REGISTRO_ATUALIZACOES.md` |
| Entrada única do backend | Implementado | `AURA_INSTALAR_E_INICIAR_TUDO.bat` reescreve o manual após criar a venv |
| Shell Windows | Preparado | `desktop/Aura.Desktop.csproj`, `Program.cs`, `MainForm.cs` |
| Navegador embutido | Preparado | `BrowserHost.cs` usa WebView2 e host virtual |
| Captura sem extensão | Preparado | `desktop/capture/aura-capture.js` não usa APIs `chrome.runtime` |
| Contrato Bridge | Validado estaticamente | schema `cornerai-analyst-1` e teste `view_to_skill_pack` |
| Menus individuais dos agentes | Preparado | catálogo de 34 agentes com funções, ações e estado |
| Paper trade | Forçado | JSON, `Program.cs`, catálogo e manifesto EXE definem `allowRealOrders=false` |
| WebView2 Runtime | Pendente Windows | precisa ser detectado/instalado pelo futuro instalador |
| DOM autenticado do SokkerPRO | Pendente Windows | seletores genéricos precisam de teste em uma partida real |
| Build .NET | Pendente Windows | sandbox não possui `dotnet` nem WebView2 |
| Instalador EXE | Não iniciado por escopo | somente manifesto e checklist foram preparados |

## Fluxo preparado

O usuário executa `AURA_INSTALAR_E_INICIAR_TUDO.bat`. O BAT instala/repara o backend, atualiza `MANUAL_SISTEMA_AURA.txt`, verifica Ollama/GLM-4, sobe Bridge na porta 8080, Engine na 8765 e Voice na 8099, aguardando health checks.

No modo desktop, o shell inicia com um perfil em `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data`, abre o painel local e permite navegar ao SokkerPRO. O capturador é injetado pelo host WebView2. Mensagens de captura são aceitas pelo host somente quando a origem é `sokkerpro.com` ou subdomínio; o JSON é enviado ao Bridge em `POST /api/cornerai/feed`. Valores ausentes permanecem nulos e o normalizador do Bridge decide se o feed é utilizável.

## Funções e conexões catalogadas

O manual mestre lista serviços, portas, ferramentas, dependências, agentes, funções, captura, Ollama, voz, TTS, STT, Telegram opcional, extensão legada e critérios do futuro EXE. O catálogo desktop deriva dos 34 agentes do manifesto e do relatório de auditoria, incluindo funções runnable, funções gerais, ações `status`/`inspect`/`run_function`/`health` e indicação `inspect_only` quando aplicável.

## Segurança e dados

O shell não encerra processos existentes automaticamente, não grava credenciais no código e força paper trade no carregamento da configuração. O futuro instalador deve manter cookies/tokens no perfil do usuário, dados e logs em `%LOCALAPPDATA%`, preservar o banco durante upgrades e assinar os binários antes da distribuição.

## Validações executadas no sandbox

Os testes do contrato desktop passaram com **7 testes**. A validação cobre configuração, portas, modelo alvo, catálogo dos 34 agentes, ausência de chamadas reais de `chrome.runtime` no capturador, normalização de um payload `cornerai-analyst-1`, sintaxe Python, contrato C# por inspeção textual e presença dos arquivos obrigatórios. `node --check` passou para o JavaScript da UI.

A execução real do WebView2, do .NET, do login SokkerPRO, do Ollama, da RTX 4050, do microfone e dos serviços Windows não foi afirmada, pois esses componentes não existem no sandbox Linux.

## Referências

[1]: https://blogs.opera.com/news/2025/01/opera-joins-supporters-of-chromium-based-browsers-open-source-ecosystem/ "Opera — Chromium-Based Browsers"
[2]: https://chromiumembedded.github.io/cef/ "Chromium Embedded Framework Documentation"
[3]: https://learn.microsoft.com/en-us/microsoft-edge/webview2/ "Microsoft Learn — Introduction to WebView2"
[4]: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution "Microsoft Learn — Distribute your app and the WebView2 Runtime"
