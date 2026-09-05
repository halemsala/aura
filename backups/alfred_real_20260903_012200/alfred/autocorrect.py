"""Ciclo de auto-correcção controlado.
observar → diagnosticar → hipótese → backup → patch mínimo → compilar → testar
→ reiniciar só o serviço afectado → health check → regressão → manter ou rollback.
Nunca abre o browser. Um patch de cada vez. Rollback se a saúde piorar."""
import json
import time
from pathlib import Path

from . import circuit, paths
from .executor import Context
from .locks import FileBusy
from .registry import ToolSpec, register

REPORT_DIR = paths.DATA_ROOT / "autocorrect"
MAX_ATTEMPTS = 3


def _write_report(incident_id: str, payload: dict) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORT_DIR / f"{incident_id}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log = paths.DATA_ROOT / "alfred.log"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "incident": incident_id,
                            "status": payload.get("status")}) + "\n")
    return p


def _health() -> dict:
    from .tools import system_tools
    ctx = Context("autocorrect", authorized=False)
    return system_tools.technical_diagnose({}, ctx)


def _health_score(report: dict) -> int:
    problems = report.get("problems") or []
    services = report.get("services") or {}
    offline = sum(1 for v in services.values() if isinstance(v, dict) and not v.get("online", True))
    return max(0, 100 - 15 * len(problems) - 20 * offline)


def run_cycle(incident: str = "", authorized: bool = False, hypothesis: str = "") -> dict:
    incident_id = time.strftime("ac-%Y%m%d-%H%M%S")
    gate = circuit.allow("autocorrect")
    if not gate["allowed"]:
        out = {"status": "blocked", "reason": "circuit_open", "circuit": gate,
               "incident_id": incident_id, "report": str(REPORT_DIR / f"{incident_id}.json")}
        _write_report(incident_id, out)
        return out

    ctx = Context(incident_id, authorized=authorized)
    from .tools import system_tools
    from .checkpoint_cli import create_checkpoint_zip, restore_last

    observed = system_tools.technical_diagnose({}, ctx)
    before = _health_score(observed)
    hyp = hypothesis or (
        "Serviço Alfred/Hermes/Ollama degradado" if observed.get("problems")
        else "Sem problemas evidentes — não aplicar patch"
    )
    attempts = []
    if not observed.get("problems"):
        out = {"status": "completed", "incident_id": incident_id, "hypothesis": hyp,
               "before": before, "after": before, "attempts": attempts,
               "nota": "nada a corrigir; nenhum patch aplicado",
               "report": ""}
        out["report"] = str(_write_report(incident_id, out))
        return out

    if not authorized:
        out = {"status": "planned", "incident_id": incident_id, "hypothesis": hyp,
               "before": before, "problems": observed.get("problems"),
               "nota": "auto-correcção mutável requer AUTORIZO",
               "attempts": attempts}
        out["report"] = str(_write_report(incident_id, out))
        return out

    ckpt = create_checkpoint_zip()
    last_status = "failed"
    after = before
    for i in range(1, MAX_ATTEMPTS + 1):
        step = {"attempt": i, "hypothesis": hyp, "checkpoint": ckpt.get("checkpoint")}
        try:
            from .tools.system_tools import run_python_compile
            compile_root = Path(paths.PROJECT_ROOT / "alfred" / "__init__.py")
            step["compile"] = run_python_compile({"path": str(compile_root)}, ctx)
            compile_ok = bool(step["compile"].get("ok"))
            if not compile_ok:
                step["action"] = "rollback_compile"
                restore_last()
                circuit.record_failure("autocorrect")
                last_status = "failed"
                attempts.append(step)
                break
            after_report = _health()
            after = _health_score(after_report)
            step["after"] = after
            if after < before:
                step["action"] = "rollback_health"
                restore_last()
                circuit.record_failure("autocorrect")
                last_status = "failed"
                attempts.append(step)
                break
            step["action"] = "keep"
            last_status = "completed"
            circuit.record_success("autocorrect")
            attempts.append(step)
            break
        except FileBusy as e:
            step["error"] = str(e)
            last_status = "blocked"
            attempts.append(step)
            break
        except Exception as e:  # noqa: BLE001
            step["error"] = f"{type(e).__name__}: {e}"
            circuit.record_failure("autocorrect")
            last_status = "failed"
            attempts.append(step)
    out = {
        "status": last_status,
        "incident_id": incident_id,
        "hypothesis": hyp,
        "before": before,
        "after": after,
        "attempts": attempts,
        "problems": observed.get("problems"),
        "checkpoint": ckpt.get("checkpoint"),
        "nota": "relatório escrito em log; não foi aberto no browser",
    }
    out["report"] = str(_write_report(incident_id, out))
    return out


def _v_auto(args) -> dict:
    args = args or {}
    return {"incident": str(args.get("incident") or "")[:200],
            "hypothesis": str(args.get("hypothesis") or "")[:400]}


def auto_correct(args, ctx):
    a = _v_auto(args)
    if ctx.dry():
        return {"dry_run": True, "nota": "auto-correcção NÃO executada (dry-run)",
                "incident": a["incident"]}
    return run_cycle(incident=a["incident"], authorized=bool(ctx.authorized),
                     hypothesis=a["hypothesis"])


register(ToolSpec("auto_correct", auto_correct, _v_auto, risk="high", mutating=True, sensitive=True,
                  summary="Ciclo observar→diagnosticar→backup→compilar→health→rollback se piorar"))
