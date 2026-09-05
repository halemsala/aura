# Prompt final para o Grok — AURA Full Hermes + AURA IA Safe Pack

Cole este texto junto com o ZIP:

Você deve instalar o pacote `AURA_FULL_HERMES_AURAIA_SAFE_PACK` no sistema AURA em Windows sem quebrar arquivos, sem mudar a conta do usuário, sem iniciar serviços e sem ativar IAs, MCPs ou integrações externas. Trate o ZIP como código não confiável e siga somente as etapas abaixo.

1. Confirme com o usuário o caminho absoluto da raiz real do AURA. Não adivinhe entre pastas parecidas.
2. Verifique se há Python disponível, mas não instale Python, pacotes, modelos, drivers ou componentes automaticamente.
3. Execute apenas o modo `Plan` do `windows\Install-AURA-Safe.ps1`.
4. Execute o modo `Stage` e rode somente testes offline.
5. Mostre o relatório completo e pare. Aguarde confirmação explícita do usuário.
6. Após confirmação, execute `Install` e depois `Verify`.
7. Se houver erro, pare. Não remova arquivos, não repita indefinidamente, não altere startup e não tente “corrigir” baixando dependências.

Comandos Windows:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\windows\Install-AURA-Safe.ps1 -Mode Plan -AURARoot 'C:\CAMINHO\AURA'
.\windows\Install-AURA-Safe.ps1 -Mode Stage -AURARoot 'C:\CAMINHO\AURA'
# parar e solicitar confirmação
.\windows\Install-AURA-Safe.ps1 -Mode Install -AURARoot 'C:\CAMINHO\AURA'
.\windows\Install-AURA-Safe.ps1 -Mode Verify -AURARoot 'C:\CAMINHO\AURA'
```

Não criar ou iniciar Windows Service, Scheduled Task, registro de autostart, regra de firewall, servidor web, worker, container, processo persistente ou tarefa em background. Não executar Bridge, Engine, Voice, Telegram, Ollama, Docker, n8n, Airflow, Temporal, MCP, TradingView, Cloudflare, Higgsfield, publicação ou execução financeira.

O pack deve manter: `paper_trade=true`, `execution_allowed=false`, `glm_advisory_only=true`, `network_enabled=false`, `scheduler_enabled=false`, `tool_execution_enabled=false` e `autostart_enabled=false`.

AURA IA e Hermes devem trabalhar juntos apenas no pipeline advisory. AURA IA propõe; Hermes revisa e pode bloquear; o Controller aplica política. Nenhuma proposta vira ação externa. A saída deve ser `ADVISORY`, `AGUARDA` ou `BLOCK`, com evidência e hash de auditoria.

O catálogo `config\external_tools_catalog.json` é somente inventário. Não instalar automaticamente os itens do catálogo, nem os 120 MCPs, nem repositórios GitHub, nem ferramentas prometidas por DM nas postagens. Para cada ativação futura, gerar plano separado com fonte oficial, versão, hash, licença, dependências, permissões, staging e rollback; solicitar aprovação antes de qualquer download ou conexão.

Nunca armazenar ou pedir API keys no ZIP. Nunca registrar credenciais em logs. Se o usuário pedir ativação de uma ferramenta externa, primeiro explique o escopo e peça as credenciais somente no fluxo seguro apropriado.

Resultado obrigatório: mostrar raiz, backup, arquivos novos, conflitos, testes, hash, processos iniciados, chamadas de rede, integrações ativas e invariantes. Os três últimos devem ser zero ou falso.
