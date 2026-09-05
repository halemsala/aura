# Checklist de validação — Autonomy Layer V1 (paper-only)

Use após copiar os arquivos e antes de considerar a camada ativa.

## 1. Pré-requisitos
- [ ] Backup da pasta AURA (ex.: C:\AURA_BACKUP_YYYYMMDD)
- [ ] ZIP completo disponível para reextração
- [ ] Python 3.10 ou 3.11 confirmado (`py -3.11 --version`)
- [ ] `config\AURA_RUNTIME.env` com PAPER=1 e EXECUTION=0

## 2. Arquivos de governança
- [ ] `AGENTS.md` presente na raiz
- [ ] `MANIFESTO_MINIMO.json` presente (política; não aplica sozinho)
- [ ] `scripts\aura_doctor.py` presente

## 3. Serviços
- [ ] Bridge :8080 health 200
- [ ] Engine :8765 health 200
- [ ] Voice :8099 (se usado) health 200
- [ ] Hermes responde ou log claro se OFF

## 4. Invariantes
- [ ] paper_trade=true
- [ ] execution_allowed=false
- [ ] Nenhum unlock LIVE ativo

## 5. Doctor
- [ ] `python scripts\aura_doctor.py` (ou via venv) executa sem crash
- [ ] Gera `logs_supervisor\DOCTOR_LATEST.txt` e `.json`
- [ ] Overall ≠ crítico (ou críticos entendidos e com plano)

## 6. Relatório geral
- [ ] `RELATORIO_GERAL_LATEST.txt` atualizado
- [ ] Sem erros bloqueantes de Bridge/Engine

## 7. Agentes
- [ ] Núcleo corner / hawkes / market_edge / risk / veracity ativo
- [ ] Demais em disabled ou shadow (se manifesto foi ajustado)
- [ ] Nenhuma skill externa alterou AGENTS.md

## 8. Rollback testado
- [ ] Sabe como parar portas AURA
- [ ] Sabe restaurar backup ou reextrair ZIP
- [ ] Documentou o procedimento

## 9. Segurança
- [ ] Nenhum segredo em logs do doctor ou relatório
- [ ] Allowlist respeitada
- [ ] Strix NÃO instalado neste ambiente de produção
