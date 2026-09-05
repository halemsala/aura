# Instalação O — Football Research Hub e mapa de pressão

Esta instalação adiciona `engine/agents/football_research_hub.py`, um meta-pesquisador que consulta, quando chamado explicitamente, Crossref, arXiv, GitHub, Wikipedia, DuckDuckGo e conhecimento local em paralelo, além de `MatchMap`, que transforma métricas agregadas do jogo em um mapa ASCII de pressão territorial.

O mapa é deliberadamente descrito como **intensidade estatística por zona**, não como posição real de jogadores. Dados de tracking não fazem parte deste módulo.

## Segurança e operação

O import não faz chamadas de rede. As consultas externas só ocorrem quando `FootballResearchHub.search()` ou `run_research_campaign()` são invocados. A integração com `jarvis_voice_server.py` e a cadeia global de parsers não foi aplicada; os comandos `meta_pesquisa`, `campanha_pesquisa` e `mapa_jogo` não ficam ativos no servidor até uma ativação futura explícita.

O módulo não contém stake, carteira, aposta ou execução financeira. O mapa e as pesquisas são informativos e compatíveis com `PAPER_TRADE=true`, `EXECUTION_ALLOWED=false` e `GLM_ADVISORY_ONLY=true`.

## Validação

O self-test isolado passou com dados falsos, cobrindo cálculo do mapa, detecção de domínio, ritmo de cantos, ranking de múltiplas fontes, aprendizado no ToolKnowledge, gramática e registro em CommandCenter. Nenhuma fonte externa foi consultada durante o teste.

## Reversão

Remova `engine/agents/football_research_hub.py` e este diretório de addon. O backup independente encontra-se em `.install-backups/installation-o-20260825_090500/`. Não remova instalações A–N nem o addon D separado.
