# Instalação P — EnhancedCore

## Escopo

A Instalação P adiciona `engine/agents/enhanced_core.py`, uma camada opcional que detecta bibliotecas de upgrade sem substituir o núcleo stdlib do AURA. O módulo oferece interfaces para busca DDG, RAG vetorial, HTTPX, APScheduler, faster-whisper e Piper TTS quando essas dependências estiverem instaladas e explicitamente habilitadas.

## Segurança por padrão

A busca web fica desativada até `AURA_ENHANCED_ENABLE_WEB=1`. O RAG vetorial, que pode carregar `chromadb` e `SentenceTransformer`, fica desativado até `AURA_ENHANCED_ENABLE_RAG=1`; isso evita download de modelos durante o import. O scheduler fica desativado até `AURA_ENHANCED_ENABLE_SCHEDULER=1`. O módulo não registra ferramentas no CommandCenter por import: `build_enhanced_tools()` somente é executado quando um integrador o chama explicitamente.

Nenhuma dependência pip foi instalada nesta rodada. Nenhum pacote, modelo, processo, rede, navegador, microfone, câmera, Telegram, Ollama ou autostart foi ativado.

## Validação

O módulo passou em compilação e self-test com as flags de upgrade ausentes. Nesse modo, as APIs web e semântica degradam para listas vazias e as estatísticas registram as capacidades sem ativação de rede, modelo ou scheduler.

## Ativação futura

A ativação deve ser feita individualmente, após auditoria de dependências e decisão explícita. Instale somente o pacote necessário, configure a flag correspondente e valide em ambiente isolado. Não habilite RAG vetorial sem definir o diretório persistente do banco e a política de modelos locais. Não habilite DDG ou outras fontes externas sem revisar privacidade, limites e disponibilidade.

## Reversão

Remova `engine/agents/enhanced_core.py` e este addon. O backup e o estado anterior estão em `.install-backups/installation-p-20260825_100800/`.
