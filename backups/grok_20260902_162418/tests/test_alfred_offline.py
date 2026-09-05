# tests/test_alfred_offline.py — ficheiro REAL (ignora o bloco de nota acima)
import threading, time, uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from alfred import paths, security, util
from alfred.bridge import EXECUTOR, STORE, STATE, try_handle
from alfred.config import get_config
from alfred.executor import Context, Plan, Task
from alfred.planner import plan_from_message
from alfred.registry import ToolSpec, register
from alfred.validators import ValidationError, resolve_allowed, validate_url


# ---------- (1)(2)(3)(4) router/plano ----------
def test_model_is_qwen3():
    assert get_config()["model"] == "qwen3:8b"


def test_router_recognizes_alfred():
    from alfred.router import is_alfred_message, strip_prefix
    assert is_alfred_message("Alfred, abre três pesquisas sobre automação")
    assert is_alfred_message("AURA Alfred, estado")
    assert not is_alfred_message("olá tudo bem?")


def test_three_search_plan_exact_3():
    plan = plan_from_message("abre três pesquisas sobre automação industrial", client=None)
    assert len(plan.tasks) == 3
    assert all(t.tool == "open_url" for t in plan.tasks)
    assert plan.intent == "search_multi"
    assert plan.requires_confirmation is True
    assert all(t.arguments["url"].startswith("https://www.google.com/search?q=") for t in plan.tasks)


def test_alfred_status_works_offline():
    r = try_handle("Alfred, estado")
    assert r is not None and r["model"] == "alfred:qwen3:8b"
    assert "1 de 1" in r["reply"]


def test_alfred_help():
    r = try_handle("Alfred, ajuda")
    assert r is not None and "AUTORIZO" in r["reply"]


# ---------- (5) dry-run sem autorização ----------
def test_dry_run_without_authorization(test_home):
    from alfred.tools import files, open_url as ou
    ctx = Context("t-dry", authorized=False)
    r1 = files.create_folder({"name": "nao-existe", "parent": "Desktop"}, ctx)
    assert r1["dry_run"] is True and not (test_home / "Desktop" / "nao-existe").exists()
    r2 = files.write_text_file({"path": "Documents/x.txt", "text": "ola"}, ctx)
    assert r2["dry_run"] is True and not (test_home / "Documents" / "x.txt").exists()
    r3 = ou.open_url({"url": "https://example.com"}, ctx)
    assert r3["dry_run"] is True and r3.get("opened") is None


# ---------- (6) execução autorizada verificada ----------
def test_authorized_execution_verified(test_home):
    from alfred.tools import files
    ctx = Context("t-auth", authorized=True)
    name = f"pasta-{uuid.uuid4().hex[:6]}"
    r = files.create_folder({"name": name, "parent": "Desktop"}, ctx)
    assert r["created"] is True and Path(r["path"]).is_dir()
    p = test_home / "Documents" / f"f-{uuid.uuid4().hex[:6]}.txt"
    r2 = files.write_text_file({"path": str(p), "text": "v1"}, Context("t-auth2", authorized=True))
    assert r2["written"] is True and p.read_text(encoding="utf-8") == "v1"


def test_write_backup_and_rollback(test_home):
    from alfred.tools import files
    from alfred.registry import spec
    p = test_home / "Documents" / f"rb-{uuid.uuid4().hex[:6]}.txt"
    c1 = Context("a", authorized=True)
    files.write_text_file({"path": str(p), "text": "v1"}, c1)
    r2 = files.write_text_file({"path": str(p), "text": "v2"}, Context("b", authorized=True))
    assert r2["backup"] and Path(r2["backup"]).exists()
    assert spec("write_text_file").rollback({"path": str(p)}, r2, Context("c", authorized=True)) is True
    assert p.read_text(encoding="utf-8") == "v1"


# ---------- (7) caminhos fora da allowlist ----------
def test_paths_outside_allowlist_blocked():
    for bad in ("../../etc/passwd", "C:/Windows/System32/config/system",
                "C:/Windows/notas.txt", "//servidor/partilha/x.txt",
                "C:/Users/x/.ssh/id_rsa", "C:/Users/x/.env"):
        with pytest.raises(ValidationError):
            resolve_allowed(bad)


def test_traversal_blocked():
    with pytest.raises(ValidationError):
        resolve_allowed("Desktop/../../segredos")


# ---------- (8) URLs perigosas ----------
def test_dangerous_urls_blocked():
    for bad in ("javascript:alert(1)", "file:///C:/Windows/system.ini",
                "data:text/html,<script>1</script>", "", "ftp://x.com",
                "https://a.com/" + "x" * 3000, "https://user:pass@a.com"):
        with pytest.raises(ValidationError):
            validate_url(bad)
    assert validate_url("https://www.google.com/search?q=x") == "https://www.google.com/search?q=x"


# ---------- (9)(10) sem duplicação, sem ciclos ----------
def test_no_duplicate_processes_no_loops(monkeypatch, test_home):
    import webbrowser
    from alfred.tools import open_url as ou  # garante registo
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda u, new=0: calls.append(u) or True)
    topic = f"automação {uuid.uuid4().hex[:6]}"
    plan = plan_from_message(f"abre três pesquisas sobre {topic}", client=None)
    entry = EXECUTOR.submit(plan, authorized=True, reason="teste")
    assert len(calls) == 3                      # exactamente 3 aberturas, uma execução
    plan2 = plan_from_message(f"abre três pesquisas sobre {topic}", client=None)
    entry2 = EXECUTOR.submit(plan2, authorized=False, reason="teste")
    assert len(calls) == 3                      # dry-run/pending: zero novas aberturas
    # sem temporizadores em lado nenhum do código do Alfred (nenhum ciclo de 2 minutos)
    for p in (paths.PROJECT_ROOT / "alfred").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        assert "threading.Timer" not in src
        assert "schedule.every" not in src


def test_dedupe_same_pending_plan():
    topic = f"robotica {uuid.uuid4().hex[:6]}"
    p1 = plan_from_message(f"abre duas pesquisas sobre {topic}", client=None)
    e1 = EXECUTOR.submit(p1, authorized=False, reason="t")
    p2 = plan_from_message(f"abre duas pesquisas sobre {topic}", client=None)
    e2 = EXECUTOR.submit(p2, authorized=False, reason="t")
    assert e1["job"]["job_id"] == e2["job"]["job_id"]   # mesmo job, não duplicado
    assert e2["job"]["dedupe_hits"] == 1


# ---------- (11) cancelamento ----------
def test_cancel_blocks_pending_tasks():
    tool_name = f"test_slow_{uuid.uuid4().hex[:6]}"
    def fake_fn(args, ctx):
        time.sleep(0.3)
        return {"ok": True}
    register(ToolSpec(tool_name, fake_fn, lambda a: {}, risk="low", mutating=False))
    tasks = [Task(id=f"task-{i}", tool=tool_name, arguments={}, risk="low") for i in range(1, 6)]
    plan = Plan(request_id=uuid.uuid4().hex[:8], intent="multi_task",
                requires_confirmation=False, content_hash=uuid.uuid4().hex[:8], tasks=tasks)
    entry = STORE.create(plan, authorized=True, reason="teste")
    th = threading.Thread(target=EXECUTOR.run, args=(entry,), daemon=True)
    th.start()
    time.sleep(0.45)                       # tasks 1-2 terminam, 3+ ainda não começaram
    assert EXECUTOR.cancel(entry["job"]["job_id"]) is True
    th.join(timeout=6)
    statuses = {t["id"]: t["status"] for t in entry["job"]["tasks"]}
    assert statuses["task-3"] == "skipped" and statuses["task-5"] == "skipped"
    assert entry["job"]["status"] == "cancelled"


# ---------- (12) falhas visíveis ----------
def test_failure_visible_and_next_skipped():
    tasks = [Task(id="task-1", tool="ferramenta_inexistente", arguments={}, risk="low"),
             Task(id="task-2", tool="list_files", arguments={"path": "Desktop"}, risk="low")]
    plan = Plan(request_id=uuid.uuid4().hex[:8], intent="multi_task",
                requires_confirmation=False, content_hash=uuid.uuid4().hex[:8], tasks=tasks)
    entry = EXECUTOR.submit(plan, authorized=True, reason="teste")
    st = {t["id"]: t for t in entry["job"]["tasks"]}
    assert st["task-1"]["status"] == "failed" and "desconhecida" in st["task-1"]["error"]
    assert st["task-2"]["status"] == "skipped"
    assert "FALHOU" in entry["job"]["summary"] and entry["job"]["status"] == "failed"


# ---------- (13) checkpoint cria backup verificável ----------
def test_checkpoint_creates_zip():
    from alfred.tools import system_tools
    ctx = Context("t-ckpt", authorized=True)
    r = system_tools.create_checkpoint({}, ctx)
    assert Path(r["checkpoint"]).exists() and r["files"] > 0


# ---------- (14) todos os módulos compilam ----------
def test_all_modules_compile():
    import compileall, sys
    ok = compileall.compile_dir(str(paths.PROJECT_ROOT / "alfred"), quiet=2, force=True)
    assert ok, "compileall falhou — ver erros acima"


# ---------- segurança adicional ----------
def test_secrets_blocked_in_write():
    from alfred.tools import files
    with pytest.raises(ValidationError):
        files._v_write({"path": "Documents/x.txt", "text": "token: ghp_" + "a" * 40})
    with pytest.raises(ValidationError):
        files._v_write({"path": "Documents/x.txt", "text": "-----BEGIN RSA PRIVATE KEY-----"})


def test_personal_memory_needs_auth():
    from alfred.tools import memory
    r = memory.remember({"text": "o meu email é x@y.pt"}, Context("m", authorized=False))
    assert r.get("dry_run") is True and r.get("saved") is None


def test_sensitive_needs_execution_allowed():
    from alfred.tools import files
    cfg = get_config()
    old = cfg["execution_allowed"]
    try:
        cfg["execution_allowed"] = False
        ctx = Context("s", authorized=True)          # AUTORIZO, mas exec_allowed=False
        with pytest.raises(Exception):
            ctx.current_spec = registry.spec("write_text_file")
            files.write_text_file({"path": "Documents/s.txt", "text": "x"}, ctx)
    finally:
        cfg["execution_allowed"] = old
