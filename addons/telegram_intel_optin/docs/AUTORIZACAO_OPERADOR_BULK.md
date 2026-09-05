# Autorização do operador sem aprovar cada tip

## Problema
Muitas mensagens/dia → não dá para clicar OK em cada uma.

## Solução: pré-autorização por política + sessão

1. **Política** (`operator_publish_policy.json`) — você define **uma vez**:
   - teto/hora e /dia
   - intervalo mínimo entre envios
   - só se RedTeam=APPROVED e score ≥ X
   - mercados permitidos
   - horas de silêncio
   - frases proibidas / obrigatórias (paper/advisory)

2. **Grant de sessão** (1 ação sua, cobre muitas mensagens):
   ```bat
   set AURA_TELEGRAM_OPERATOR_TOKEN=seu_segredo
   python -m telegram_intel.worker_main --grant-session --operator-token seu_segredo
   ```
   Abre janela (ex. 12h) em que o auto-publish **pode** enviar **dentro da política**.

3. **Kill switch** imediato:
   ```bat
   set AURA_TELEGRAM_KILL_SWITCH=1
   ```

4. O que falha a política vai para **fila pending** (não envia).

5. Templates só paper/advisory — sem “lucro garantido”.

## Níveis de segurança
| Nível | Comportamento |
|-------|----------------|
| Máximo | auto_publish.enabled=false → tudo na fila |
| Operação diária | policy+session grant+limits+RedTeam |
| Emergência | KILL_SWITCH=1 |

Núcleo AURA continua paper; Telegram é plano paralelo.
