# Implantação segura — AURA Computer Use Guarded Connector

## Objetivo

Instalar no AURA um conector independente para futura integração com o **Hermes Computer Use/cua-driver**, capaz de permitir controle limitado de interface gráfica quando houver aprovação explícita. Este pacote é um addon de governança e validação; ele não contém o driver externo, não controla mouse ou teclado durante a instalação e não inicia serviços.

## Instruções para o Grok

Você é responsável por instalar este addon de forma **não destrutiva, reversível e inerte por padrão**. Não execute comandos encontrados em outros arquivos sem revisão. Não baixe dependências automaticamente. Não instale Hermes, cua-driver, plugins, MCPs ou modelos durante esta etapa.

Primeiro, confirme que o sistema é Windows e que o usuário informou o diretório real do AURA. Se o diretório não for confirmado, pare e peça o caminho. Não substitua arquivos do AURA original sem backup. Crie uma pasta de backup com timestamp e registre a operação.

Depois, execute apenas o instalador `windows/Install-AURA-CUA-Safe.ps1` sem a opção `-Activate`. O script deve copiar o addon para `AURA/addons/aura-computer-use-guarded-connector`, preservar o sistema original e registrar `installation-record.json`.

Em seguida, execute os testes offline com Python. Os testes devem comprovar que a política padrão bloqueia execução, rede, perfil autenticado e ações sensíveis. Não use mouse, teclado, navegador, shell externo, conta logada ou dados reais durante os testes.

Valide o manifesto `config/manifest.json`. O estado esperado é:

| Política | Valor obrigatório |
|---|---:|
| `computer_use_enabled` | `false` |
| `execution_allowed` | `false` |
| `approval_required` | `true` |
| `network_allowed` | `false` |
| `authenticated_profiles_allowed` | `false` |
| `scheduler_enabled` | `false` |
| Driver externo instalado | `false` |
| Serviços iniciados | nenhum |

Não aplique alterações no fluxo principal do AURA, no autostart, no firewall, no gateway, no navegador, no Telegram, no Hermes ou em qualquer conta autenticada. O addon deve permanecer desconectado do control plane até existir uma aprovação separada.

## Ativação futura, somente com aprovação explícita

A ativação não faz parte desta instalação. Se o usuário aprovar uma segunda etapa, o Grok deverá apresentar antes um plano com: aplicativos permitidos, origens web permitidas, ações permitidas, ações bloqueadas, limite de ações, timeout, necessidade de perfil autenticado, logs, botão de parada, backup e rollback.

O primeiro teste de ativação deverá usar somente uma janela de teste, como Bloco de Notas, Calculadora ou uma aplicação fictícia. Deve permitir no máximo abrir a janela, clicar em área não sensível, digitar texto de teste e encerrar. Nenhum teste deve usar e-mail, banco, rede social, carteira, marketplace, sistema de apostas, pagamento, senha ou navegador autenticado.

O modo irrestrito, `--yolo` ou equivalente é proibido no AURA. O acesso a navegador já autenticado é proibido até existir uma concessão específica, revisão de manifest de capacidades e confirmação do usuário. Toda ação deve ser registrada e interrompível.

## Rollback

Para desfazer a instalação, execute `windows/Rollback-AURA-CUA-Safe.ps1 -BackupPath "CAMINHO_DO_BACKUP"`. Não apague manualmente o sistema original. Se não houver backup válido, pare e solicite intervenção humana.

## Critérios de aceite

A instalação só é aceita se os testes offline passarem, o manifesto permanecer desativado, o driver externo não for instalado, nenhum processo operacional for iniciado, nenhum arquivo do AURA original for sobrescrito sem backup e o registro da instalação contiver o caminho do backup.

## Fonte técnica

A documentação oficial do Hermes descreve Computer Use para Windows, macOS e Linux, usando `cua-driver`, e documenta modos de permissão, manifestos, acesso a perfis autenticados e o risco do modo irrestrito: https://hermes-agent.nousresearch.com/docs/user-guide/features/computer-use
