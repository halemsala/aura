# Importação manual de partidas encerradas

## Objetivo

Este modelo serve para reunir partidas já encerradas antes de qualquer processamento pelo AURA. O arquivo não inicia serviços, não altera o Paper-Trading e não alimenta a IA automaticamente.

## Arquivo

Use `historico_partidas_template.csv` como base. Salve uma cópia preenchida em UTF-8, com uma partida por linha.

| Campo | Obrigatório | Regra |
|---|---:|---|
| `fixture_id` | Sim | Identificador único da partida na fonte. Não repetir. |
| `utc_date` | Sim | Data/hora UTC em formato ISO 8601, por exemplo `2026-09-01T19:30:00Z`. |
| `league` | Sim | Campeonato ou competição. |
| `home_team`, `away_team` | Sim | Nomes dos times conforme a fonte. |
| `status` | Sim | Use `FINISHED`; partidas ao vivo ou canceladas não entram. |
| `home_score`, `away_score` | Sim | Placar final inteiro, maior ou igual a zero. |
| `home_corners`, `away_corners` | Recomendado | Escanteios finais inteiros, maior ou igual a zero. |
| `home_yellow_cards`, `away_yellow_cards` | Opcional | Cartões amarelos finais. |
| `home_red_cards`, `away_red_cards` | Opcional | Cartões vermelhos finais. |
| `source` | Sim | Nome da fonte do dado, sem token ou chave de API. |

## Regras de segurança

Não inclua tokens, cookies, chaves, credenciais ou URLs privadas. Não misture partidas ao vivo com partidas encerradas. Não use o placar final para alterar decisões passadas; o resultado deve ser usado somente para resolver o histórico e calibrar o sistema depois que a decisão original estiver registrada.

## Fluxo previsto

1. Coloque o CSV preenchido numa pasta de entrada isolada.
2. O validador verifica colunas, tipos, status, duplicidades e valores impossíveis.
3. Linhas inválidas são rejeitadas e registradas num relatório; não são corrigidas silenciosamente.
4. Somente linhas aprovadas são convertidas em registros históricos.
5. O `FeedbackConnector` compara os resultados com as decisões armazenadas e gera relatório de TP, FP, TN e FN.
6. A memória/calibração é atualizada sem liberar execução real: `paper_trade=true` e `execution_allowed=false`.

Este primeiro modelo ainda não executa a importação no AURA. Ele é a etapa de preparação para evitar que dados incompletos ou duplicados contaminem a memória do sistema.
