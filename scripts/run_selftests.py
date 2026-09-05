"""
run_selftests.py — Runner de self-tests, manifest e auditoria de contratos
do AURA QUANT-X V25.

POR QUE EXISTE
    Protocolo atual: Grok roda `python <modulo>.py` e o self-test imprime
    PASS/FAIL. O lote defeituoso provou que isso sozinho nao basta: dois
    arquivos quebravam sozinhos (erro de sintaxe; teste que falhava), mas os
    tres MAIS perigosos passavam no proprio self-test enquanto sobrescreviam
    modulos criticos com stubs (browser_agent sem HeuristicWalker, replay sem
    ReplayClock, supervisor sem register_check). Self-test passando nao prova
    nada se o arquivo substitui modulo existente.

    Este runner fecha as tres lacunas:
    1. EXECUCAO ISOLADA — cada self-test roda em subprocesso serial, com
       timeout e tree-kill. patch_time() do replay, threads do governor e
       portas do MetricsServer nunca vazam entre modulos.
    2. MANIFEST — compara a arvore real contra o inventario do bloco de
       transferencia (+ modulos novos). Ausente = MISSING; desconhecido =
       extra (visibilidade do legado V25).
    3. CONTRATO — cada modulo do inventario e varrido por simbolos
       obrigatorios (regex word-boundary no FONTE; funciona ate em arquivo
       com sintaxe quebrada, sem importar nada). security.py tem os
       invariantes do paragrafo 0 verificados por AST: uma atribuicao
       EXECUTION_ALLOWED = True e CONTRACT_VIOLATION onde quer que esteja
       (sem falso-positivo em comentario ou string de log).

    Limite honesto: arquivos fora do inventario (legado) so ganham self-test
    executado, sem contrato — e FALHAS deles NAO derrubam o exit code
    (instalacao incremental). Registre-os no INVENTORY abaixo para estender
    a cobertura; o dicionario e CONFIGURACAO, nao codigo.

USO (salve em scripts/)
    python scripts\\run_selftests.py                 # suite completa
    python scripts\\run_selftests.py --list          # estatico: manifest+contratos+sintaxe
    python scripts\\run_selftests.py --only replay browser_agent
    python scripts\\run_selftests.py --skip neural_tts --timeout 300
    python scripts\\run_selftests.py --json rep.json --md rep.md
    python scripts\\run_selftests.py --fail-on-missing    # pos-instalacao completa
    python scripts\\run_selftests.py --self-test      # valida o PROPRIO runner (sandbox)

DESVIO CONSCIENTE DA CONVENCAO: sem argumentos o arquivo roda a SUITE (funcao
operacional primaria), nao o self-test dele mesmo. O self-test embutido
existe e roda com --self-test, em sandbox deterministico que reproduz os
cenarios do incidente (stub com self-test passando = CONTRACT_VIOLATION).

AUDITORIA DE SEGURANCA (decisoes deliberadas)
    - subprocess sempre com lista de argumentos; nunca shell=True;
    - env dos filhos filtrado por padrao (chaves AURA_*/GLM_*): nenhum
      self-test recebe token de Telegram ou GLM_API_KEY — nenhum teste
      dispara rede real. --keep-env desativa;
    - saida de filho vai para arquivo temporario; so o tail e lido (limite
      de memoria);
    - cwd do filho e tempdir descartavel: escritas relativas nao poluem a
      arvore do projeto (e paths com espaco funcionam por construcao);
    - o runner NUNCA importa codigo do projeto: arquivo quebrado nao derruba
      o orquestrador;
    - copias do runner na arvore nao sao executadas (marcador no fonte) —
      sem recursao acidental;
    - relatorios escritos com tmp + os.replace;
    - o runner EXECUTA codigo da arvore por design (e a funcao dele): so
      aponte --root para arvore confiavel.

INTEGRACAO (opcional, boot): REG.register_component("selftest_runner", runner.stats)

stdlib only. Python 3.9+. Windows compativel. Saida de console 100% ASCII.
"""
# AURA_SELFTEST_RUNNER_DO_NOT_EXECUTE — marcador anti-recursao (nao remova)
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Blindagem de encoding: stdout/stderr redirecionado para arquivo de log
# pode herdar cp1252 do console Windows em vez de UTF-8, derrubando print()
# com UnicodeEncodeError. Reconfigura com fallback seguro.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "1.1.0-V25T6"

SELF_PATH = os.path.abspath(__file__)
_RUNNER_MARKER = "AURA_SELFTEST_RUNNER_DO_NOT_EXECUTE"
_MAIN_RE = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:")

# ---- vereditos ------------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
TIMEOUT = "TIMEOUT"
SYNTAX_ERROR = "SYNTAX_ERROR"
CONTRACT = "CONTRACT_VIOLATION"
NO_SELFTEST = "NO_SELFTEST"
MISSING = "MISSING"
INFO = "INFO"
SKIPPED = "SKIPPED"

_SHORT = {PASS: "PASS", FAIL: "FAIL", TIMEOUT: "TIMEOUT", SYNTAX_ERROR: "SYNTAX",
          CONTRACT: "CONTRACT", NO_SELFTEST: "NO-MAIN", MISSING: "MISSING",
          INFO: "INFO", SKIPPED: "SKIP"}
_ORDER = [PASS, FAIL, TIMEOUT, SYNTAX_ERROR, CONTRACT, NO_SELFTEST, MISSING, INFO, SKIPPED]
_HARD = {FAIL, TIMEOUT, SYNTAX_ERROR, CONTRACT}

# ---- invariantes do paragrafo 0 (verificados por AST no security.py) ------
SECURITY_INVARIANTS: Tuple[Tuple[str, bool], ...] = (
    ("PAPER_TRADE", True),
    ("EXECUTION_ALLOWED", False),
    ("GLM_ADVISORY_ONLY", True),
)

OPTIONAL_DEPS = ["playwright", "selenium", "duckdb", "psutil", "pynvml", "weasyprint"]

SKIP_DIRS = {"__pycache__", "venv", ".venv", "node_modules", "build", "dist",
             ".tox", ".eggs", ".mypy_cache", ".pytest_cache"}

# ---------------------------------------------------------------------------
# INVENTARIO — CONFIGURACAO, NAO CODIGO. Edite conforme a arvore cresce.
#   symbols   = identificadores que DEVEM existir no fonte (word-boundary).
#   invariants= True ativa verificacao AST dos invariantes §0 neste arquivo.
# Um modulo presente sem um simbolo = CONTRACT_VIOLATION (suspeita de
# colisao/stub — o cenario do lote defeituoso).
# ---------------------------------------------------------------------------
INVENTORY: Dict[str, Dict[str, Any]] = {
    # --- engine/core ---
    "engine/core/feed_bus.py": {"desc": "hot path nao-bloqueante + sinks",
        "symbols": ["FeedBus", "JsonlSink", "LatestJsonSink", "flush_sync"]},
    "engine/core/conformal_gate.py": {"desc": "gate conformal split rolling",
        "symbols": ["ConformalRiskGate", "OutcomeResolver"]},
    "engine/core/mc_grid.py": {"desc": "grade Monte Carlo 4D",
        "symbols": ["CornerSimulator", "EffectiveRateModel", "sanity_check", "start_build_async"]},
    "engine/core/replay.py": {"desc": "replay deterministico + run_ab",
        "symbols": ["ReplayClock", "run_ab", "stream_digest", "extract_segment", "patch_time"]},
    "engine/core/analytics.py": {"desc": "journals -> SQL (duckdb/sqlite) v1.1+",
        "symbols": ["fill_decision_outcomes", "q_window_yield", "q_calibration",
                    "q_coverage", "q_feed_health", "q_decision_scorecard",
                    "_delete_by_file", "_migrate"]},
    "engine/core/observability.py": {"desc": "registry + metrics server",
        "symbols": ["Registry", "MetricsServer", "register_component", "timer_us"]},
    "engine/core/error_handler.py": {"desc": "matador de silencio",
        "symbols": ["install_global", "safe_call", "safe_decorator"]},
    "engine/core/security.py": {"desc": "invariantes §0 imutaveis",
        "symbols": ["SecurityGuard", "PAPER_TRADE", "EXECUTION_ALLOWED", "GLM_ADVISORY_ONLY"],
        "invariants": True},
    "engine/core/hardware_governor.py": {"desc": "limitador 85% VRAM/CPU",
        "symbols": ["can_run_background", "pynvml", "nvidia"]},
    "engine/core/autonomous_cache.py": {"desc": "limpeza de RAM por prioridade",
        "symbols": ["AutonomousCache", "psutil"]},
    "engine/core/cache_integration.py": {"desc": "registra cleanups globais",
        "symbols": ["start_cache_management"]},
    "engine/core/meta_labeling.py": {"desc": "DESATIVADO ate green-light",
        "symbols": ["take_bet"]},
    # --- engine/agents ---
    "engine/agents/supervisor_jarvis.py": {"desc": "loop de checagens plugaveis",
        "symbols": ["register_check", "run_once", "alert_callback"]},
    "engine/agents/telegram_hq.py": {"desc": "bot 2FA long-polling",
        "symbols": ["TelegramHQ", "require_pin", "allowed_chat_ids"]},
    "engine/agents/browser_agent.py": {"desc": "interceptacao de API SokkerPRO v4",
        "symbols": ["BrowserAgent", "HeuristicWalker", "FixtureState", "GLMBridge",
                    "extract_view", "get_active_fixture", "_WSDecoder"]},
    "engine/agents/cross_site_analyst.py": {"desc": "tips externas + reputacao",
        "symbols": ["register_site", "TipsterReputation", "ConsensusEngine",
                    "EdgeDetector", "TipQualityScorer", "AdaptiveScheduler"]},
    "engine/agents/jarvis_persona.py": {"desc": "persona de voz JARVIS",
        "symbols": ["PERSONA_PROMPT", "SpeechFormatter", "MemoryStore",
                    "ProactiveEngine", "update_context"]},
    "engine/agents/persona_tools.py": {"desc": "function calling GLM-4",
        "symbols": ["TOOL_SCHEMAS", "PersonaToolRouter", "ContextProviders",
                    "call_glm_with_tools"]},
    # --- modulos novos (entregues em chats anteriores) ---
    "engine/core/sensor_cache.py": {"desc": "cache TTL p/ sensores GPU",
        "symbols": ["SensorCache"]},
    "engine/core/latency_sim.py": {"desc": "injetor de latencia p/ replay",
        "symbols": ["LatencyInjector"]},
    "engine/agents/tts_cache.py": {"desc": "cache LRU de disco p/ TTS",
        "symbols": ["TTSDiskCache"]},
    "engine/agents/tab_scheduler.py": {"desc": "prioridade multi-tab W1/W2",
        "symbols": ["TabScheduler"]},
    "engine/agents/greenlight_check.py": {"desc": "checker dos criterios §7",
        "symbols": ["GreenLightCheck"]},
    "engine/agents/people_memory.py": {"desc": "presenca, voz e memoria local opt-in",
        "symbols": ["PeopleMemory", "VoicePrint", "CameraWatcher"]},
    "engine/agents/research_improver.py": {"desc": "pesquisa de repos e papers",
        "symbols": ["ResearchImprover", "GithubSource", "ArxivSource", "parse_research"]},
    "engine/agents/media_editor.py": {"desc": "edicao ffmpeg com perfil criativo",
        "symbols": ["MediaEditor", "CreativeProfile", "parse_media"]},
    "engine/agents/desktop_controller.py": {"desc": "controle desktop teclado-first com gate",
        "symbols": ["DesktopController", "MacroStore", "DeskSession", "parse_desktop"]},
    "engine/agents/telegram_employee.py": {"desc": "funcionario Telegram opt-in",
        "symbols": ["TelegramEmployee", "TelegramAPI", "VoiceGateway"]},
    "engine/agents/voice_auth.py": {"desc": "autenticacao de voz opcional",
        "symbols": ["VoiceAuthGate", "CodeChallenge"]},
    "engine/agents/command_router_v2.py": {"desc": "roteamento contextual",
        "symbols": ["CommandRouterV2"]},
    "engine/agents/vision.py": {"desc": "visao sob demanda",
        "symbols": ["VisionPerceiver", "parse_vision"]},
    "engine/agents/external_intelligence.py": {"desc": "hub de APIs externas",
        "symbols": ["WikipediaSource", "DuckDuckGoSource", "JinaReaderSource",
                    "FootballDataOrg", "SemanticKnowledge", "parse_external_intel"]},
    "engine/agents/football_intelligence.py": {"desc": "dados e calculadoras de futebol",
        "symbols": ["OpenFootballSource", "CrossrefFootballSearch",
                    "FootballCalculators", "parse_football_intel"]},
    "engine/agents/football_research_hub.py": {"desc": "meta-pesquisador + mapa zonal",
        "symbols": ["FootballResearchHub", "MatchMap",
                    "build_research_hub_tools", "parse_research_hub"]},
    "engine/agents/enhanced_core.py": {"desc": "upgrades opcionais fail-closed",
        "symbols": ["EnhancedCore", "build_enhanced_tools", "_enabled"]},
    "engine/agents/natural_voice.py": {"desc": "voz natural opcional com fallback",
        "symbols": ["NaturalVoiceEngine", "get_natural_voice", "replace_synthesize_bytes"]},
    "engine/agents/tipster_capture.py": {"desc": "captador de tips Telegram + auditoria",
        "symbols": ["TipsterCaptureAgent", "TipsterJournal", "build_tipster_tools", "parse_tip_message"]},
    "engine/agents/intent_router.py": {"desc": "roteador de intenção LLM + cache semântico",
        "symbols": ["IntentRouter", "ContextProvider"]},
    "engine/agents/web_knowledge.py": {"desc": "RAG local JSONL",
        "symbols": ["ToolKnowledge"]},
    "engine/agents/persona_bridge.py": {"desc": "ponte de persona opt-in",
        "symbols": ["PersonaBridge", "build_system_prompt"]},
    "engine/boot.py": {"desc": "orquestrador defensivo",
        "symbols": ["AuraBoot", "Stage", "main"]},
    # --- superfícies endurecidas desta release ---
    "engine/admin/aura_admin_api.py": {"desc": "Admin Control Plane autenticado e com teto",
        "symbols": ["_require_admin_auth", "_require_approver_auth", "_enforce_mode_ceiling", "consume_many", "router"]},
    "engine/server.py": {"desc": "Engine com CORS e mutações fail-closed",
        "symbols": ["_mutation_auth_error", "AURA_MUTATION_TOKEN", "api_tools_activate_all", "feedback"]},
    "bridge/server.py": {"desc": "Bridge com token e CORS explícito",
        "symbols": ["_REQUIRE_BRIDGE_TOKEN", "_auth_ok", "X-CornerAI-Token", "_origin_allowed"]},
    "desktop/BrowserHost.cs": {"desc": "WebView2 com captura gated por host",
        "symbols": ["BrowserHost", "InitializeAsync", "IsSokkerHost", "InjectAuraCaptureAsync", "SetVirtualHostNameToFolderMapping"]},
    "desktop/Program.cs": {"desc": "Desktop single-instance mutex",
        "symbols": ["AURA_QUANTX_V25_DESKTOP_MUTEX", "Mutex", "Main"]},
    "desktop/packaging/AURA_Setup.iss": {"desc": "Inno Setup com mutex e exclusões runtime",
        "symbols": ["AppMutex", "engine", "duckdb", "session", "PrepareToInstall"]},
    "AURA_InPlace.ps1": {"desc": "apply reversível com lock stale e retenção",
        "symbols": ["Test-ProcessAlive", "started_at", "LockStaleAfterSeconds", "Prune-Backups", "BackupRetention"]},
    "AURA_ABRIR_DESKTOP_SEGURO.bat": {"desc": "launcher somente do publish identificado",
        "symbols": ["AURA_PUBLISH_INFO", "Aura.QuantX.Desktop.exe", "12.7.0-V25T6-OPERATOR-OS-INDEX-FIX"]},
    "scripts/aura_voice_client.py": {"desc": "cliente local de voz",
        "symbols": ["VoiceClient", "VoicePlayer", "EnergyVAD"]},
    # --- scripts / desktop ---
    "scripts/aura_weekly_analytics.py": {"desc": "job semanal de analytics",
        "symbols": ["weekly_report", "fill_decision_outcomes"]},
    "scripts/aura_docgen.py": {"desc": "doc viva dos modulos",
        "symbols": ["escape", "PERSONA_PROMPT"]},
        "scripts/robot_alert_audit.py": {"desc": "auditoria estatistica de tipster externo",
        "symbols": ["AlertAudit", "wilson", "binom_p_ge", "FILTERS"]},
    "desktop/Security/SecureStorage.cs": {"desc": "DPAPI C# (estatico)",
        "symbols": ["Store", "Retrieve", "Delete", "Exists"]},
}


# ---------------------------------------------------------------------------
# helpers puros
# ---------------------------------------------------------------------------
def _atomic_write(path: str, content: str) -> None:
    """Escrita atomica tmp + os.replace (convencao §6)."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    os.replace(tmp, path)


def _tail(fh, max_bytes: int = 65536) -> Tuple[str, int]:
    """Le o tail de um arquivo temporario preenchido por um filho."""
    try:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes))
        data = fh.read()
    except (OSError, ValueError):
        return "", 0
    return data.decode("utf-8", errors="replace"), size


def _kill_tree(proc: subprocess.Popen) -> None:
    """Mata o processo e sua arvore. Best-effort, nunca levanta."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _missing_symbols(symbols: List[str], text: str) -> List[str]:
    """Simbolos obrigatorios ausentes do fonte (word-boundary)."""
    missing = []
    for sym in symbols:
        if not re.search(r"\b%s\b" % re.escape(sym), text):
            missing.append(sym)
    return missing


def _const_bool(value: ast.AST) -> Optional[bool]:
    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return value.value
    return None


def _invariant_status(tree: ast.AST, wanted: Tuple[Tuple[str, bool], ...]
                      ) -> Tuple[List[str], List[str], List[str]]:
    """Verifica por AST os invariantes §0.

    Retorna (violacoes, nao_confirmados, confirmados). Violacao = atribuicao
    explicita com valor constante ERRADO (falha critica). Nao confirmado =
    nome ausente ou valor nao-constante (apenas aviso: a implementacao pode
    encapsular os valores de outra forma).
    """
    names = {name for name, _ in wanted}
    found: Dict[str, Optional[bool]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id in names:
                found[tgt.id] = _const_bool(node.value)
    violations, unconfirmed, confirmed = [], [], []
    for name, expect in wanted:
        if name not in found or found[name] is None:
            unconfirmed.append(name)
        elif found[name] != expect:
            violations.append("%s=%r (esperado %r)" % (name, found[name], expect))
        else:
            confirmed.append(name)
    return violations, unconfirmed, confirmed


def _default_root() -> str:
    here = os.path.dirname(SELF_PATH)
    if os.path.basename(here).lower() in ("scripts", "engine"):
        return os.path.dirname(here)
    return here


def _dep_probe_child(name: str) -> int:
    """Modo filho interno: importa um pacote e emite JSON. Nunca levanta."""
    result: Dict[str, Any] = {"module": name, "available": False,
                              "version": None, "error": None}
    try:
        import importlib
        importlib.import_module(name)
        result["available"] = True
        try:
            from importlib import metadata as _md
            result["version"] = _md.version(name)
        except Exception:
            pass
    except Exception as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    print(json.dumps(result))
    return 0


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
class SelfTestRunner:
    """Orquestra manifest + contratos + self-tests isolados + deps + relatorio."""

    def __init__(self,
                 root: str,
                 inventory: Optional[Dict[str, Dict[str, Any]]] = None,
                 timeout: float = 180.0,
                 dep_timeout: float = 60.0,
                 only: Optional[List[str]] = None,
                 skip: Optional[List[str]] = None,
                 run_selftests: bool = True,
                 scan_deps: bool = True,
                 strip_env: bool = True,
                 quiet: bool = False,
                 fail_on_missing: bool = False,
                 deps: Optional[List[str]] = None) -> None:
        self._root = os.path.abspath(root)
        self._inventory = dict(inventory) if inventory is not None else dict(INVENTORY)
        self._timeout = float(timeout)
        self._dep_timeout = float(dep_timeout)
        self._only = list(only) if only else []
        self._skip = list(skip) if skip else []
        self._run_selftests = bool(run_selftests)
        self._scan_deps = bool(scan_deps)
        self._strip_env = bool(strip_env)
        self._quiet = bool(quiet)
        self._fail_on_missing = bool(fail_on_missing)
        self._deps = list(deps) if deps is not None else list(OPTIONAL_DEPS)
        self._lock = threading.Lock()
        self._runs = 0
        self._last_report: Optional[Dict[str, Any]] = None
        self._texts: Dict[str, str] = {}
        self._extra_skipped = 0
        self._runner_copies_skipped = 0

    # ------------------------------------------------------------- utils
    @staticmethod
    def _soften_stdio() -> None:
        """Console cp1252 nunca quebra por acento/unicode vindo de filho."""
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass

    def _emit(self, msg: str) -> None:
        if not self._quiet:
            print(msg, flush=True)

    def _keep(self, rel: str) -> bool:
        low = rel.lower()
        if self._only and not any(s.lower() in low for s in self._only):
            return False
        if self._skip and any(s.lower() in low for s in self._skip):
            return False
        return True

    def _read_cached(self, abs_path: str) -> str:
        key = os.path.normcase(abs_path)
        if key not in self._texts:
            try:
                with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as fh:
                    self._texts[key] = fh.read()
            except OSError:
                self._texts[key] = ""
        return self._texts[key]

    def _is_runner_copy(self, full: str) -> bool:
        """O proprio runner ou copias dele (marcador) nunca sao executados."""
        if os.path.normcase(full) == os.path.normcase(SELF_PATH):
            return True
        try:
            with open(full, "rb") as fh:
                head = fh.read(8192)
        except OSError:
            return False
        return _RUNNER_MARKER.encode("utf-8") in head

    def _discover_extras(self) -> List[str]:
        """Varre a arvore e devolve .py fora do inventario (legado)."""
        extras: List[str] = []
        inv_keys = {rel.lower() for rel in self._inventory}
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = [d for d in sorted(dirnames)
                           if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                full = os.path.abspath(os.path.join(dirpath, fn))
                if self._is_runner_copy(full):
                    with self._lock:
                        self._runner_copies_skipped += 1
                    continue
                rel = os.path.relpath(full, self._root).replace(os.sep, "/")
                if rel.lower() in inv_keys:
                    continue
                extras.append(rel)
        return sorted(extras)

    # ---------------------------------------------------- analise estatica
    def _static_check(self, rel: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        abs_path = os.path.join(self._root, rel.replace("/", os.sep))
        rec: Dict[str, Any] = {"rel": rel, "desc": spec.get("desc", ""),
                               "in_inventory": True, "notes": [], "verdict": None}
        if not os.path.isfile(abs_path):
            rec["verdict"] = MISSING
            rec["notes"].append("arquivo ausente — instalacao incremental?")
            return rec
        text = self._read_cached(abs_path)
        if not rel.endswith(".py"):
            # C# e afins: contrato estatico apenas (nunca executado)
            missing = _missing_symbols(spec.get("symbols", []), text)
            if missing:
                rec["missing_symbols"] = missing
                rec["notes"].append("faltam: %s" % ", ".join(missing))
                rec["verdict"] = CONTRACT
            return rec
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            rec["verdict"] = SYNTAX_ERROR
            rec["notes"].append("linha %s: %s" % (getattr(exc, "lineno", 0) or 0, exc.msg))
            rec["has_main"] = bool(_MAIN_RE.search(text))
            return rec
        rec["has_main"] = bool(_MAIN_RE.search(text))
        missing = _missing_symbols(spec.get("symbols", []), text)
        if missing:
            rec["missing_symbols"] = missing
            rec["notes"].append("faltam: %s" % ", ".join(missing))
            rec["verdict"] = CONTRACT
        if spec.get("invariants"):
            violations, unconfirmed, _confirmed = _invariant_status(tree, SECURITY_INVARIANTS)
            if violations:
                rec["invariant_violations"] = violations
                rec["notes"].append("INVARIANTE §0 VIOLADO: %s" % "; ".join(violations))
                rec["verdict"] = CONTRACT
            if unconfirmed:
                rec["notes"].append("invariantes nao confirmados (aviso): %s"
                                    % ", ".join(unconfirmed))
        return rec

    # -------------------------------------------------------- execucao
    def _child_env(self) -> Optional[Dict[str, str]]:
        if not self._strip_env:
            return None
        env: Dict[str, str] = {}
        for k, v in os.environ.items():
            ku = k.upper()
            if ku.startswith("AURA_") or ku.startswith("GLM_"):
                continue
            env[k] = v
        return env

    def _run_selftest(self, rec: Dict[str, Any], rel: str) -> None:
        abs_path = os.path.join(self._root, rel.replace("/", os.sep))
        env = self._child_env()
        argv = [sys.executable, "-X", "utf8", abs_path]
        popen_extra: Dict[str, Any] = {}
        if os.name != "nt":
            popen_extra["start_new_session"] = True
        out_fh = tempfile.TemporaryFile(mode="w+b")
        try:
            with tempfile.TemporaryDirectory(prefix="aura_st_cwd_") as tmpcwd:
                t0 = time.monotonic()
                proc = subprocess.Popen(
                    argv, cwd=tmpcwd, env=env,
                    stdout=out_fh, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, **popen_extra)
                timed_out = False
                try:
                    proc.communicate(timeout=self._timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _kill_tree(proc)
                    try:
                        proc.communicate(timeout=10)
                    except Exception:
                        pass
                duration = time.monotonic() - t0
            tail, total_bytes = _tail(out_fh)
        finally:
            out_fh.close()
        rec["duration_s"] = round(duration, 2)
        rec["rc"] = proc.returncode
        rec["output_bytes"] = total_bytes
        rec["tail"] = tail[-4000:]
        if timed_out:
            rec["verdict"] = TIMEOUT
            rec["notes"].append("timeout apos %.1fs — processo e filhos mortos" % self._timeout)
            return
        if proc.returncode != 0:
            rec["verdict"] = FAIL
            rec["notes"].append("exit code %s" % proc.returncode)
        elif "[FAIL]" in tail:
            rec["verdict"] = FAIL
            rec["notes"].append("exit 0 mas stdout contem [FAIL] (modulo que mente)")
        else:
            rec["verdict"] = PASS

    def _maybe_execute(self, rec: Dict[str, Any], rel: str) -> None:
        if rec["verdict"] == MISSING:
            return
        if not rel.endswith(".py"):
            if rec["verdict"] is None:
                rec["verdict"] = PASS
                rec["notes"].append("estatico (C#)")
            return
        if rec["verdict"] == SYNTAX_ERROR:
            rec["notes"].append("execucao pulada: nao compila")
            return
        if not self._run_selftests:
            if rec["verdict"] is None:
                rec["verdict"] = PASS
                rec["notes"].append("estatico (--list)")
            return
        if not rec.get("has_main"):
            if rec["verdict"] is None:
                rec["verdict"] = NO_SELFTEST
                rec["notes"].append("sem bloco __main__ (convencao §6)")
            else:
                rec["notes"].append("sem __main__; contrato ja violado")
            return
        static = rec["verdict"]  # None ou CONTRACT
        self._run_selftest(rec, rel)
        if static == CONTRACT:
            rc = rec.get("rc")
            if rc == 0:
                rec["notes"].append(
                    "self-test rc=0 — contrato violado apesar de teste passando "
                    "(assinatura do stub)")
            else:
                rec["notes"].append("self-test rc=%s — contrato violado" % rc)
            rec["verdict"] = CONTRACT  # execucao nao lava contratos

    # ---------------------------------------------------------- deps
    def _scan_optional_deps(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not self._deps:
            return results
        self._emit("-- deps opcionais --")
        env = self._child_env()
        for name in self._deps:
            rec: Dict[str, Any] = {"module": name, "available": False,
                                   "version": None, "error": None}
            try:
                proc = subprocess.run(
                    [sys.executable, SELF_PATH, "--dep-probe", name],
                    capture_output=True, timeout=self._dep_timeout,
                    env=env, cwd=tempfile.gettempdir())
                out = proc.stdout.decode("utf-8", errors="replace").strip()
                for line in reversed(out.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            rec.update(json.loads(line))
                        except ValueError:
                            continue
                        break
                if proc.returncode != 0 and rec.get("error") is None:
                    rec["error"] = "probe rc=%d" % proc.returncode
            except subprocess.TimeoutExpired:
                rec["error"] = "probe timeout (%.0fs)" % self._dep_timeout
            except OSError as exc:
                rec["error"] = "probe falhou: %s" % exc
            mark = "OK" if rec.get("available") else "--"
            ver = (" v%s" % rec["version"]) if rec.get("version") else ""
            err = (" (%s)" % rec["error"][:60]) if rec.get("error") else ""
            self._emit("  %-12s %s%s%s" % (name, mark, ver, err))
            results.append(rec)
        return results

    # ---------------------------------------------------------- orquestracao
    def run(self) -> Dict[str, Any]:
        with self._lock:
            self._runs += 1
        t0 = time.monotonic()
        self._soften_stdio()
        self._emit("== AURA self-test runner v%s ==" % __version__)
        self._emit("root: %s" % self._root)
        self._emit("modo: %s | timeout: %.0fs | env filhos: %s" % (
            "estatico (--list)" if not self._run_selftests else "execucao",
            self._timeout,
            "AURA_*/GLM_* removidos" if self._strip_env else "intacto (--keep-env)"))

        if not os.path.isdir(self._root):
            self._emit("ERRO: root nao existe: %s" % self._root)
            report = {"generated_at": datetime.now(timezone.utc).isoformat(),
                      "runner_version": __version__, "root": self._root,
                      "python": sys.version.split()[0], "platform": platform.platform(),
                      "mode": "erro", "duration_s": 0.0, "counts": {},
                      "modules": [], "deps": [], "exit_code": 2}
            with self._lock:
                self._last_report = {"exit_code": 2, "counts": {}}
            return report

        modules: List[Dict[str, Any]] = []

        # 1) inventario
        inv_items = [(rel, spec) for rel, spec in self._inventory.items()
                     if self._keep(rel)]
        total = len(inv_items)
        for idx, (rel, spec) in enumerate(inv_items, 1):
            rec = self._static_check(rel, spec)
            self._maybe_execute(rec, rel)
            modules.append(rec)
            extra = ""
            if "rc" in rec:
                extra = " (rc=%s" % rec["rc"]
                if "duration_s" in rec:
                    extra += ", %.1fs" % rec["duration_s"]
                extra += ")"
            elif rec.get("notes"):
                extra = " — %s" % rec["notes"][0][:70]
            self._emit("[%2d/%d] %-9s %s%s"
                       % (idx, total, _SHORT.get(rec["verdict"], "?"), rel, extra))

        # 2) extras (fora do inventario — legado; falhas nao derrubam exit code)
        extra_listed = 0
        for rel in self._discover_extras():
            if not self._keep(rel):
                continue
            abs_path = os.path.join(self._root, rel.replace("/", os.sep))
            text = self._read_cached(abs_path)
            has_main = bool(_MAIN_RE.search(text))
            try:
                ast.parse(text)
                syntax_ok = True
            except SyntaxError:
                syntax_ok = False
            if has_main or not syntax_ok:
                rec = {"rel": rel, "desc": "fora do inventario", "in_inventory": False,
                       "notes": [], "has_main": has_main}
                if not syntax_ok:
                    rec["verdict"] = SYNTAX_ERROR
                    rec["notes"].append("sintaxe quebrada")
                if has_main and syntax_ok and self._run_selftests:
                    self._run_selftest(rec, rel)
                elif rec.get("verdict") is None:
                    rec["verdict"] = INFO
                modules.append(rec)
                extra_listed += 1
                self._emit("  extra  %-9s %s (nao afeta exit code)"
                           % (_SHORT.get(rec["verdict"], "?"), rel))
            else:
                with self._lock:
                    self._extra_skipped += 1

        # 3) deps opcionais
        deps: List[Dict[str, Any]] = []
        if self._scan_deps:
            deps = self._scan_optional_deps()

        # 4) agregacao
        counts: Dict[str, int] = {}
        for rec in modules:
            counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
        failed = [r for r in modules if r["in_inventory"] and r["verdict"] in _HARD]
        missing = [r for r in modules if r["in_inventory"] and r["verdict"] == MISSING]
        exit_code = 0
        if failed:
            exit_code = 1
        if self._fail_on_missing and missing:
            exit_code = 1

        summary = " | ".join("%s %d" % (_SHORT[v], counts[v])
                             for v in _ORDER if counts.get(v))
        self._emit("-- resumo -- %s" % (summary or "nenhum modulo"))
        if failed:
            self._emit("FALHAS (inventario):")
            for r in failed:
                self._emit("  %s — %s" % (r["rel"], "; ".join(r["notes"])[:140]))
        if missing:
            self._emit("AUSENTES (inventario): %s"
                       % ", ".join(r["rel"] for r in missing))
        self._emit("exit code: %d" % exit_code)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runner_version": __version__,
            "root": self._root,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "mode": "static" if not self._run_selftests else "full",
            "duration_s": round(time.monotonic() - t0, 2),
            "counts": counts,
            "modules": modules,
            "deps": deps,
            "exit_code": exit_code,
        }
        with self._lock:
            self._last_report = {"exit_code": exit_code, "counts": dict(counts)}
        return report

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            last = dict(self._last_report) if self._last_report else None
            return {
                "selftest_runner": {
                    "runs": self._runs,
                    "last_exit_code": (last or {}).get("exit_code"),
                    "last_counts": (last or {}).get("counts"),
                    "extras_skipped_no_main": self._extra_skipped,
                    "runner_copies_skipped": self._runner_copies_skipped,
                    "timeout_s": self._timeout,
                    "strip_env": self._strip_env,
                }
            }


# ---------------------------------------------------------------------------
# relatorio markdown
# ---------------------------------------------------------------------------
def _render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# AURA self-test report")
    lines.append("")
    lines.append("- gerado: %s" % report.get("generated_at"))
    lines.append("- root: `%s`" % report.get("root"))
    lines.append("- modo: %s | Python %s | duracao: %ss | exit: %s" % (
        report.get("mode"), report.get("python"),
        report.get("duration_s"), report.get("exit_code")))
    counts = report.get("counts") or {}
    lines.append("- resumo: %s" % ", ".join("%s=%d" % (k, v) for k, v in counts.items()))
    lines.append("")
    lines.append("| veredito | modulo | detalhe |")
    lines.append("|---|---|---|")
    for rec in report.get("modules", []):
        det: List[str] = []
        if rec.get("rc") is not None:
            det.append("rc=%s" % rec["rc"])
        if rec.get("duration_s") is not None:
            det.append("%.1fs" % rec["duration_s"])
        det.extend(rec.get("notes", []))
        if rec.get("missing_symbols"):
            det.append("faltam: %s" % ", ".join(rec["missing_symbols"]))
        det_s = "; ".join(det).replace("|", "/")[:200]
        lines.append("| %s | `%s` | %s |" % (rec.get("verdict"), rec.get("rel"), det_s))
    deps = report.get("deps") or []
    if deps:
        lines.append("")
        lines.append("## Dependencias opcionais")
        lines.append("")
        lines.append("| modulo | status | versao | erro |")
        lines.append("|---|---|---|---|")
        for d in deps:
            lines.append("| %s | %s | %s | %s |" % (
                d.get("module"), "OK" if d.get("available") else "--",
                d.get("version") or "", (d.get("error") or "")[:80]))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# self-test do proprio runner (sandbox com os cenarios do incidente)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    # --- helpers puros ---
    check("missing_symbols word-boundary",
          _missing_symbols(["Foo", "Bar"], "class Foo: pass") == ["Bar"])
    check("missing_symbols acha membro",
          _missing_symbols(["_WSDecoder"], "self._WSDecoder()") == [])

    good_src = "PAPER_TRADE = True\nEXECUTION_ALLOWED = False\nGLM_ADVISORY_ONLY = True\n"
    viol, unconf, conf = _invariant_status(ast.parse(good_src), SECURITY_INVARIANTS)
    check("invariantes ok confirmados", viol == [] and len(conf) == 3)
    bad_src = "PAPER_TRADE = True\nEXECUTION_ALLOWED = True\n"
    viol2, _u2, _c2 = _invariant_status(ast.parse(bad_src), SECURITY_INVARIANTS)
    check("violacao detectada", len(viol2) == 1 and "EXECUTION_ALLOWED" in viol2[0])
    commented = "# EXECUTION_ALLOWED = True (comentario historico)\n"
    viol3, unconf3, _c3 = _invariant_status(ast.parse(commented), SECURITY_INVARIANTS)
    check("comentario nao gera falso-positivo", viol3 == [] and len(unconf3) == 3)

    # --- dep probe filho (stdlib, sem risco de wheel quebrada) ---
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _dep_probe_child("json")
    payload = json.loads(buf.getvalue().strip().splitlines()[-1])
    check("dep probe stdlib", rc == 0 and payload["available"] is True)

    # --- sandbox: arvore falsa com todos os cenarios ---
    with tempfile.TemporaryDirectory(prefix="aura_runner_st_") as sandbox:

        def w(rel: str, content: str) -> None:
            path = os.path.join(sandbox, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)

        w("engine/core/security.py",
          "PAPER_TRADE = True\nEXECUTION_ALLOWED = False\nGLM_ADVISORY_ONLY = True\n\n"
          "if __name__ == \"__main__\":\n    print(\"[PASS] security ok\")\n")
        w("engine/core/good.py",
          "class FooClass:\n    pass\n\n"
          "if __name__ == \"__main__\":\n    print(\"[PASS] good\")\n")
        w("engine/core/broken.py", "def broken(:\n    pass\n")
        w("engine/core/stub_browser.py",
          "class StubQualquer:\n    pass\n\n"
          "if __name__ == \"__main__\":\n    print(\"[PASS] stub ok\")\n")
        w("engine/core/liar.py",
          "if __name__ == \"__main__\":\n"
          "    print(\"[FAIL] imprimiu FAIL mas exit 0\")\n")
        w("engine/core/slow.py",
          "import time\n\nif __name__ == \"__main__\":\n    time.sleep(30)\n")
        w("engine/core/nomain.py", "X = 1\n")
        w("engine/agents/sec_bad.py",
          "PAPER_TRADE = True\nEXECUTION_ALLOWED = True\nGLM_ADVISORY_ONLY = True\n\n"
          "if __name__ == \"__main__\":\n    print(\"[PASS] sec_bad ok\")\n")
        w("legacy_tts.py",
          "if __name__ == \"__main__\":\n    print(\"[PASS] legacy tts\")\n")
        w("legacy_broken.py",
          "if __name__ == \"__main__\":\n    print(\"[FAIL] legacy broken\")\n")
        w("tools/run_selftests.py",
          "# AURA_SELFTEST_RUNNER_DO_NOT_EXECUTE\n"
          "if __name__ == \"__main__\":\n    print(\"EXECUTED-LOOP\")\n")

        inv = {
            "engine/core/security.py": {"symbols": ["PAPER_TRADE"], "invariants": True},
            "engine/core/good.py": {"symbols": ["FooClass"]},
            "engine/core/broken.py": {"symbols": ["broken"]},
            "engine/core/stub_browser.py": {"symbols": ["HeuristicWalker", "FixtureState"]},
            "engine/core/liar.py": {"symbols": []},
            "engine/core/slow.py": {"symbols": []},
            "engine/core/nomain.py": {"symbols": ["X"]},
            "engine/core/ausente.py": {"symbols": ["Y"]},
            "engine/agents/sec_bad.py": {"symbols": [], "invariants": True},
        }

        runner = SelfTestRunner(root=sandbox, inventory=inv, timeout=1.0,
                                dep_timeout=5.0, run_selftests=True,
                                scan_deps=False, deps=[], quiet=True,
                                strip_env=True, fail_on_missing=False)
        report = runner.run()
        by = {r["rel"]: r for r in report["modules"]}

        check("modulo bom passa", by["engine/core/good.py"]["verdict"] == PASS)
        check("erro de sintaxe detectado",
              by["engine/core/broken.py"]["verdict"] == SYNTAX_ERROR)
        stub = by["engine/core/stub_browser.py"]
        check("stub com self-test passando = CONTRACT_VIOLATION",
              stub["verdict"] == CONTRACT and stub.get("rc") == 0)
        check("assinatura do stub nomeada",
              "assinatura do stub" in " ".join(stub["notes"]))
        check("modulo que mente (exit 0 + [FAIL])",
              by["engine/core/liar.py"]["verdict"] == FAIL)
        check("timeout com tree-kill",
              by["engine/core/slow.py"]["verdict"] == TIMEOUT)
        check("sem __main__ = NO_SELFTEST",
              by["engine/core/nomain.py"]["verdict"] == NO_SELFTEST)
        check("ausente = MISSING",
              by["engine/core/ausente.py"]["verdict"] == MISSING)
        bad = by["engine/agents/sec_bad.py"]
        check("invariante §0 violado = CONTRACT_VIOLATION",
              bad["verdict"] == CONTRACT
              and "INVARIANTE" in " ".join(bad["notes"]))
        check("security bom passa (invariantes ok)",
              by["engine/core/security.py"]["verdict"] == PASS)
        all_tails = " ".join(r.get("tail", "") for r in report["modules"])
        check("copia do runner nunca executada", "EXECUTED-LOOP" not in all_tails)
        check("exit code 1 com falhas no inventario", report["exit_code"] == 1)
        check("extra visivel no relatorio",
              any(r["rel"] == "legacy_tts.py" for r in report["modules"]))

        # extra que falha NAO derruba exit code quando fora do inventario
        runner2 = SelfTestRunner(root=sandbox, inventory={}, timeout=1.0,
                                 run_selftests=True, scan_deps=False, deps=[],
                                 quiet=True, strip_env=True)
        report2 = runner2.run()
        lb = [r for r in report2["modules"] if r["rel"] == "legacy_broken.py"]
        check("extra com FAIL reportado", lb and lb[0]["verdict"] == FAIL)
        check("extra com FAIL nao derruba exit code", report2["exit_code"] == 0)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s" % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - run_selftests.py")
    return 0


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_selftests.py",
        description="Runner de self-tests + manifest + contratos do AURA QUANT-X V25")
    parser.add_argument("--root", default=None, help="raiz do projeto (default: auto)")
    parser.add_argument("--list", action="store_true",
                        help="apenas analise estatica (nao executa self-tests)")
    parser.add_argument("--only", nargs="*", default=[], metavar="PAT",
                        help="apenas modulos cujo path contem PAT (substring)")
    parser.add_argument("--skip", nargs="*", default=[], metavar="PAT",
                        help="pula modulos cujo path contem PAT")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="timeout por self-test em segundos (default 180)")
    parser.add_argument("--dep-timeout", type=float, default=60.0)
    parser.add_argument("--json", default=None, help="grava relatorio JSON no caminho")
    parser.add_argument("--md", default=None, help="grava relatorio Markdown no caminho")
    parser.add_argument("--fail-on-missing", action="store_true",
                        help="exit 1 se houver modulo do inventario ausente")
    parser.add_argument("--keep-env", action="store_true",
                        help="nao filtra AURA_*/GLM_* do env dos filhos")
    parser.add_argument("--no-deps", action="store_true",
                        help="pula o probe de dependencias opcionais")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--self-test", action="store_true",
                        help="valida o proprio runner (sandbox deterministico)")
    parser.add_argument("--dep-probe", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.dep_probe is not None:
        return _dep_probe_child(args.dep_probe)
    if args.self_test:
        return _self_test()

    root = os.path.abspath(args.root) if args.root else _default_root()
    runner = SelfTestRunner(
        root=root, timeout=args.timeout, dep_timeout=args.dep_timeout,
        only=args.only, skip=args.skip, run_selftests=not args.list,
        scan_deps=not args.no_deps, strip_env=not args.keep_env,
        quiet=args.quiet, fail_on_missing=args.fail_on_missing)
    report = runner.run()
    if args.json:
        _atomic_write(args.json, json.dumps(report, indent=2, ensure_ascii=True))
        print("relatorio JSON: %s" % args.json)
    if args.md:
        _atomic_write(args.md, _render_markdown(report))
        print("relatorio MD: %s" % args.md)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
