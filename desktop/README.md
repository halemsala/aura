# AURA QUANT-X Desktop

Este diretório contém a **preparação** do aplicativo Windows local. Ele ainda não é um EXE e não substitui os testes reais no Windows.

## O que já está preparado

O projeto `Aura.Desktop.csproj` define um aplicativo WinForms .NET 8 x64 com Microsoft WebView2. A janela carrega a Operator OS local na raiz do host virtual, consulta Bridge/Engine/Voice, mostra o catálogo dos agentes, permite abrir o SokkerPRO dentro da própria janela e encaminha capturas por uma ponte nativa. O capturador não depende de `chrome.runtime` nem de uma extensão Chrome.

O supervisor consulta os serviços e preserva processos que já estejam saudáveis. A inicialização controlada é feita pelo atalho criado pelo BAT unificado; a abertura direta do EXE não inicia Ollama nem backends. Falhas de serviço aparecem no painel e em `logs_instalacao\desktop_host.log`; o host não mata processos automaticamente.

## Pré-requisitos para compilar no Windows

Instale o .NET 8 SDK x64, o WebView2 Runtime e prepare o backend AURA pela entrada única `AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat`. O build de preparação pode ser executado com:

```powershell
dotnet restore .\desktop\Aura.Desktop.csproj
dotnet build .\desktop\Aura.Desktop.csproj -c Release -p:Platform=x64
```

Esses comandos apenas compilam o shell; não criam o instalador EXE final.

## Execução de desenvolvimento

Após compilar no Windows, execute o binário a partir da raiz do pacote ou copie `desktop`, `bridge`, `engine`, `agents`, `extensao` e os arquivos de configuração necessários para o diretório de saída mantendo os caminhos relativos. A janela abre a Operator OS e apenas consulta o estado dos serviços; ela não inicia Ollama nem outros processos automaticamente.

Para verificar o contrato sem abrir a UI, execute:

```powershell
& .\engine\venv\Scripts\python.exe .\desktop\update_manual.py --root .
```

## Migração da captura

A URL inicial é `https://aura.local/index.html`, que hospeda o build Operator OS armazenado fisicamente em `desktop/ui/matriz_v22` dentro do WebView2. O botão **Abrir SokkerPRO** navega para o domínio dentro do WebView2. O host injeta `desktop\capture\aura-capture.js`, valida a origem e envia JSON para `POST http://127.0.0.1:8080/api/cornerai/feed`.

A captura preparada é um adaptador genérico. O teste de produção precisa confirmar os seletores e estados JSON do SokkerPRO autenticado. Se o site alterar o DOM, atualize o capturador e reescreva o manual mestre.

## Entrada única do usuário

A instalação e a validação passam por `AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat`, sem perguntas. Na primeira execução ele instala, verifica e cria `AURA QUANT-X V25.lnk`; o atalho inicia o núcleo local controlado e abre a Operator OS. Os BATs individuais permanecem arquivados em `ARQUIVO_LEGADO\BAT_PS1`.
