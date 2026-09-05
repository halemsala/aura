# Plano Windows CMD — Autonomy Layer V1 (A+B+C)

**Ainda sem execução automática.** Copie e rode **um bloco de cada vez** no CMD.

Path assumido: `C:\aura`

---

## 0) Backup

```bat
mkdir C:\AURA_BACKUP_20260831
xcopy C:\aura C:\AURA_BACKUP_20260831\aura_before_autonomy /E /I /H /Y
```

---

## 1) Copiar arquivos de governança

Coloque na raiz `C:\aura`:
- AGENTS.md
- MANIFESTO_MINIMO.json

Coloque em `C:\aura\scripts\`:
- aura_doctor.py

```bat
cd /d C:\aura
dir AGENTS.md
dir MANIFESTO_MINIMO.json
dir scripts\aura_doctor.py
```

---

## 2) Confirmar env paper-only

```bat
cd /d C:\aura
if not exist config\AURA_RUNTIME.env copy config\AURA_RUNTIME.env.example config\AURA_RUNTIME.env
notepad config\AURA_RUNTIME.env
```

Garanta:
```
AURA_PAPER_TRADE=1
AURA_EXECUTION_ALLOWED=0
AURA_UNLOCK_LIVE=0
```

---

## 3) (Opcional) Ajustar manifesto de agentes

**Não faça isso sem backup.**  
O `MANIFESTO_MINIMO.json` é política. Se for editar `agents\activation_manifest.json`:

```bat
cd /d C:\aura
copy agents\activation_manifest.json agents\activation_manifest.json.bak
notepad agents\activation_manifest.json
```

Deixe apenas o núcleo enabled; resto disabled/shadow.  
Salve e documente no changelog.

---

## 4) Subir / verificar stack

```bat
cd /d C:\aura
AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat
```

Se venv/cache corrompido:
```bat
AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat /FORCE
```

---

## 5) Rodar doctor

```bat
cd /d C:\aura
engine\venv\Scripts\python.exe scripts\aura_doctor.py
```

Se o venv não existir:
```bat
py -3.11 scripts\aura_doctor.py
```

Verifique:
```bat
type logs_supervisor\DOCTOR_LATEST.txt
```

---

## 6) Relatório geral

```bat
cd /d C:\aura
AURA_INSTALAR_TESTAR_RELATORIO_GERAL.bat
```

Ou, se a stack já estiver no ar:
```bat
AURA_RELATORIO_GERAL.bat
```

---

## 7) Validação rápida

```bat
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8099/api/voice/health
type logs_supervisor\RELATORIO_GERAL_LATEST.txt
```

---

## 8) Rollback (se necessário)

```bat
REM Parar portas AURA (ou use o free-ports do próprio BAT)
cd /d C:\aura
REM Restaurar:
xcopy C:\AURA_BACKUP_20260831\aura_before_autonomy C:\aura /E /I /H /Y
```

Ou reextrair o ZIP completo limpo em `C:\aura`.

---

## Notas
- Não instale Strix neste ambiente.
- Não altere execution_allowed.
- Manifesto mínimo é recomendação; aplicação no JSON real exige revisão humana.
