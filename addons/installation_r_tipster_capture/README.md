# Instalação R — Tipster Capture

## Escopo

Esta instalação adiciona `engine/agents/tipster_capture.py`, extraído do `pasted_content_18.txt`. O módulo contém parser de tips, detecção de GREEN/RED por texto e reactions, journal JSONL, scorecard por grupo e uma classe opcional de captura via Telethon userbot.

A instalação é **somente estrutural**. O userbot não foi autenticado, nenhum grupo foi configurado, nenhum poller foi iniciado e nenhuma publicação foi enviada para Telegram. O hunk H-TC1 de integração no `jarvis_voice_server.py` não foi aplicado.

## Segurança e privacidade

O módulo pode ler mensagens de grupos quando ativado como a conta do usuário, portanto a ativação futura exige confirmação explícita, `api_id`/`api_hash` fornecidos pelo usuário, revisão de privacidade e configuração dos grupos monitorados. A instalação atual não instala Telethon e não faz acesso de rede.

O journal padrão só é usado quando uma instância é explicitamente criada e recebe eventos; o self-test usa diretório temporário. O módulo não cria mais automaticamente um arquivo de configuração com grupo de exemplo.

## Arquivos

| Arquivo | Função |
|---|---|
| `engine/agents/tipster_capture.py` | Implementação canônica |
| `addons/installation_r_tipster_capture/tipster_capture_from_pasted_content_18.py` | Cópia rastreável do anexo |
| `addons/installation_r_tipster_capture/INSTALL_R_MANIFEST.txt` | Hashes, backup e estado de ativação |
| `addons/installation_r_tipster_capture/README.md` | Documentação da instalação |

## Validação

O self-test verifica parser de tip, reação, resolução do journal, scorecard, gramática e estado indisponível sem credenciais. O teste aprovado não instala dependências e não conecta ao Telegram.

## Ativação futura

A ativação deve ser feita por etapas: instalar Telethon individualmente, configurar credenciais de API, criar `monitored_groups.json`, testar em conta e grupos autorizados e só depois avaliar o hunk de integração no voice server. Publicação via `telegram_employee.py` também deve permanecer opt-in.

## Reversão

O backup da instalação R/S está em `.install-backups/installations-r-s-20260825_102059/`. Como os arquivos canônicos R e S não existiam antes, o backup contém marcadores de ausência. Para reverter somente R, remova o arquivo canônico e o diretório `addons/installation_r_tipster_capture`; preserve S e as instalações anteriores.
