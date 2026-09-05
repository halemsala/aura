# AURA — Mapa do Sistema
_Gerado em 2026-08-31 01:04_

## Servicos & Portas

| Porta | Servico | Definido em |
|---|---|---|
| 1024 | (desconhecido — catalogar!) | addons/aura-grid-voluntary/code/aura_grid/codec.py, bridge/jarvis/modules/device.py, bridge/jarvis/modules/neural_tts.py |
| 1200 | (desconhecido — catalogar!) | addons/installation_s_intent_router/intent_router_from_pasted_content_19.py, engine/agents/intent_router.py |
| 1234 | (desconhecido — catalogar!) | engine/agents/voice_auth.py |
| 1600 | (desconhecido — catalogar!) | scripts/aura_voice_client.py |
| 1800 | (desconhecido — catalogar!) | scripts/aura_mora_daily_trigger.py |
| 2000 | (desconhecido — catalogar!) | engine/core/cache_integration.py, engine/core/mc_grid.py, scripts/aura_admin_core.py |
| 3000 | (desconhecido — catalogar!) | engine/server.py, scripts/aura_voice_client.py, scripts/hermes_knowledge.py |
| 3600 | (desconhecido — catalogar!) | addons/installation_r_tipster_capture/tipster_capture_from_pasted_content_18.py, addons/telegram_intel_optin/src/telegram_intel/policy_gate.py, bridge/telegram/tg_dependencies.py |
| 4050 | (desconhecido — catalogar!) | addons/installation_q_natural_voice/natural_voice_from_pasted_content_17.py, bridge/jarvis/gpu_resource_manager.py, bridge/jarvis/modules/device.py |
| 4096 | (desconhecido — catalogar!) | engine/agents/hermes_supervisor_agent.py, engine/data_store.py, scripts/hermes_melhorias_v25q.py |
| 5000 | (desconhecido — catalogar!) | bridge/diagnostico_gpu_voice.py, engine/core/cache_integration.py, engine/core/experience_db.py |
| 5555 | (desconhecido — catalogar!) | bridge/cognitive/state_vector_daemon.py, bridge/jarvis_voice_server.py, engine/sre/omnipotent_health_profiler.py |
| 5556 | (desconhecido — catalogar!) | bridge/cognitive/state_vector_daemon.py, engine/surrogate_harvester.py |
| 5558 | (desconhecido — catalogar!) | bridge/telegram/tg_dependencies.py, engine/agents/bet365_asian_stabilizer.py |
| 5559 | (desconhecido — catalogar!) | bridge/telegram/tg_dependencies.py |
| 5560 | (desconhecido — catalogar!) | engine/infra/resilience/zmq_xpub_xsub_router.py |
| 6379 | (desconhecido — catalogar!) | engine/reliability/advanced_diagnostic.py |
| 7200 | (desconhecido — catalogar!) | engine/core/cache_integration.py |
| 8000 | (desconhecido — catalogar!) | bridge/voice_preflight.py, engine/agents/people_memory.py |
| 8080 | Bridge | agents/glm_analysis_agent.py, bridge/diagnostico_gpu_voice.py, bridge/emergency_bridge.py |
| 8088 | (desconhecido — catalogar!) | engine/infra/network_bandwidth.py, engine/infra/network_latency.py |
| 8099 | Voice | bridge/diagnostico_gpu_voice.py, bridge/jarvis_voice_server.py, bridge/telegram/tg_async_decoupled_proxy.py |
| 8192 | (desconhecido — catalogar!) | engine/agents/hermes_supervisor_agent.py, scripts/hermes_melhorias_v25q.py |
| 8765 | Engine AURA | agents/glm_analysis_agent.py, bridge/diagnostico_gpu_voice.py, bridge/jarvis_voice_server.py |
| 8766 | Matriz | desktop/packaging/audit_installer_static.py, engine/agents/hermes_agents_v9_max.py, engine/agents/hermes_swarm_v32.py |
| 8777 | Hermes Chat API | hermes_v10/core/hermes_llm_engine.py, hermes_v10/scripts/hermes_v10_chat_api.py, hermes_v10/scripts/hermes_v9_chat_api.py |
| 8778 | (desconhecido — catalogar!) | hermes_v10/scripts/hermes_v10_chat_api.py, scripts/hermes_v10_chat_api.py |
| 8788 | (desconhecido — catalogar!) | scripts/aura_compute.py |
| 8790 | Tools Control API | scripts/aura_generate_map.py, scripts/aura_tools_control_api.py |
| 9101 | (desconhecido — catalogar!) | bridge/server.py |
| 9102 | (desconhecido — catalogar!) | engine/server.py |
| 9999 | (desconhecido — catalogar!) | engine/agents/voice_auth.py, engine/worker_offload.py |
| 10000 | (desconhecido — catalogar!) | engine/hybrid_data_store.py, engine/pillars/hybrid_data_store.py, hermes_v10/core/hermes_constitutional_loop.py |
| 10048 | (desconhecido — catalogar!) | bridge/diagnostico_gpu_voice.py |
| 10050 | (desconhecido — catalogar!) | engine/pillars/hybrid_data_store.py |
| 11434 | Ollama (NUNCA matar) | addons/domestic_operator_v2_separate_final/domestic_operator.py, agents/glm_analysis_agent.py, agents/master_agent.py |
| 12000 | (desconhecido — catalogar!) | scripts/AURA_AI_AUDITOR.py |
| 14582 | (desconhecido — catalogar!) | scripts/AURA_AI_AUDITOR.py, scripts/AURA_AI_SENTINEL.py |
| 16000 | (desconhecido — catalogar!) | scripts/aura_voice_client.py |
| 20000 | (desconhecido — catalogar!) | engine/core/observability.py |
| 22050 | (desconhecido — catalogar!) | scripts/teste_xtts_referencia.py |

## Inventario .py (amostra top por tamanho)

| Ficheiro | Bytes | Descricao |
|---|---|---|
| `engine/server.py` | 114797 | Hard-block: never start Engine with real execution enabled by accident. |
| `scripts/aura_admin_core.py` | 97153 | Small synchronous event bus; subscriber failures never break the caller. |
| `scripts/test_aura_admin_advanced.py` | 68836 | Advanced dependency-light tests for the AURA administrator control plane. |
| `bridge/server.py` | 64057 | Rotaciona JSONL antes do fallback escrever, sem apagar o arquivo ativo. |
| `engine/agents/browser_agent.py` | 57240 | Deserializa frames WS texto/binario do SokkerPRO para JSON. |
| `scripts/hermes_v10_chat_api.py` | 55432 | Converte tipos numpy/não-JSON em tipos Python nativos. |
| `hermes_v10/scripts/hermes_v10_chat_api.py` | 55432 | Converte tipos numpy/não-JSON em tipos Python nativos. |
| `scripts/aura_chat_agents.py` | 52924 | Arranca processo em background com log (Windows detached). |
| `engine/core/mc_grid.py` | 49562 | Media trapezoidal da taxa em [0, minutes] (referencia da grade). |
| `scripts/run_selftests.py` | 48821 | Escrita atomica tmp + os.replace (convencao §6). |
| `engine/engine_core.py` | 48464 | Converte lista/array para tensor somente se houver margem segura. |
| `engine/agents/desktop_controller.py` | 48156 | 'ctrl+shift+s' -> [VK_CONTROL, VK_SHIFT, ord('S')]; [] se invalido. |
| `engine/agents/domestic_operator.py` | 44725 | Arquivos domesticos: TUDO confinado a um unico diretorio raiz. |
| `addons/domestic_operator_v2_separate_final/domestic_operator.py` | 44510 | Arquivos domesticos: TUDO confinado a um unico diretorio raiz. |
| `engine/agents/domestic_operator_v2.py` | 44504 | Arquivos domesticos: TUDO confinado a um unico diretorio raiz. |
| `engine/data_store.py` | 43248 | Serializa escritas não críticas e agrupa a fila em intervalos curtos. |
| `engine/core/analytics.py` | 40747 | 'F1|m82|W2' -> ('F1', 82). |
| `bridge/jarvis_voice_server.py` | 39413 | — |
| `engine/agents/pc_operator.py` | 38490 | Bloqueia IP privado (SSRF) exceto localhost (nossos servicos). |
| `engine/admin/aura_admin_api.py` | 38423 | Small Ollama adapter returning only the model's structured text. |
| `engine/pillars/hybrid_data_store.py` | 37986 | Retorna todos os registros válidos em ordem de inserção. |
| `engine/agents/hermes_supervisor_agent.py` | 37060 | Print safe on Windows cp1252 consoles. |
| `engine/core/conformal_gate.py` | 35093 | Drift ALARGA o intervalo: reduz o alpha efetivo (mais cobertura exigida). |
| `engine/agents/jarvis_command_center.py` | 34843 | GET JSON defensivo. None = inalcançavel (nunca levanta). |
| `engine/agents/people_memory.py` | 34680 | Carrega opencv e devolve (cv2, face_module_or_None, level). |
| `patches/hermes_supervisor_agent.py` | 34107 | Print safe on Windows cp1252 consoles. |
| `scripts/hermes_v9_chat_api.py` | 32767 | Garante dirs e seed paper-demo para instalacao limpa. |
| `hermes_v10/scripts/hermes_v9_chat_api.py` | 32767 | Garante dirs e seed paper-demo para instalacao limpa. |
| `engine/agents/media_editor.py` | 32702 | Preferencia OBSERVADA em render aprovado — conta menos que dita. |
| `engine/agents/football_research_hub.py` | 32332 | Um resultado de pesquisa de qualquer fonte. |
| `engine/agent_registry.py` | 32317 | Parse AST only when file mtime changes. |
| `addons/installation_r_tipster_capture/tipster_capture_from_pasted_content_18.py` | 32298 | Detecta se uma mensagem e uma entrada de aposta. |
| `engine/agents/tipster_capture.py` | 32298 | Detecta se uma mensagem e uma entrada de aposta. |
| `scripts/aura_compute.py` | 32073 | — |
| `engine/agents/football_intelligence.py` | 31799 | Busca uma temporada completa de uma liga. |
| `engine/agents/cross_site_analyst.py` | 31168 | Bayesian reputation: prior Beta(5,5), updates com hits/misses. |
| `engine/boot.py` | 30094 | Configura log rotativo sem duplicar handlers em reinicializações. |
| `scripts/robot_alert_audit.py` | 29316 | — |
| `engine/core/observability.py` | 29039 | Snapshot JSON local para o dashboard; não abre portas nem faz I/O externo. |
| `engine/mora_daily_pipeline.py` | 28810 | Resultado da Fase 1 — Auditoria Interna. |
| `engine/agents/agent_skill_engine.py` | 28794 | Pede ao Qwen3 para gerar sequencia de acoes como tool calls. |
| `engine/agents/research_improver.py` | 27678 | GET injetavel (testes sem rede). Nunca levanta — caller decide. |
| `engine/agents/external_intelligence.py` | 27513 | Detecta e usa nomic-embed-text no Ollama local. Sem modelo: None. |
| `engine/risk_gates.py` | 27123 | Hard gates independentes + cooldown + histerese. Kelly off. |
| `engine/agents/telegram_employee.py` | 27044 | Cliente minimo da Bot API (urllib, multipart manual). |
| `engine/core/feed_bus.py` | 26619 | Escrita atomica: tmp + os.replace. Leitor nunca ve arquivo truncado. |
| `engine/sre/omnipotent_health_profiler.py` | 25224 | — |
| `engine/model_shadow.py` | 25140 | Separate corner / pressure / xG / shot / card / market events. |
| `engine/agents/jarvis_persona.py` | 25094 | AURA QUANT-X V25 — Jarvis Persona: identidade, memoria e comportamento. |
| `scripts/aura_final_check.py` | 24829 | Import seguro em subprocesso (nao contamina este processo). |
| `agents/master_agent.py` | 23335 | Resultado do Passo 1 — Auditoria. |
| `engine/agents/master_agent.py` | 23335 | Resultado do Passo 1 — Auditoria. |
| `agents/glm_analysis_agent.py` | 23270 | Agente advisory — nunca executa ordem. |
| `bridge/jarvis/modules/neural_tts.py` | 23191 | Chave estável: engine + texto já sanitizado/normalizado. |
| `agents/threshold_tuner.py` | 22874 | Formato lido por DynamicThresholds se approved=true. |
| `engine/agents/threshold_tuner.py` | 22874 | Formato lido por DynamicThresholds se approved=true. |
| `addons/installation_s_intent_router/intent_router_from_pasted_content_19.py` | 22672 | Fornece contexto dinâmico para o prompt do router. |
| `engine/agents/intent_router.py` | 22672 | Fornece contexto dinâmico para o prompt do router. |
| `scripts/aura_admin_governance.py` | 21804 | Issue and validate short-lived approvals bound to one exact action. |
| `engine/core/replay.py` | 21534 | Epoch do registro: received_at > view.raw_ts > ts. |
| `engine/agents/glm_analysis_agent.py` | 21310 | Agente advisory — nunca executa ordem. |
| `scripts/hermes_autonomous_os.py` | 21209 | — |
| `engine/hybrid_data_store.py` | 19940 | Ring buffer de dicionários usado pela API dos anexos. |
| `engine/orchestrator.py` | 19319 | Classifica o pedido sem impedir conversa fora do domínio de trading. |
| `scripts/AURA_DIAG_INTELIGENTE_E2E.py` | 19268 | Analise heuristica local (sem API externa). Usa regras + cobertura. |
| `scripts/hermes_tools.py` | 18982 | Hermes Tool Registry V9 — tool-use com guardrails. Nunca liga execution_allowed. |
| `scripts/aura_voice_client.py` | 18846 | POST que consome NDJSON e devolve eventos. |
| `scripts/verify_aura_apis.py` | 18686 | Lê ficheiro Python. Stripa BOM se existir. Retorna (source, error). |
| `engine/pillars/core_system.py` | 18549 | AURA QUANT-X V13.0 — core_system.py — Topologia unificada (pilares 1,2,4,5,8,10). |
| `engine/agents/hermes_agents_v9_max.py` | 18489 | Crew-style inter-agent message (TradingAgents / CrewAI pattern). |
| `scripts/AURA_AI_AUDITOR.py` | 18160 | Regras deterministicas (sempre ligadas, mesmo sem LLM). |
| `desktop/update_manual.py` | 18055 | — |
| `engine/digital_twin_monte_carlo.py` | 17786 | Local precomputed cache keyed by MD5 of the current-state NumPy array. |
| `addons/installation_q_natural_voice/natural_voice_from_pasted_content_17.py` | 17651 | Detecta e usa o melhor TTS disponível. Degrada para edge-tts. |
| `engine/agents/natural_voice.py` | 17651 | Detecta e usa o melhor TTS disponível. Degrada para edge-tts. |
| `engine/agents/odds_quality_monitor.py` | 17622 | Extrai odds de um frame cornerai-analyst-1. |
| `bridge/jarvis/parallel_audio_pipeline.py` | 17562 | Invoca mocks/implementações com assinaturas antiga e nova. |
| `desktop/aura_self_test.py` | 16707 | — |
| `desktop/packaging/audit_installer_static.py` | 16702 | — |
| `engine/matrix_full_diagnostic.py` | 16662 | Diagnostico completo multi-camada + narrativa Hermes/Ollama para a Matriz. |

_Total ficheiros .py indexados: 658_

## Env vars detectadas

- `AURA_BRIDGE_LATEST_URL`
- `AURA_BRIDGE_TOKEN`
- `AURA_CHAT_GLM_GATE_WAIT`
- `AURA_CHAT_GLM_RESOURCE_WAIT`
- `AURA_CPU_AFFINITY`
- `AURA_ENGINE_ORIGIN_REGEX`
- `AURA_EXECUTION_ALLOWED`
- `AURA_E_ENABLE_SKILL_EXECUTION`
- `AURA_GC_CLEANUP_INTERVAL_S`
- `AURA_GLM_MODEL`
- `AURA_LOCAL_ONLY`
- `AURA_MANUAL_ROOT`
- `AURA_MUTATION_TOKEN`
- `AURA_OLLAMA_BASE_URL`
- `AURA_OLLAMA_KEEP_ALIVE`
- `AURA_OLLAMA_MODEL`
- `AURA_OLLAMA_PREWARM_ENABLED`
- `AURA_PAPER_ONLY`
- `AURA_PIPER_BIN`
- `AURA_PIPER_CONFIG`
- `AURA_PIPER_MODEL`
- `AURA_ROOT`
- `AURA_SCHEMA_HASH_HEALTHY`
- `AURA_SELF_TEST_PHASE`
- `AURA_SELF_TEST_ROOT`
- `AURA_SHUTDOWN_UNLOAD_OLLAMA`
- `AURA_TELEGRAM_BOT_TOKEN`
- `AURA_TELEGRAM_ENGINE_URL`
- `AURA_TELEGRAM_MIN_INTERVAL`
- `AURA_TELEGRAM_PIN`
- `AURA_TG_PIN`
- `AURA_TG_TOKEN`
- `AURA_TTS_CACHE_FILES`
- `AURA_TTS_CACHE_MB`
- `AURA_TTS_ENGINE`
- `AURA_TTS_RAM_CACHE`
- `AURA_UNLOCK_LIVE`
- `AURA_VOICE_PORT`
- `AURA_WORKER_ALLOW_PUBLIC_ENDPOINT`
- `AURA_WORKER_ENDPOINT`
- `AURA_WORKER_ENDPOINTS`
- `AURA_WORKER_OFFLOAD_AGENTS`
- `AURA_WORKER_OFFLOAD_ENABLED`
- `AURA_WORKER_TIMEOUT`
- `AURA_WORKER_TOKEN`
- `AURA_WORKER_TOKENS`
- `AURA_XTTS_DEVICE`
- `CORNERAI_ADMIN_MODEL`
- `CORNERAI_BRIDGE_REQUIRE_TOKEN`
- `CORNERAI_BRIDGE_TOKEN`
- `CORNERAI_CHAT_MODEL`
- `CORNERAI_CHAT_TIMEOUT`
- `CORNERAI_MODEL`
- `CORNERAI_OLLAMA_HOST`
- `CUDA_VISIBLE_DEVICES`
- `EXECUTION_ALLOWED`
- `GLM_API_KEY`
- `HERMES_ALERT_WEBHOOK`
- `HERMES_API_PORT`
- `HERMES_DEBUG`

## Fluxo de boot esperado
1. Ollama :11434 (externo)
2. Bridge :8080
3. Engine :8765
4. Matriz :8766
5. Control :8790
6. Hermes Chat :8777

> Portas sem servico nomeado = candidatas a live_missing no detector.

## Catalogo de erros
Ver `core/aura_error_catalog.json` + motor `core/aura_error_catalog.py`.
Diagnostico: GET /api/diagnose · Fix: `fix E-NET-004` no chat.