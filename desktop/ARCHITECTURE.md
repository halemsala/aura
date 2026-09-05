# AURA QUANT-X Desktop — arquitetura preparada

## Objetivo

Este módulo prepara a migração do AURA QUANT-X de uma extensão Chrome para um aplicativo Windows local. A primeira implementação usa WinForms .NET 8 com WebView2, que fornece um navegador embutido baseado em Chromium e uma ponte segura entre a página e o host nativo.

A referência à experiência Opera é tratada como compatibilidade com o ecossistema Chromium e como direção de experiência de uso. O projeto não incorpora binários, marca, contas, serviços ou código proprietário da Opera.

## Componentes

| Componente | Responsabilidade | Contrato |
|---|---|---|
| `Program.cs` | Entrada do aplicativo e carregamento do contrato desktop | força `paperTradeOnly=true` |
| `MainForm.cs` | Janela, toolbar, status, integração visual e envio de captura | não executa ordens |
| `BrowserHost.cs` | WebView2, host virtual `https://aura.local`, navegação permitida e mensagens | aceita captura somente de host SokkerPRO |
| `ServiceSupervisor.cs` | Inicialização/health check de Bridge, Engine e Voice | nunca encerra processo existente |
| `capture/aura-capture.js` | Adaptador DOM injetado no SokkerPRO | não usa `chrome.runtime` |
| `ui/index.html` | Painel local e Agent Hub | acessa somente contratos locais |
| `config/desktop.json` | Portas, rotas, origins e caminhos | fonte única do shell |
| `update_manual.py` | Reescrita do bloco de notas mestre | não acessa rede nem credenciais |

## Fluxo ponta a ponta

1. O BAT mestre instala/repara a venv e atualiza `MANUAL_SISTEMA_AURA.txt`.
2. A aplicação desktop carrega `desktop/config/desktop.json`.
3. O supervisor verifica Bridge, Engine, Voice e Ollama. Serviço saudável não é duplicado nem encerrado.
4. O WebView2 cria um perfil em `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data` e mapeia `https://aura.local` para `desktop/ui`.
5. O host injeta `desktop/capture/aura-capture.js` em cada documento criado.
6. O adaptador só publica `AURA_SOKKERPRO_CAPTURE` quando existe `window.chrome.webview` e envia payload normalizado, sem usar APIs de extensão.
7. `BrowserHost` valida a origem da mensagem e somente aceita captura de `sokkerpro.com` ou subdomínio.
8. `MainForm` envia o payload ao Bridge em `POST http://127.0.0.1:8080/api/cornerai/feed`.
9. O Bridge normaliza e persiste; o Engine calcula análise/risco; o Voice atende fala e TTS.
10. A UI local consulta saúde e catálogo de agentes. A execução de ações continua submetida ao Gatekeeper e ao paper trade.

## Política de captura

O adaptador tem seletores genéricos e procura estados JSON embutidos comuns. Como o DOM real e os contratos autenticados do SokkerPRO podem mudar, a captura precisa ser validada com uma partida real no Windows. Campos não encontrados permanecem `null`; o adaptador não fabrica estatísticas.

O host não concede permissões genéricas de rede à página. A navegação fica limitada aos hosts configurados em `desktop/config/desktop.json`. Em produção, a lista deve ser revisada com o domínio exato necessário e o WebView2 Runtime deve ser verificado pelo instalador.

## Dados e perfil

O perfil do navegador não deve ficar na pasta de instalação no futuro EXE. A implementação preparada usa `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data`. Tokens e cookies pertencem ao perfil do usuário e não são gravados no repositório. Logs de host ficam em `logs_instalacao\desktop_host.log` durante a preparação; o instalador futuro deverá mover logs e banco para um diretório de dados gravável.

## Compatibilidade legada

A pasta `extensao` permanece para regressão e transição. Ela não é chamada pelo shell desktop e não é requisito para a captura no WebView2. Os BATs individuais continuam preservados no arquivo legado para diagnóstico, mas a entrada recomendada é `AURA_INSTALAR_E_INICIAR_TUDO.bat`.

## Control plane administrativo

A migração Windows reserva o Engine para o control plane em `/api/admin`. O GLM planeja em JSON estruturado; o Policy Gate valida agente, modo, risco e schema; ferramentas mutáveis exigem aprovação humana vinculada ao plano; o executor determinístico registra pós-condição e o ledger hash-chained. O modo inicial é `PLAN_ONLY` e `PAPER TRADE ONLY` é imutável.

A UI desktop consulta `/api/admin/health`, `/api/admin/tools`, `/api/admin/history` e `/api/admin/checkpoints`. A futura interface pode implementar o fluxo `/api/admin/plan` → mostrar plano e risco → `/api/admin/approve` → `/api/admin/execute`, sem dar ao GLM acesso a shell, credenciais, banco bruto ou ordens reais.

## Navegador interno

O `BrowserHost` usa WebView2 e permite somente as origens configuradas em `desktop/config/desktop.json`, incluindo `sokkerpro.com` e subdomínios autorizados. O script nativo de captura envia um envelope normalizado ao Bridge; conteúdo recebido da página é tratado como dado não confiável e não altera a política do AURA. A fonte continua sujeita à sessão do usuário, aos termos de uso e aos limites de coleta.

## O que ainda não está concluído

A etapa atual não gera EXE, não instala WebView2 no computador do usuário, não valida login real, não conhece o DOM autenticado atual do SokkerPRO, não substitui automaticamente todos os painéis da extensão e não testa microfone/GPU/Ollama no Windows. Esses pontos ficam no checklist de `packaging/EXE_PREPARATION.md` e no manual mestre.
