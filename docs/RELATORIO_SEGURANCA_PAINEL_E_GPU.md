# Relatório — Segurança do Painel + Monitoramento GPUs + Interface
**AURA QUANT-X HERMES V37.3.37** · 2026-08-30

## Resumo executivo
O painel de controlo (`tools-hub.html` + API `:8790`) é **local-only**, paper-trade only e relativamente bem protegido para o uso pretendido (operador único em máquina Windows). As melhorias deste patch reforçam autenticação opcional, auditoria e visualização de GPU.

## Segurança do Painel

### Controles existentes (positivos)
| Controlo | Localização | Notas |
|----------|-------------|-------|
| Paper-trade invariante | `engine/core/security.py` | `PAPER_TRADE=True`, `EXECUTION_ALLOWED=False` imutáveis em runtime |
| Firewall + sanitização | `engine/aura_security_firewall.py` | Rate-limit, XSS/SQLi/path patterns, agent firewall |
| Admin PolicyGate | `engine/admin/aura_admin_api.py` | Allowlist de tools, human approval, circuit-breaker |
| Allowlist de ficheiros | `config/allowlist.json` | Padrões + protected paths |
| SafeExecutor anti-bet | `bridge/jarvis/security/safe_executor.py` | Bloqueia janelas de casas de apostas |
| SecureStorage (DPAPI) | `desktop/Security/SecureStorage.cs` | Cifra CurrentUser + anti-traversal |
| Bind localhost | Control API | `127.0.0.1:8790` apenas |

### Riscos residuais
1. **API de controlo sem auth por defeito** — qualquer processo local pode POST (kill-switch, limpar fila, etc.).
2. **CORS e Host** — originalmente permissivos.
3. **Escritas em JSON** sem lock de ficheiro (race possível sob carga).
4. **Sem rate-limit na Control API** (só no firewall principal).
5. **Dependência de paths Windows** e `AURA_ROOT`.

### Mitigações deste patch
- Token opcional via env `AURA_CONTROL_TOKEN` (header `X-AURA-Token`).
- Audit log: `logs_supervisor/control_api_actions.jsonl`.
- Headers: `X-Content-Type-Options`, `X-Frame-Options`, CORS mais restrito.
- Verificação básica de Host (localhost/127.0.0.1).
- Endpoint dedicado `/api/vram`.

**Como ativar token:**
```bat
set AURA_CONTROL_TOKEN=seu-segredo-longo
AURA_TOOLS_CONTROL_API.bat
```
No browser o fetch precisa enviar o header (ou use só BATs locais).

## Monitoramento de GPUs
- Já existia via `nvidia-smi` → `ops_status.json` e aba VRAM.
- Agora a API devolve: memória usada/total, %, util, **temperatura**, lista de **recomendações**.
- UI colorida (ok / warn / bad) + tips (“VRAM crítica → AURA_GROK_GPU_LIVRE.bat”).
- `engine/gpu_resource_manager.py` continua a ser a fonte canónica para política CUDA vs Intel UHD e headroom de voz/LLM.

## Correções de Interface
- Bloco VRAM expandido com tips.
- Rendering de status com classes de cor.
- Banner da API mais claro (paper-only).
- Nenhuma tag HTML crítica em aberto encontrada (void elements OK em HTML5).

## Como aplicar os patches
1. Pare a Control API se estiver a correr.
2. Copie:
   - `aura_patches/aura_tools_control_api.py` → `scripts/aura_tools_control_api.py`
   - `aura_patches/tools-hub.html` → `desktop/ui/matriz_v22/tools-hub.html`
3. (Opcional) Defina `AURA_CONTROL_TOKEN`.
4. Reinicie: `AURA_TOOLS_CONTROL_API.bat` e abra `http://127.0.0.1:8766/tools-hub.html` (ou via Cockpit).

## Checklist de hardening adicional (futuro)
- [ ] File lock (portalocker / msvcrt) nas escritas de fila/policy.
- [ ] Rate-limit simples na Control API (ex.: 30 req/min por endpoint mutável).
- [ ] Assinatura HMAC opcional dos ficheiros de estado críticos.
- [ ] Expor apenas GET de status se token não configurado (POST exige token).
- [ ] Integração opcional com `gpu_resource_manager` (torch/pynvml) quando disponível.

---
**Invariantes mantidos:** paper_trade=true · execution_allowed=false · sem execução real de ordens.
