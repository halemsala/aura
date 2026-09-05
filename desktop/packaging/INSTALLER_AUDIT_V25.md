# Auditoria do instalador Windows — AURA QUANT-X V25

## Conclusão

O pacote agora contém um fluxo de instalador Windows reproduzível, mas o `.exe` final ainda precisa ser compilado em Windows. O sandbox atual é Linux e não possui Inno Setup, Wine, `dotnet` SDK Windows ou ambiente WinForms, portanto não seria correto declarar um executável Windows como compilado e validado aqui.

O fluxo foi preparado para produzir um `AURA_QUANT_X_Setup_V25_x64.exe` quando executado em Windows x64 com .NET 8 SDK, Inno Setup 6+ e WebView2 Runtime disponível.

## Falhas encontradas no fluxo anterior

| Falha | Impacto | Correção |
|---|---|---|
| Script Inno Setup identificado como template V22 e sem build binário | Versão e artefato não correspondiam ao V25 | `AURA_Setup.iss` atualizado para V25 e nome de saída determinístico |
| Publicação usava `desktop\bin` e `--self-contained false` | Dependência de .NET no PC e caminho inconsistente | `PUBLISH_WINDOWS.ps1` passou a usar `desktop\publish`, `win-x64` e publicação autocontida por padrão |
| `[Run]` iniciava reparo/serviços automaticamente | Risco de iniciar Bridge, Engine, Voice e Ollama durante a instalação | `[Run]` agora abre somente o shell Desktop pelo launcher seguro |
| `AURA_INICIAR_SISTEMA.bat` iniciava Ollama, fazia pull do modelo e iniciava serviços | Autostart, rede local e download pesado sem decisão explícita | Não é chamado pelo instalador; permanece disponível como ação manual documentada |
| WebView2 era pré-requisito implícito | Shell poderia instalar e falhar na primeira abertura | `PrepareToInstall` bloqueia o setup quando o Runtime não é detectado |
| Payload não separava dados do usuário | Atualizações poderiam misturar perfil e logs com arquivos do programa | Diretórios `%LOCALAPPDATA%\AURA_QUANT_X` são criados e preservados na desinstalação |
| Ausência de fluxo reproduzível de compilação | Necessidade de editar o `.iss` manualmente | `BUILD_WINDOWS_INSTALLER.ps1` automatiza publish, validação, ISCC e hash |
| Nenhuma validação de rollback específica do Setup | Risco de perder arquivos durante atualização | Backup final de hardening e manifestos permanecem fora do payload distribuível |
| Versão do manifesto apontava para preparação antiga | Auditoria do pacote podia usar caminhos históricos | Manifesto e documentação devem ser atualizados juntamente com cada build |
| Wrapper `.bat` podia exibir comandos truncados após transferência/encoding | Diagnóstico pouco claro no CMD | Wrapper reescrito em ASCII com CRLF; aceita `ISCC.exe` como argumento, pelo `PATH` ou em caminhos padrão |
| PowerShell podia exibir acentos como `nÃ£o` em Windows PowerShell 5.1 | Mensagens de erro ilegíveis | Scripts PowerShell salvos em UTF-8 com BOM e erro do Inno Setup normalizado em ASCII |
| GUID do WebView2 não correspondia à chave oficial Evergreen | Setup poderia bloquear máquinas com Runtime instalado | GUID atualizado para `{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` e `pv` validado com `StrToVersion`/`ComparePackedVersion` |
| `Excludes` usava ponto e vírgula | Arquivos históricos poderiam não ser excluídos pelo compilador | Padrões convertidos para a sintaxe oficial separada por vírgulas |

## Arquitetura instalada

O instalador copia o shell publicado para `desktop\publish`, a árvore do AURA para `{app}`, cria os diretórios de dados em `%LOCALAPPDATA%\AURA_QUANT_X` e cria atalhos para o EXE. O backend não é iniciado pelo setup. O launcher `AURA_ABRIR_DESKTOP_SEGURO.bat` executa apenas preflight local e abre o shell, mantendo Bridge, Engine, Voice, Telegram, Ollama e compute desligados.

## Critérios de aceite antes da distribuição

1. Executar `desktop\packaging\BUILD_WINDOWS_INSTALLER.ps1` em Windows x64.
2. Confirmar `dotnet publish` sem erros e existência do EXE e dos recursos `config\desktop.json`, `capture\aura-capture.js` e `ui\index.html` junto ao binário.
3. Instalar em uma VM limpa com WebView2 Runtime e confirmar que o setup bloqueia corretamente quando o Runtime estiver ausente.
4. Abrir o Desktop e verificar o perfil WebView2 em `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data`.
5. Confirmar que a instalação não cria processos de Ollama, Bridge, Engine, Voice ou Telegram.
6. Executar os backends manualmente somente depois de uma decisão explícita e validar os health checks nas portas 8080, 8765 e 8099.
7. Testar atualização, desinstalação e rollback preservando `%LOCALAPPDATA%\AURA_QUANT_X`.
8. Assinar o EXE e o instalador com certificado de código antes da distribuição.

## Pré-requisitos que não podem ser simulados no sandbox Linux

O teste real do WinForms/WebView2, `dotnet publish`, instalação do WebView2 Evergreen, comportamento de UAC, atalhos, desinstalador, GPU, microfone, câmera e portas ocupadas exige Windows. Também não há como embutir honestamente Ollama, modelo GLM, credenciais Telegram, cookies do SokkerPRO ou tokens de APIs no instalador.

## Política de segurança

O instalador e o launcher não executam ordens reais, não habilitam apostas, não ativam autostart e não armazenam tokens. As invariantes do pacote permanecem `PAPER_TRADE=true`, `EXECUTION_ALLOWED=false` e `GLM_ADVISORY_ONLY=true`. Integrações de Telegram, fontes externas, voz, câmera e compute permanecem opt-in.

## Comando de build no Windows

```powershell
cd C:\caminho\AURA_QUANT_X_12.7.0_V25_INSTALLER_FIXED
desktop\packaging\BUILD_WINDOWS_INSTALLER.ps1
```

Para usar um `ISCC.exe` não localizado automaticamente:

```powershell
desktop\packaging\BUILD_WINDOWS_INSTALLER.ps1 -InnoSetupPath 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

Ou pelo wrapper corrigido:

```bat
desktop\packaging\BUILD_WINDOWS_INSTALLER.bat "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

O resultado será salvo em `dist_installer\`, acompanhado de `installer-build.json` e do arquivo `.sha256`. Se o erro `Inno Setup 6 was not found` persistir, o Inno Setup ainda não está instalado ou o caminho informado não aponta para `ISCC.exe`.

## Estado desta auditoria

A auditoria estrutural do código Python e a auditoria específica do instalador passaram após a revalidação das fontes, manifestos, encoding, detecção de WebView2, exclusões e wrappers. O wrapper foi verificado como ASCII/CRLF, a detecção de `ISCC.exe` foi ampliada e a auditoria terminou como **preparada para build Windows**, não como `.exe` já compilado. O ambiente Linux desta sessão continua sem `dotnet`, Inno Setup, PowerShell Windows, Wine e WebView2.

**Autor:** Manus AI
