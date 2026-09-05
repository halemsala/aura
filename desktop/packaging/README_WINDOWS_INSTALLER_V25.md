# Instalador Windows do AURA QUANT-X V25

## Estado atual

O projeto do instalador está pronto para compilação reproduzível em Windows x64. O sandbox usado nesta sessão é Linux e não possui Inno Setup, SDK .NET 8 para WinForms ou WebView2 Runtime; por isso o `Setup.exe` Windows não foi falsamente declarado como compilado aqui.

## Pré-requisitos para gerar o EXE

No Windows x64, instale o .NET 8 SDK, o Inno Setup 6+ e o Microsoft Edge WebView2 Runtime Evergreen. A política de distribuição do WebView2 é de pré-requisito: o instalador verifica o Runtime nas chaves oficiais do Evergreen Runtime e bloqueia a instalação quando ele não está presente. A detecção usa o valor `pv` em `{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` e exige versão superior a `0.0.0.0`. Não são incluídos tokens, cookies, chaves de API, credenciais de Telegram, modelo Ollama ou dados do usuário.

## Instalação temporária sem Inno Setup

Enquanto o Inno Setup não estiver instalado, use `AURA_INSTALAR_TEMPORARIO_SEGURO.bat` na raiz do pacote. Ele copia o sistema para `%LOCALAPPDATA%\AURA_QUANT_X\portable`, não inicia serviços, não instala dependências, não baixa modelos e não cria um desinstalador formal. A documentação completa está em `docs\INSTALACAO_TEMPORARIA_BAT_SEGURA.md`.

```bat
AURA_INSTALAR_TEMPORARIO_SEGURO.bat
```

Essa é uma instalação portátil temporária; o `Setup.exe` continua sendo necessário para instalação formal, atalhos, desinstalação e rollback.

## Build

Abra PowerShell na raiz do pacote e execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\desktop\packaging\BUILD_WINDOWS_INSTALLER.ps1
```

Também é possível usar o wrapper de duplo clique, que agora está em ASCII/CRLF para evitar comandos truncados no CMD:

```bat
desktop\packaging\BUILD_WINDOWS_INSTALLER.bat
```

Se o Inno Setup estiver instalado em caminho não padrão, passe o caminho completo para o `ISCC.exe` como primeiro argumento:

```bat
desktop\packaging\BUILD_WINDOWS_INSTALLER.bat "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

O script executa `dotnet restore`, publica o shell `win-x64` autocontido em `desktop\publish`, valida o EXE e os recursos `config\desktop.json`, `capture\aura-capture.js` e `ui\index.html`, compila `AURA_Setup.iss` com Inno Setup e gera `dist_installer\installer-build.json` e o hash `.sha256`.

Se o Inno Setup estiver em um caminho não padrão e você executar diretamente o PowerShell:

```powershell
.\desktop\packaging\BUILD_WINDOWS_INSTALLER.ps1 `
  -InnoSetupPath 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

O script também aceita a variável de ambiente `INNO_SETUP_PATH` e procura `ISCC.exe` no `PATH`, em `Program Files (x86)`, em `Program Files` e em `%LOCALAPPDATA%\Programs`. A lista de exclusões do Inno Setup usa a sintaxe oficial separada por vírgulas e remove backups, legado, caches, logs, bytecode e archives históricos.

## Comportamento durante a instalação

O Setup instala o shell Desktop e o backend em `C:\Program Files\AURA_QUANT_X`, cria dados e logs em `%LOCALAPPDATA%\AURA_QUANT_X` e cria atalhos para `Aura.QuantX.Desktop.exe`. O Setup não inicia Bridge, Engine, Voice, Telegram, Ollama, compute, microfone, câmera ou autostart.

O único comando pós-instalação é o launcher `AURA_ABRIR_DESKTOP_SEGURO.bat`, que executa preflight local e abre o shell. Ele não chama `AURA_INICIAR_SISTEMA.bat` e não inicia processos backend.

O launcher manual `AURA_INICIAR_SISTEMA.bat` agora exige confirmação explícita antes de ligar Ollama, Bridge, Engine e Voice. O instalador mestre `AURA_INSTALAR_E_INICIAR_TUDO.bat` também exige confirmação explícita antes de criar venv, fazer downloads ou inicializar serviços.

## Teste recomendado

Antes de distribuir, instale em uma VM Windows limpa. Teste primeiro sem WebView2 para confirmar que o Setup bloqueia com uma mensagem clara. Depois instale WebView2, execute o Setup, abra o Desktop, confirme que o perfil é gravável em `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data` e verifique no Gerenciador de Tarefas que nenhum backend foi iniciado.

Em seguida, execute o Final Check rápido. Teste atualização, desinstalação e rollback sem apagar `%LOCALAPPDATA%\AURA_QUANT_X`. Somente após uma decisão explícita, execute o launcher de serviços e valide as portas 8080, 8765 e 8099.

## Falhas corrigidas no fluxo anterior

O template anterior usava versão V22, caminho `desktop\bin`, publicação framework-dependent, referências opcionais frágeis e ações `[Run]` que chamavam reparo/serviços automaticamente. A versão V25 usa `desktop\publish`, shell autocontido por padrão, WebView2 verificado com chave oficial, dados fora do diretório protegido, hash do artefato, launcher seguro, wrapper ASCII/CRLF e nenhuma inicialização automática de backend.

## Rollback

Cada atualização deve manter a versão anterior e o diretório de dados. O backup específico desta auditoria está em `.install-backups/installer-hardening-20260825_094500/`. A reversão não deve apagar `%LOCALAPPDATA%\AURA_QUANT_X` sem consentimento explícito.

## Limitações honestas

A compilação do WinForms e o teste do WebView2, UAC, GPU, câmera, microfone, portas ocupadas, instalação do Runtime e assinatura de código só podem ser validados em Windows. O EXE final deve ser assinado com certificado de código antes da distribuição.
