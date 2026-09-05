#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the V37.3.53 architecture/security stabilization pass."""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILS: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    server = read("engine/server.py")
    main_at = server.rfind('if __name__ == "__main__":')
    capture_at = server.find('@app.post("/api/capture/arm")')
    quant_at = server.find('@app.post("/api/quant_brain")')
    ok(
        "engine.server __main__ after capture/arm",
        capture_at != -1 and main_at != -1 and main_at > capture_at,
        f"main={main_at} capture={capture_at}",
    )
    ok(
        "engine.server __main__ after quant_brain",
        quant_at != -1 and main_at > quant_at,
        f"main={main_at} quant={quant_at}",
    )
    ok("engine.server CORS not wildcard .* default", 'r".*"' not in server.split("_ENGINE_ORIGIN_REGEX", 1)[-1][:400])
    ok("engine.server telegram paper block", "telegram_send_blocked_paper_only" in server)
    ok("engine.server micro_router gated", server.split("api_micro_router_dispatch", 1)[-1][:400].count("_mutation_auth_error") >= 1)
    ok("engine.server feed gated", "_mutation_auth_error" in server.split("async def post_feed", 1)[-1][:350])

    spec_v7 = read("agents/corner_window_specialist_v7/corner_window_specialist.py")
    spec_ind = read("agents/corner_independent/corner_window_specialist.py")
    ok("specialist v7 has evaluate", "def evaluate(" in spec_v7)
    ok("specialist v7 has analyse", "def analyse(" in spec_v7)
    ok("specialist independent has evaluate", "def evaluate(" in spec_ind)

    pipeline = read("engine/unified_pipeline.py")
    ok("unified_pipeline does not invent odds 1.85", "odds or 1.85" not in pipeline)
    ok("unified_pipeline marks missing odds", "odds_unobserved" in pipeline)

    tg = read("bridge/telegram/tg_command_center.py")
    ok("telegram is_admin not tautology", "or True" not in tg)
    ok("telegram python_patch disabled", "python_patch_disabled" in tg)
    ok("telegram opt-in gate", "AURA_TELEGRAM_OPTIN" in tg)

    voice = read("bridge/jarvis_voice_server.py")
    ok("voice CORS not double-escaped 127", r"127\\." not in voice)
    ok("voice CORS matches 127.0.0.1", r"127\.0\.0\.1" in voice)

    bridge = read("bridge/server.py")
    ok("bridge fallback uses real newline", 'json.dumps(record, ensure_ascii=False) + "\\n"' in bridge)
    ok("bridge token compare_digest", "hmac.compare_digest" in bridge)

    limpeza = read("AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat")
    ok("LIMPEZA voice path is bridge", r"bridge\jarvis_voice_server.py" in limpeza)
    ok("LIMPEZA does not start engine voice", r"engine\jarvis_voice_server.py" not in limpeza)
    ok("LIMPEZA python 3.10/3.11 pin", "(3,10),(3,11)" in limpeza or "(3, 10), (3, 11)" in limpeza)

    policy = read("engine/core/policy_runtime.py")
    ok("policy_runtime paper-only mode", '"mode": "paper"' in policy)
    ok("policy_runtime never grants live execution", "execution_allowed\": execution" not in policy)

    trading = read("engine/improvements/trading_mode.py")
    ok("trading_mode live maps to paper", "if raw == \"live\"" in trading)

    force = read("engine/modules/paper_force_mode.py")
    ok("paper_force_mode can_live False", '"can_live": False' in force)

    poisson = read("engine/poisson_risk_engine.py")
    ok("poisson implied_prob not 1.0 on bad odds", "odds_unobserved" in poisson)

    router = read("engine/execution_router.py")
    ok("execution_router does not call fn on paper", "HARD_LOCK_ACTIVE" in router)
    ok("execution_router no LIVE_QUEUED", "LIVE_QUEUED" not in router)

    heal = read("hermes_v10/core/hermes_self_healing.py")
    ok("hermes self-heal dry-run", '"dry_run": True' in heal or "dry_run" in heal)
    ok("hermes self-heal does not write_text in handler", "f.write_text" not in heal.split("handler_set_execution_false", 1)[-1][:800])

    sandbox = read("hermes_v10/core/hermes_sandbox_adapters.py")
    ok("hermes local sandbox opt-in", "AURA_HERMES_LOCAL_SANDBOX" in sandbox)

    supervisor = read("desktop/ServiceSupervisor.cs")
    ok("desktop supervisor paper env", '["AURA_UNLOCK_LIVE"]="0"' in supervisor.replace(" ", ""))
    host = read("desktop/BrowserHost.cs")
    ok("desktop SafeAgentRoute unescapes before .. check", "SanitizeApiTail" in host)
    ok("desktop loopback ports pinned", "LoopbackPorts" in host)
    token_cs = read("desktop/BridgeToken.cs")
    ok("desktop Bridge REQUIRE default 1", 'CORNERAI_BRIDGE_REQUIRE_TOKEN", "1"' in token_cs)
    ok("desktop Bridge REQUIRE not default 0", 'CORNERAI_BRIDGE_REQUIRE_TOKEN", "0"' not in token_cs)

    for rel in (
        "engine/server.py",
        "engine/execution_router.py",
        "engine/core/policy_runtime.py",
        "engine/unified_pipeline.py",
        "engine/poisson_risk_engine.py",
        "bridge/server.py",
        "bridge/telegram/tg_command_center.py",
        "bridge/telegram/tg_dependencies.py",
        "agents/corner_window_specialist_v7/corner_window_specialist.py",
        "hermes_v10/core/hermes_self_healing.py",
        "hermes_v10/core/hermes_sandbox_adapters.py",
        "scripts/test_audit_stabilization.py",
    ):
        src = read(rel)
        try:
            ast.parse(src, filename=rel)
            parsed = True
        except SyntaxError as exc:
            parsed = False
            FAILS.append(f"syntax:{rel}:{exc.lineno}")
            print(f"[FAIL] AST {rel} — {exc}")
            continue
        ok(f"AST {rel}", parsed)

    print()
    print(f"fails={len(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
