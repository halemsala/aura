#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
robot_alert_audit.py — auditoria estatistica honesta de datasets de alertas de
tipster externo (robô de Telegram), para o AURA QUANT-X V25.

Local: scripts/robot_alert_audit.py

POR QUE EXISTE
    O dataset do robô vem sendo analisado em outros chats com promessas de
    "70-78% de acerto com filtros". Esta ferramenta aplica a disciplina do §8:
      1. DEDUPLICACAO — o mesmo alerta reenviado nao e amostra nova.
      2. IC DE WILSON em TODA taxa informada.
      3. TESTE BINOMIAL EXATO contra a probabilidade de empate implicita na odd media.
      4. EV POR UNIDADE com IC propagado do IC da taxa.
      5. SUITE DE FILTROS PRE-REGISTRADOS com relatorio do COLAPSO DE N.
      6. Sequencias maximas — variancia visivel.

    AURA = analise. Este script NAO aposta, NAO recomenda stake, NAO envia
    nada a lugar nenhum. Le arquivo, cospe verdade estatistica em markdown.

FORMATOS ACEITOS (arquivo .json ou .jsonl):
    a) plano (dataset_completo.json do extrator)
    b) aninhado (metadata do robô com "entradas"/"estatisticas")

USO
    python scripts/robot_alert_audit.py dataset_completo.json --md audit.md
    python scripts/robot_alert_audit.py --self-test

stdlib only. Python 3.9+. Windows compativel. Console 100% ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"
Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> Tuple[Optional[float], Optional[float]]:
    if n <= 0:
        return None, None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def binom_p_ge(k: int, n: int, p: float) -> float:
    if n < 0:
        raise ValueError("n < 0")
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    q = 1.0 - p
    acc = 0.0
    for i in range(k, n + 1):
        acc += math.comb(n, i) * (p ** i) * (q ** (n - i))
    return min(1.0, max(0.0, acc))


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else x


def parse_minute(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def parse_outcome(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        if v == 1:
            return 1
        if v == 0:
            return 0
        return None
    s = str(v).strip().upper()
    if not s:
        return None
    if s in ("1", "GREEN", "VERDE", "WIN", "V", "SUCESSO"):
        return 1
    if s in ("0", "RED", "VERMELHO", "LOSS", "L", "PERDA"):
        return 0
    if "\u2705" in s:
        return 1
    if "\u274c" in s:
        return 0
    return None


_STAT_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("posse", "posse_casa", "posse_visit"),
    ("superioridade", "superioridade_casa", "superioridade_visit"),
    ("pressao1", "pressao1_casa", "pressao1_visit"),
    ("pressao2", "pressao2_casa", "pressao2_visit"),
    ("ataques_perigosos", "ataques_perigosos_casa", "ataques_perigosos_visit"),
    ("appm_total", "appm_total_casa", "appm_total_visit"),
    ("appm_10min", "appm_10min_casa", "appm_10min_visit"),
    ("appm_5min", "appm_5min_casa", "appm_5min_visit"),
    ("appm_3min", "appm_3min_casa", "appm_3min_visit"),
    ("escanteios", "escanteios_casa", "escanteios_visit"),
    ("chutes_totais", "chutes_totais_casa", "chutes_totais_visit"),
    ("chutes_alvo", "chutes_alvo_casa", "chutes_alvo_visit"),
    ("cartoes", "cartoes_casa", "cartoes_visit"),
)

_NESTED_KEY_MAP = {
    "posse": "posse", "superioridade": "superioridade", "pressao1": "pressao1",
    "pressao2": "pressao2", "ataques_perigosos": "ataques_perigosos",
    "appm": "appm_total", "appm_total": "appm_total",
    "escanteios": "escanteios", "chutes_totais": "chutes_totais",
    "chutes_alvo": "chutes_alvo", "cartoes": "cartoes",
}

_FP_FIELDS = ["jogo", "liga", "tempo", "placar", "mercado", "tipo_alerta"] \
    + [c for _b, c, _v in _STAT_PAIRS] + [v for _b, _c, v in _STAT_PAIRS]


def _expand_nested(r: dict) -> dict:
    out = dict(r)
    est = r.get("estatisticas")
    if isinstance(est, dict):
        for k, v in est.items():
            base = _NESTED_KEY_MAP.get(str(k).strip().lower())
            if base is None or not isinstance(v, str):
                continue
            parts = re.split(r"[-\u2013]", v)
            if len(parts) != 2:
                continue
            a = _num(parts[0].strip().rstrip("%"))
            b = _num(parts[1].strip().rstrip("%"))
            out.setdefault(base + "_casa", a)
            out.setdefault(base + "_visit", b)
    ent = r.get("entrada")
    if isinstance(ent, dict):
        odd = _num(ent.get("odd"))
        if odd is not None and _num(out.get("odd_entrada")) is None:
            out["odd_entrada"] = odd
        if ent.get("mercado") and not out.get("mercado"):
            out["mercado"] = ent.get("mercado")
    return out


def _f_appm5(a: dict) -> bool:
    v = a["dom"].get("appm_5min")
    return v is not None and v >= 0.6


def _f_crescendo(a: dict) -> bool:
    a5, a10 = a["dom"].get("appm_5min"), a["dom"].get("appm_10min")
    return a5 is not None and a10 is not None and a5 > a10


def _f_pressao1(a: dict) -> bool:
    d = a["dom"].get("pressao1_diff")
    return d is not None and d >= 10


def _f_chutes(a: dict) -> bool:
    v = a["dom"].get("chutes_totais")
    return v is not None and v >= 10


def _f_alvo(a: dict) -> bool:
    v = a["dom"].get("chutes_alvo")
    return v is not None and v >= 3


def _f_odd(a: dict) -> bool:
    o = a["odd"]
    return o is not None and 1.70 <= o <= 2.00


FILTERS: Tuple[Tuple[str, str, Callable[[dict], bool]], ...] = (
    ("F1", "APPM 5min lado dominante >= 0.6", _f_appm5),
    ("F2", "crescendo: APPM5 dom > APPM10 dom", _f_crescendo),
    ("F3", "diff pressao1 (dom - outro) >= +10", _f_pressao1),
    ("F4", "chutes totais dom >= 10", _f_chutes),
    ("F5", "chutes no alvo dom >= 3", _f_alvo),
    ("F6", "odd de entrada em [1.70, 2.00]", _f_odd),
)

_ODD_BANDS = ((1.0, 1.60, "1.00-1.59"), (1.60, 1.80, "1.60-1.79"),
              (1.80, 2.00, "1.80-1.99"), (2.00, 2.50, "2.00-2.49"),
              (2.50, 99.0, "2.50+"))


def _odd_band(a: dict) -> Optional[str]:
    o = a["odd"]
    if o is None:
        return None
    for lo, hi, label in _ODD_BANDS:
        if lo <= o < hi:
            return label
    return None


def _half_of(a: dict) -> str:
    m = a["minute"]
    if m is None:
        return "sem minuto"
    return "1T (ate 45)" if m <= 45 else "2T (46+)"


def _streaks(ys: Sequence[int]) -> Dict[str, int]:
    max_w = max_l = cur_w = cur_l = 0
    for y in ys:
        if y == 1:
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)
    return {"max_win_streak": max_w, "max_loss_streak": max_l}


def _group_stats(items: List[dict], keyfn: Callable[[dict], Optional[str]]) -> List[dict]:
    groups: Dict[str, List[int]] = {}
    for a in items:
        k = keyfn(a)
        if k is None:
            continue
        g = groups.setdefault(k, [0, 0])
        g[0] += 1
        g[1] += a["y"]
    rows = []
    for k in sorted(groups, key=lambda kk: (-groups[kk][0], kk)):
        n, w = groups[k]
        lo, hi = wilson(w, n)
        rows.append({"label": k, "n": n, "wins": w,
                     "rate": w / n, "ci_lo": lo, "ci_hi": hi})
    return rows


def _filter_row(name: str, desc: str, sub: List[dict], total: int) -> dict:
    w = sum(a["y"] for a in sub)
    lo, hi = wilson(w, len(sub))
    return {"filter": name, "rule": desc, "n": len(sub), "wins": w,
            "rate": (w / len(sub)) if sub else None,
            "ci95": {"lo": lo, "hi": hi},
            "pct_of_resolved": (len(sub) / total) if total else None}


class AlertAudit:
    def __init__(self, alerts: Sequence[dict]):
        self._raw = [a for a in alerts if isinstance(a, dict)]
        self._prepared: List[dict] = []
        self._dupes = 0
        self._runs = 0
        self._last: Optional[dict] = None
        self._prepare()

    def _prepare(self) -> None:
        seen = set()
        for r in self._raw:
            r = _expand_nested(r)
            fp_src = {f: r.get(f) for f in _FP_FIELDS}
            try:
                fp = hashlib.sha256(json.dumps(
                    fp_src, sort_keys=True, default=str,
                    ensure_ascii=False).encode("utf-8")).hexdigest()
            except (TypeError, ValueError):
                fp = "id-%d" % id(r)
            if fp in seen:
                self._dupes += 1
                continue
            seen.add(fp)
            dom: Dict[str, Optional[float]] = {}
            for base, ck, vk in _STAT_PAIRS:
                c, v = _num(r.get(ck)), _num(r.get(vk))
                if c is None or v is None:
                    dom[base] = None
                    dom[base + "_diff"] = None
                elif c >= v:
                    dom[base], dom[base + "_diff"] = c, c - v
                else:
                    dom[base], dom[base + "_diff"] = v, v - c
            self._prepared.append({
                "y": parse_outcome(r.get("resultado")),
                "minute": parse_minute(r.get("tempo")),
                "odd": _num(r.get("odd_entrada")),
                "dom": dom,
                "when": str(r.get("data_hora") or ""),
                "id": r.get("id"),
                "tipo": str(r.get("tipo_alerta") or "sem tipo"),
                "liga": str(r.get("liga") or "sem liga"),
            })

    @property
    def resolved(self) -> List[dict]:
        return [a for a in self._prepared if a["y"] is not None]

    def run(self) -> dict:
        self._runs += 1
        resolved = self.resolved
        n = len(resolved)
        wins = sum(a["y"] for a in resolved)
        lo, hi = wilson(wins, n)
        report: Dict[str, Any] = {
            "tool": "robot_alert_audit", "version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": {
                "raw": len(self._raw),
                "duplicates_removed": self._dupes,
                "prepared": len(self._prepared),
                "outcome_unknown": len(self._prepared) - n,
                "resolved": n, "wins": wins, "losses": n - wins,
            },
            "hit_rate": (wins / n) if n else None,
            "hit_rate_ci95": {"lo": lo, "hi": hi},
        }
        withodd = [a for a in resolved if a["odd"] is not None]
        ev_block: Dict[str, Any] = {"n_with_odds": len(withodd)}
        if withodd:
            avg_odd = sum(a["odd"] for a in withodd) / len(withodd)
            if avg_odd > 1.0:
                w2 = sum(a["y"] for a in withodd)
                lo2, hi2 = wilson(w2, len(withodd))
                be = 1.0 / avg_odd
                p = binom_p_ge(w2, len(withodd), be)
                verdict = (
                    "NAO distinguivel do sem-edge implicito na odd ao nivel de 5%% (p=%.3f)" % p
                    if p >= 0.05 else
                    "excede o sem-edge implicito na odd ao nivel de 5%% (p=%.3f); "
                    "validacao em dados NOVOS continua obrigatoria" % p)
                ev_block.update({
                    "wins_with_odds": w2, "avg_odd": avg_odd,
                    "breakeven_p": be,
                    "hit_rate_with_odds": w2 / len(withodd),
                    "ci95_with_odds": {"lo": lo2, "hi": hi2},
                    "ev_per_unit": (w2 / len(withodd)) * avg_odd - 1.0,
                    "ev_ci95": {"lo": lo2 * avg_odd - 1.0,
                                "hi": hi2 * avg_odd - 1.0},
                    "binom_p_vs_breakeven": p, "verdict": verdict,
                })
            else:
                ev_block["avg_odd"] = avg_odd
                ev_block["verdict"] = "odd media <= 1.0 — dados de odd suspeitos"
        report["ev"] = ev_block
        ordered = sorted(resolved, key=lambda a: (a["when"], str(a["id"])))
        report["streaks"] = _streaks([a["y"] for a in ordered])
        report["by_odd_band"] = _group_stats(withodd, _odd_band)
        report["by_half"] = _group_stats(resolved, _half_of)
        report["by_tipo"] = _group_stats(resolved, lambda a: a["tipo"])[:12]
        report["by_liga"] = _group_stats(resolved, lambda a: a["liga"])[:12]
        frows = [_filter_row(nm, ds, [a for a in resolved if fn(a)], n)
                 for nm, ds, fn in FILTERS]
        sub_all = [a for a in resolved if all(fn(a) for _nm, _ds, fn in FILTERS)]
        frows.append(_filter_row("CHECKLIST", "F1..F6 simultaneos", sub_all, n))
        report["filters"] = frows
        self._last = report
        return report

    def stats(self) -> dict:
        last = self._last or {}
        ev = last.get("ev") or {}
        return {"robot_alert_audit": {
            "runs": self._runs,
            "raw": len(self._raw), "prepared": len(self._prepared),
            "duplicates_removed": self._dupes,
            "last_hit_rate": last.get("hit_rate"),
            "last_binom_p": ev.get("binom_p_vs_breakeven"),
            "last_ev_per_unit": ev.get("ev_per_unit"),
        }}


def _md_table(rows: List[dict], cols: List[str]) -> str:
    if not rows:
        return "_(sem dados)_"
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if v is None:
                cells.append("-")
            elif isinstance(v, float):
                cells.append("%.3f" % v)
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown(rep: dict) -> str:
    c = rep["counts"]
    L: List[str] = []
    L.append("# Auditoria de tipster externo (robô de alertas)")
    L.append("")
    L.append("*gerado: %s · robot_alert_audit v%s*" % (rep.get("generated_at"), rep.get("version")))
    L.append("")
    L.append("**Papel:** análise estatística em paper. Nenhuma recomendação de aposta,")
    L.append("stake ou execução sai daqui (§0). O robô é tipster externo sendo auditado.")
    L.append("")
    L.append("## Cabeçalho da amostra")
    L.append("")
    L.append("| métrica | valor |")
    L.append("|---|---|")
    L.append("| alertas brutos | %d |" % c["raw"])
    L.append("| duplicatas removidas | %d |" % c["duplicates_removed"])
    L.append("| únicos preparados | %d |" % c["prepared"])
    L.append("| resolvidos (com outcome) | %d |" % c["resolved"])
    L.append("| verdes / vermelhos | %d / %d |" % (c["wins"], c["losses"]))
    L.append("| outcome desconhecido | %d |" % c["outcome_unknown"])
    L.append("")
    if rep.get("hit_rate") is not None:
        ci = rep["hit_rate_ci95"]
        L.append("## Taxa de acerto (resolvidos)")
        L.append("")
        L.append("**%.1f%%** — IC 95%% (Wilson): **[%.1f%%, %.1f%%]**"
                 % (100 * rep["hit_rate"], 100 * ci["lo"], 100 * ci["hi"]))
        L.append("")
    ev = rep.get("ev") or {}
    if ev.get("breakeven_p") is not None:
        L.append("## Valor esperado vs. mercado (subset com odd)")
        L.append("")
        L.append("| métrica | valor |")
        L.append("|---|---|")
        L.append("| n com odd | %d |" % ev["n_with_odds"])
        L.append("| odd média | %.3f |" % ev["avg_odd"])
        L.append("| prob. de empate implícita | %.1f%% |" % (100 * ev["breakeven_p"]))
        L.append("| taxa (subset) | %.1f%% |" % (100 * ev["hit_rate_with_odds"]))
        L.append("| EV por unidade | %+.1f%% |" % (100 * ev["ev_per_unit"]))
        L.append("| IC 95%% do EV | [%+.1f%%, %+.1f%%] |"
                 % (100 * ev["ev_ci95"]["lo"], 100 * ev["ev_ci95"]["hi"]))
        L.append("| P(X≥%d \\| n=%d, p=empate implícito) | %.3f |"
                 % (ev["wins_with_odds"], ev["n_with_odds"], ev["binom_p_vs_breakeven"]))
        L.append("")
        L.append("**Veredito do teste:** %s." % ev["verdict"])
        L.append("")
    st = rep.get("streaks") or {}
    if st:
        L.append("## Sequências")
        L.append("")
        L.append("- maior sequência de verdes: %d" % st.get("max_win_streak", 0))
        L.append("- maior sequência de vermelhos: %d" % st.get("max_loss_streak", 0))
        L.append("")
    for title, key in (("Quebra por faixa de odd", "by_odd_band"),
                       ("Quebra por metade do jogo", "by_half"),
                       ("Quebra por tipo de alerta", "by_tipo"),
                       ("Quebra por liga (top)", "by_liga")):
        L.append("## %s" % title)
        L.append("")
        L.append(_md_table(rep.get(key) or [], ["label", "n", "wins", "rate", "ci_lo", "ci_hi"]))
        L.append("")
    L.append("## Filtros pré-registrados (transcritos dos docs de padrão verde)")
    L.append("")
    frows = [{"filter": r["filter"], "rule": r["rule"], "n": r["n"], "wins": r["wins"],
              "rate": r["rate"], "ci_lo": (r["ci95"] or {}).get("lo"),
              "ci_hi": (r["ci95"] or {}).get("hi"),
              "pct_of_resolved": r["pct_of_resolved"]} for r in rep.get("filters") or []]
    L.append(_md_table(frows, ["filter", "rule", "n", "wins", "rate",
                               "ci_lo", "ci_hi", "pct_of_resolved"]))
    L.append("")
    L.append("## Honestidade estatística (leia antes de citar QUALQUER número acima)")
    L.append("")
    L.append("1. Os filtros desta suíte foram transcritos de documentos minerados **post-hoc**")
    L.append(" nos mesmos dados que os geraram. Taxa alta em subconjunto escolhido DEPOIS")
    L.append(" de ver os resultados é **hipótese, não evidência**. Validação mínima: rodar")
    L.append(" os mesmos filtros em alertas ainda não coletados (out-of-sample).")
    L.append("2. Outcome rotulado por emoji de Telegram; o dataset original contém")
    L.append(" duplicatas de reenvio (removidas aqui: %d)." % c["duplicates_removed"])
    if rep.get("hit_rate_ci95", {}).get("lo") is not None:
        ci = rep["hit_rate_ci95"]
        L.append("3. n=%d é pequeno: o IC 95%% da taxa tem largura de %.0f pontos"
                 % (c["resolved"], 100 * (ci["hi"] - ci["lo"])))
        L.append(" percentuais — o conjunto de dados é consistente tanto com \"sem edge\"")
        L.append(" quanto com \"edge grande\". Ele não decide.")
    L.append("4. EV calculado sobre odd média; alertas sem odd ficam fora do bloco de EV.")
    L.append("5. Escanteio é evento raro ~Poisson com teto de previsibilidade baixo (§8).")
    L.append(" Ferramenta nenhuma fabrica edge; esta só evita desperdiçar o pouco que existe.")
    L.append("")
    return "\n".join(L)


def _print_summary(rep: dict) -> None:
    c = rep["counts"]
    print("== robot_alert_audit v%s ==" % rep["version"])
    print("brutos: %d | duplicatas removidas: %d | resolvidos: %d (verdes %d / vermelhos %d)"
          % (c["raw"], c["duplicates_removed"], c["resolved"], c["wins"], c["losses"]))
    if rep["hit_rate"] is not None:
        ci = rep["hit_rate_ci95"]
        print("taxa de acerto: %.1f%% [IC95: %.1f%% - %.1f%%]"
              % (100 * rep["hit_rate"], 100 * ci["lo"], 100 * ci["hi"]))
    ev = rep.get("ev") or {}
    if ev.get("breakeven_p") is not None:
        print("com odd: n=%d | odd media %.3f | empate implicito %.1f%%"
              % (ev["n_with_odds"], ev["avg_odd"], 100 * ev["breakeven_p"]))
        print("EV por unidade: %+.1f%% [IC95: %+.1f%% a %+.1f%%]"
              % (100 * ev["ev_per_unit"], 100 * ev["ev_ci95"]["lo"], 100 * ev["ev_ci95"]["hi"]))
        print("binomial vs sem-edge: P(X>=%d | n=%d, p=%.3f) = %.3f"
              % (ev["wins_with_odds"], ev["n_with_odds"],
                 ev["breakeven_p"], ev["binom_p_vs_breakeven"]))
        print("veredito: %s" % ev["verdict"])
    print("filtros pre-registrados (n colapsa):")
    for r in rep.get("filters") or []:
        rate = ("%.1f%%" % (100 * r["rate"])) if r["rate"] is not None else "-"
        pct = ("%.0f%%" % (100 * r["pct_of_resolved"])) if r["pct_of_resolved"] is not None else "-"
        print(" %-9s n=%-4d acerto=%-6s pct_do_total=%s" % (r["filter"], r["n"], rate, pct))


def _atomic_write(path: str, content: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.replace(tmp, path)


def load_alerts(paths: Sequence[str]) -> List[dict]:
    alerts: List[dict] = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as exc:
            print("[aviso] nao consegui ler %s: %s" % (p, exc))
            continue
        stripped = text.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, dict):
            data = (data.get("entradas") or data.get("alerts")
                    or data.get("data") or data.get("entries") or [])
        if isinstance(data, list):
            alerts.extend(x for x in data if isinstance(x, dict))
        elif data is None:
            for line in stripped.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    alerts.append(obj)
    return alerts


def _self_test() -> int:
    import tempfile
    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    check("wilson(0,10) contiene zero", wilson(0, 10)[0] <= 1e-12)
    lo, hi = wilson(25, 36)
    check("wilson(25,36) ~ [0.53, 0.82]", 0.51 < lo < 0.55 and 0.80 < hi < 0.84,
          "lo=%.3f hi=%.3f" % (lo, hi))
    check("binom conhecido", abs(binom_p_ge(2, 2, 0.5) - 0.25) < 1e-12)
    check("binom k=0 -> 1", binom_p_ge(0, 5, 0.3) == 1.0)
    check("binom k>n -> 0", binom_p_ge(6, 5, 0.5) == 0.0)
    check("binom p=1 -> 1", binom_p_ge(3, 3, 1.0) == 1.0)
    check("EV basico", abs(0.6 * 1.8 - 1.0 - 0.08) < 1e-12)
    check("minuto '85M'", parse_minute("85M") == 85)
    check("minuto '43:04'", parse_minute("43:04") == 43)
    check("minuto int", parse_minute(21) == 21)
    check("minuto None", parse_minute(None) is None)
    check("outcome verde", parse_outcome("\u2705") == 1)
    check("outcome vermelho", parse_outcome("\u274c") == 0)
    check("outcome 'GREEN'", parse_outcome("GREEN") == 1)
    check("outcome lixo -> None", parse_outcome("qualquer") is None)
    st = _streaks([1, 1, 0, 1])
    check("streaks", st["max_win_streak"] == 2 and st["max_loss_streak"] == 1)

    nested = {
        "id": 1, "liga": "Australia NPL Victoria",
        "jogo": "Hume City vs Dandenong City", "tempo": "86'", "placar": "0-0",
        "entrada": {"mercado": "MAIS DE 7.5", "odd": 1.725},
        "estatisticas": {"posse": "51%-49%", "pressao1": "18-40",
                         "appm": "0.59-0.73", "escanteios": "3-4",
                         "chutes_totais": "8-9", "chutes_alvo": "3-3"},
        "resultado": "\u2705", "data_hora": "2026-07-04 02:43:00",
    }
    exp = _expand_nested(nested)
    check("nested: posse", exp.get("posse_casa") == 51 and exp.get("posse_visit") == 49)
    check("nested: pressao1", exp.get("pressao1_casa") == 18 and exp.get("pressao1_visit") == 40)
    check("nested: appm", exp.get("appm_total_casa") == 0.59)
    check("nested: odd", exp.get("odd_entrada") == 1.725)

    def mk(i, y, jogo=None, odd=1.72, minute=86, a5=(1.2, 0.3), a10=(0.9, 0.4),
           p1=(30, 18), ct=(12, 5), ca=(4, 1)):
        return {"id": i, "data_hora": "2026-07-%02d 12:00:00" % (i + 1),
                "tipo_alerta": "BOT FT", "liga": "Liga X",
                "jogo": jogo or ("Jogo %d" % i), "tempo": "%dM" % minute,
                "placar": "0-0", "odd_entrada": odd, "mercado": "MAIS DE 9.5",
                "appm_5min_casa": a5[0], "appm_5min_visit": a5[1],
                "appm_10min_casa": a10[0], "appm_10min_visit": a10[1],
                "pressao1_casa": p1[0], "pressao1_visit": p1[1],
                "chutes_totais_casa": ct[0], "chutes_totais_visit": ct[1],
                "chutes_alvo_casa": ca[0], "chutes_alvo_visit": ca[1],
                "resultado": "\u2705" if y else "\u274c"}

    alerts = [mk(i, i % 2) for i in range(10)]
    alerts.append(dict(alerts[0]))
    resended = dict(alerts[1])
    resended["data_hora"] = "2026-07-99 23:00:00"
    alerts.append(resended)
    invalid = mk(99, 1, jogo="Jogo 99")
    invalid["resultado"] = "?"
    alerts.append(invalid)

    audit = AlertAudit(alerts)
    rep = audit.run()
    c = rep["counts"]
    check("contagens: brutos=13", c["raw"] == 13)
    check("contagens: duplicatas=2 (exata + reenvio)", c["duplicates_removed"] == 2)
    check("contagens: preparados=11", c["prepared"] == 11)
    check("contagens: resolvidos=10, verdes=5", c["resolved"] == 10 and c["wins"] == 5)
    check("contagens: outcome desconhecido=1", c["outcome_unknown"] == 1)
    check("hit_rate=0.5", abs(rep["hit_rate"] - 0.5) < 1e-12)
    check("EV com odd presente", rep["ev"].get("breakeven_p") is not None)
    flt = {r["filter"]: r for r in rep["filters"]}
    check("todos os sinteticos passam o checklist", flt["CHECKLIST"]["n"] == 10)
    check("F1 n=10", flt["F1"]["n"] == 10)

    audit2 = AlertAudit([mk(50, 1), mk(51, 1, a5=(0.3, 0.2))])
    rep2 = audit2.run()
    flt2 = {r["filter"]: r for r in rep2["filters"]}
    check("checklist exclui alerta sem pico de APPM", flt2["CHECKLIST"]["n"] == 1)

    audit_nest = AlertAudit([nested])
    rep_nest = audit_nest.run()
    check("formato aninhado: 1 resolvido", rep_nest["counts"]["resolved"] == 1)
    flt_nest = {r["filter"]: r for r in rep_nest["filters"]}
    check("formato aninhado sem APPM5 -> checklist n=0 (nao inventa)",
          flt_nest["CHECKLIST"]["n"] == 0)

    stt = audit.stats()["robot_alert_audit"]
    check("stats() coerente", stt["runs"] == 1 and stt["prepared"] == 11
          and stt["duplicates_removed"] == 2)

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "rep.md")
        _atomic_write(p, render_markdown(rep))
        with open(p, "r", encoding="utf-8") as fh:
            content = fh.read()
        check("md gravado e sem tmp orfao",
              os.path.exists(p) and not os.path.exists(p + ".%d.tmp" % os.getpid()))
        check("md contem secao de honestidade", "Honestidade estat" in content)
        check("md contem tabela de filtros", "CHECKLIST" in content)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s" % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - robot_alert_audit.py")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="robot_alert_audit.py",
        description="Auditoria estatistica honesta de datasets de alertas de tipster externo")
    ap.add_argument("paths", nargs="*", default=[], help="dataset .json/.jsonl")
    ap.add_argument("--md", default=None, help="grava relatorio markdown no caminho")
    ap.add_argument("--json", default=None, help="grava relatorio JSON no caminho")
    ap.add_argument("--self-test", action="store_true", help="valida a propria ferramenta")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    paths = list(args.paths)
    if not paths:
        if os.path.exists("dataset_completo.json"):
            paths = ["dataset_completo.json"]
        else:
            print("uso: python robot_alert_audit.py <dataset.json ...> [--md saida.md] [--json saida.json]")
            return 2

    alerts = load_alerts(paths)
    if not alerts:
        print("[erro] nenhum alerta carregado de: %s" % ", ".join(paths))
        return 2

    audit = AlertAudit(alerts)
    rep = audit.run()
    _print_summary(rep)
    if args.md:
        _atomic_write(args.md, render_markdown(rep))
        print("relatorio markdown: %s" % args.md)
    if args.json:
        _atomic_write(args.json, json.dumps(rep, indent=2, ensure_ascii=True, default=str))
        print("relatorio json: %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
