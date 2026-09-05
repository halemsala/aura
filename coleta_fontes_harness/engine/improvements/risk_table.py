# risk_table.py
# Tabela de riscos operacional — exposição, motivos de bloqueio, severidade
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RiskRow:
    code: str
    severity: str          # LOW | MEDIUM | HIGH | CRITICAL
    title: str
    description: str
    mitigation: str
    active: bool = True


# Tabela estática de riscos conhecidos do AURA (paper-first)
RISK_CATALOG: List[RiskRow] = [
    RiskRow("SYNTHETIC_MODEL", "CRITICAL", "Modelo sintético",
            "Pesos treinados em dados sintéticos. Brier/relatórios não validam produção.",
            "Substituir por dataset real rotulado + walk-forward antes de qualquer declaração de acertividade."),
    RiskRow("HEURISTIC_ACCURACY", "HIGH", "Score de acertividade heurístico",
            "accuracy_pack mede completude/confluência, não acurácia preditiva.",
            "Exibir sempre score_type=HEURISTIC_COMPLETENESS e disclaimer."),
    RiskRow("DOM_SILENT", "CRITICAL", "Captura DOM/WoM silenciosa",
            "odds_velocity ou pressão em zero sem alerta de fonte inativa.",
            "Usar DomApiCaptureCanary; emitir SOURCE_INACTIVE."),
    RiskRow("CORS_OPEN", "HIGH", "CORS permissivo",
            "Engine com Access-Control-Allow-Origin amplo.",
            "Allowlist explícita + token de instalação em modo endurecido."),
    RiskRow("AUTH_OPTIONAL", "HIGH", "Autenticação opcional",
            "Bridge/Engine aceitam requests sem token em modo dev.",
            "Tornar token obrigatório em modo hardened."),
    RiskRow("EVENTS_RECONCILE", "HIGH", "Reconciliação de eventos incompleta",
            "events_complete=true com lista vazia podia passar como OK.",
            "Tratar lista vazia completa como total=0 (já corrigido em 12.8.2)."),
    RiskRow("OBSERVATION_AS_ENTRY", "MEDIUM", "Observação confundida com entrada",
            "WATCH/HOLD podiam aparecer como bloqueio genérico de fixture.",
            "Separar contrato de observação do de execução; mensagem 'Sem entrada'."),
    RiskRow("KELLY_OFF", "LOW", "Kelly real desligado",
            "Sistema opera paper-first com approved=false.",
            "Manter. Nunca ligar stake real sem governança explícita."),
    RiskRow("VERSION_DRIFT", "MEDIUM", "Divergência de versões",
            "Manifest, Engine, Bridge e docs com versões diferentes.",
            "Single source of truth + Release Doctor."),
    RiskRow("NO_WALKFORWARD", "CRITICAL", "Ausência de walk-forward real",
            "Sem validação temporal em dados rotulados não há base para acertividade.",
            "Usar calibration_lab.walk_forward_evaluate com outcomes reais."),
]


def risk_table_as_dict(active_only: bool = False) -> List[Dict[str, Any]]:
    rows = RISK_CATALOG
    if active_only:
        rows = [r for r in rows if r.active]
    return [
        {
            "code": r.code,
            "severity": r.severity,
            "title": r.title,
            "description": r.description,
            "mitigation": r.mitigation,
            "active": r.active,
        }
        for r in rows
    ]


def highest_severity() -> str:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    return max((r.severity for r in RISK_CATALOG if r.active), key=lambda s: order.get(s, 0), default="LOW")
