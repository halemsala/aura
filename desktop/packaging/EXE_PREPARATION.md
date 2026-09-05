# Preparação para o futuro instalador EXE

## Escopo desta etapa

Este documento prepara o produto para um instalador Windows, mas **não gera o EXE**. O código e os contratos desta pasta devem ser validados no Windows antes da escolha da ferramenta de instalação.

## Pacote que o futuro instalador deverá controlar

| Item | Destino futuro | Critério |
|---|---|---|
| `Aura.QuantX.Desktop.exe` | diretório de instalação | shell assinado e compilado x64 |
| `desktop/ui` e `desktop/capture` | recursos do aplicativo | presentes e versionados |
| Bridge/Engine/Voice | runtime privado ou pré-requisito | venv/runtime detectado e health checks aprovados |
| WebView2 Runtime | sistema | detectar e instalar conforme política escolhida |
| perfil WebView2 | `%LOCALAPPDATA%\AURA_QUANT_X\desktop_data` | gravável por usuário, fora da pasta de instalação |
| dados/logs/banco | `%LOCALAPPDATA%\AURA_QUANT_X\data` | migração e backup controlados |
| Ollama/GLM-4 | instalado separadamente | nunca embutir token ou presumir GPU |
| atalhos | Menu Iniciar/Desktop opcional | apontam para o EXE, não para BAT legado |

## Sequência recomendada do instalador

1. Verificar Windows x64 e permissões.
2. Verificar WebView2 Runtime; instalar ou orientar o usuário conforme a política de distribuição escolhida.
3. Instalar os arquivos do aplicativo em diretório protegido.
4. Criar diretórios de dados em `%LOCALAPPDATA%\AURA_QUANT_X`.
5. Verificar Python/runtime ou instalar o runtime privado aprovado.
6. Executar o instalador/reparador backend e validar a venv.
7. Verificar Ollama, conectividade local e `glm4:9b-chat-q4_0`.
8. Executar preflight do Voice.
9. Iniciar Bridge, Engine e Voice em ordem, sem duplicar processos saudáveis.
10. Abrir o shell desktop e mostrar o diagnóstico de primeiro uso.
11. Registrar versão, hashes e resultado de cada etapa.

## Atualização e rollback

Cada atualização deve criar um manifesto de versão, preservar o diretório de dados, executar migrações idempotentes do banco e manter uma cópia da versão anterior até o health check pós-atualização. Se Bridge, Engine, Voice ou WebView2 não responderem, a atualização deve informar a falha e permitir rollback sem apagar o perfil do usuário.

## Assinatura e segurança

O EXE e o instalador devem ser assinados com certificado de código antes da distribuição. O pacote não deve incluir tokens de Telegram, cookies de SokkerPRO, chaves de APIs ou credenciais de Ollama. O app deve manter `allowRealOrders=false`, exibir paper trade e bloquear ações restritas no Gatekeeper.

## Critérios de aceite do EXE

- O aplicativo abre sem extensão Chrome.
- WebView2 está presente e o perfil local é gravável.
- O botão abre SokkerPRO dentro da janela e respeita a lista de hosts permitidos.
- Uma captura válida chega ao Bridge e aparece no estado do Engine.
- Payload incompleto permanece sinalizado e não vira uma decisão inventada.
- Bridge, Engine e Voice são verificados por health check.
- GLM-4 é confirmado pelo nome exato e a falha de Ollama é explícita.
- Microfone, STT, TTS, voz masculina e GPU são testados no Windows compatível.
- Cada agente aparece no Agent Hub local com estado, funções e modo seguro.
- Nenhuma ordem real pode ser criada, aprovada ou enviada.
- Logs, desinstalação, atualização, rollback e migração do banco foram testados.

## Pendências obrigatórias antes de gerar o EXE

A captura genérica precisa ser ajustada ao DOM real do SokkerPRO autenticado. Também é necessário testar o projeto .NET em Windows, fixar a política Evergreen/Fixed Version do WebView2, decidir se o Python será embutido ou pré-requisito e testar a inicialização com a porta 8099 ocupada. O EXE somente deve ser produzido após esses testes.
