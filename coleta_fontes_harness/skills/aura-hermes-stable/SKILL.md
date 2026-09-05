---
name: aura-hermes-stable
description: Estabiliza Hermes Chat ON, corrige 404 Operator OS, resolve status OFF na UI e diagnostica BLOCKED_BY_DATA da captura SokkerPro no AURA QUANT-X. Use quando Hermes fica OFF, chat recusa conexao, tela 404, ENGINE/BRIDGE/VOZ aparecem OFF, ou analise retorna BLOCKED_BY_DATA por campos ausentes (dangerous, xg, corners events).
metadata:
  type: workflow
  version: "1.0.0"
  product: AURA QUANT-X
  invariants: paper_trade=true execution_allowed=false
---

# AURA Hermes Stable + Captura

Operar o AURA QUANT-X com Hermes estavel e captura suficiente para sair de BLOCKED_BY_DATA, sem desligar paper-trade nem Policy Engine.

## Invariantes (nunca alterar)

- paper_trade=true
- execution_allowed=false
- GLM_ADVISORY_ONLY=true
- Acoes destrutivas no chat exigem AUTORIZO

## Sintomas, causa e acao

### Hermes OFF / conexao recusada em :8777

1. Ver log:
   powershell -Command "Get-Content C:\aura\logs_supervisor\hermes_v10.log -Tail 50"
2. Matar porta 8777 e subir de novo:
   AURA_HERMES_V10_ULTRA.bat
3. Se falhar por import/path, usar entry canonico:
   C:\aura\engine\venv\Scripts\python.exe C:\aura\hermes_v10\AURA_RUN_HERMES.py
4. Confirmar http://127.0.0.1:8777/chat e http://127.0.0.1:8777/api/system

### 404 Page Not Found no Operator OS

Causa tipica: Service Worker / cache WebView2.

Fechar todas as janelas AURA, depois:
powershell -Command "Remove-Item -Recurse -Force \"$env:LOCALAPPDATA\AURA_QUANT_X\" -EA SilentlyContinue"

Em seguida:
AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat /FORCE

Abrir so a URL canonica http://127.0.0.1:8766/index.html
No browser: F12, Application, Service Workers, Unregister, Clear site data, Ctrl+Shift+R.

### ENGINE / BRIDGE / VOZ em OFF na barra (mas health 200)

Desync de UI state. Nao reiniciar a cega.

1. Confirmar health real nas URLs de Bridge/Engine/Voice.
2. Se health OK e UI OFF, limpar cache Desktop (/FORCE) e reabrir Matriz.
3. Se health OFF, usar AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat.

### BLOCKED_BY_DATA

O Engine deve bloquear quando faltam campos criticos. Nao contornar o gate.

Campos que costumam faltar:
- dangerous.home / dangerous.away
- xg.home / xg.away
- timeline de escanteios (stats 4x4 com events 0x0)

Checklist de captura:
1. SokkerPro aberto na partida correta (mesma fixture do feed).
2. Extensao/captura DOM ativa (desktop/capture/aura-capture.js build SokkerPro-DOM).
3. Bridge latestAgeSec baixo (ideal menor que 30s). Verificar http://127.0.0.1:8080/health
4. Engine le Bridge + fallback bridge/live_latest.json.
5. Se corners-stats-events falha (stats existem, eventos nao), manter SokkerPro em foco na aba de estatisticas/escanteios.

Comando de verificacao rapida: CHECK.bat

Interpretar signal/decision em /api/ui/state:
- BLOCKED_BY_DATA = captura incompleta (corrigir DOM/feed, nao o gate)
- OBSERVANDO + services_health true = stack OK, so falta qualidade de dados

### Voice com No module named faster_whisper

AURA_REPARAR_XTTS_TORCHCODEC.bat
ou na venv:
C:\aura\engine\venv\Scripts\activate
pip install faster-whisper
Reiniciar Voice depois.

## BAT master canonico

Preferir sempre:
AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat /FORCE

Este BAT e o entrypoint de recuperacao completa. Nao inventar sequencia manual longa se o BAT cobrir.

## Entrega de correcoes

Qualquer alteracao de codigo/scripts no AURA exige ZIP completo do pacote (nunca so patch). Manter BATs com CRLF e invariantes intactos.

## Referencias

- Portas e smoke: skill aura-quant-x
- Governanca e Paper Lock: skill aura-governance
- Explicacoes advisory: skill aura-explanation
