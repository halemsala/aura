#!/usr/bin/env python3
"""Reescreve o manual mestre operacional do AURA em texto puro.

Uso no Windows:
    engine\\venv\\Scripts\\python.exe desktop\\update_manual.py --root .

O script é deliberadamente determinístico quanto ao conteúdo técnico e registra
somente a data da atualização. Ele não executa serviços, não acessa credenciais,
não altera paper trade e não faz chamadas externas.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

BUILD = "AURA-WINDOWS-DESKTOP-PREP-1"
VOICE_BUILD = "AURA-VOICE-MALE-V3"
MANUAL_NAME = "MANUAL_SISTEMA_AURA.txt"
CHANGELOG_NAME = "desktop/REGISTRO_ATUALIZACOES.md"


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return default


def version(root: Path) -> str:
    value = read_text(root / "VERSION.txt", "12.7.0-V22-INTEGRATED").strip()
    return value or "12.7.0-V22-INTEGRATED"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(path, "{}"))
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def count_agents(root: Path) -> tuple[int, int, int]:
    manifest = load_json(root / "agents" / "activation_manifest.json")
    declared = int(manifest.get("agent_count") or 0)
    allowlisted = 0
    handlers = 0
    for path in (root / "agents", root / "engine", root / "bridge"):
        if not path.exists():
            continue
        for file in path.rglob("*.py"):
            text = read_text(file)
            allowlisted += len(re.findall(r"allowlist|allowlisted|AUTONOMOUS_TOOLS", text, re.I))
            handlers += len(re.findall(r"def execute\s*\(|@.*(?:get|post).*agent", text, re.I))
    return declared, allowlisted, handlers


def file_state(root: Path, relative: str) -> str:
    return "PRESENTE" if (root / relative).exists() else "AUSENTE"


def service_rows(root: Path) -> list[tuple[str, str, str, str]]:
    return [
        ("Bridge", "127.0.0.1:8080", "GET /health; POST /api/cornerai/feed", file_state(root, "bridge/server.py")),
        ("Engine", "127.0.0.1:8765", "GET /api/health; GET /api/readiness; GET /api/status; POST /api/telemetry", file_state(root, "engine/server.py")),
        ("Voice/Jarvis", "127.0.0.1:8099", "GET /api/voice/health; POST /api/voice/talk; POST /api/voice/tts", file_state(root, "bridge/jarvis_voice_server.py")),
        ("Ollama", "127.0.0.1:11434", "GET /api/tags; modelo glm4:9b-chat-q4_0", "EXTERNO LOCAL"),
        ("SokkerPRO", "HTTPS", "captura dentro do WebView2; autenticação do usuário", "PENDENTE WINDOWS"),
    ]


def render_manual(root: Path) -> str:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    ver = version(root)
    declared, allowlisted, handlers = count_agents(root)
    rows = service_rows(root)
    activation = load_json(root / "agents" / "activation_manifest.json")
    raw_tools = activation.get("tools", [])
    if isinstance(raw_tools, dict):
        tool_count = len(raw_tools)
    elif isinstance(raw_tools, list):
        tool_count = len([item for item in raw_tools if isinstance(item, dict)])
    else:
        tool_count = 0
    desktop_files = [
        "AURA_REPARAR_SISTEMA.bat",
        "AURA_InPlace.ps1",
        "allowlist.json",
        "scripts/aura_install_activation_check.py",
        "scripts/test_in_place_update.py",
        "desktop/update_manual.py",
        "desktop/config/desktop.json",
        "desktop/Aura.Desktop.csproj",
        "desktop/Program.cs",
        "desktop/MainForm.cs",
        "desktop/BrowserHost.cs",
        "desktop/ServiceSupervisor.cs",
        "desktop/app.manifest",
        "desktop/capture/aura-capture.js",
        "desktop/ui/matriz_v22/index.html",
        "desktop/ui/matriz_v22/manifest.webmanifest",
        "desktop/ui/matriz_v22/sw.js",
        "engine/knowledge_review_gate.py",
        "scripts/aura_knowledge_review.py",
        "knowledge/README.md",
        "desktop/README.md",
        "desktop/ARCHITECTURE.md",
        "desktop/AUDITORIA_MIGRACAO_DESKTOP.md",
        "desktop/AUDITORIA_CORRECAO_VOZ.md",
        "desktop/AUDITORIA_DISTRIBUICAO_COMPLETA.md",
        "desktop/packaging/EXE_PREPARATION.md",
        "desktop/packaging/installer-manifest.json",
        "desktop/MANUAL_UPDATE_POLICY.txt",
        "desktop/aura_self_test.py",
        "PACKAGE_RELEASE.txt",
        "desktop/tests/test_desktop_contract.py",
    ]
    lines: list[str] = []
    add = lines.append
    add("AURA QUANT-X — MANUAL MESTRE OPERACIONAL")
    add("=" * 68)
    add(f"Versão registrada: {ver}")
    add(f"Build de preparação: {BUILD}")
    add(f"Build efetivo obrigatório do Voice: {VOICE_BUILD}")
    add(f"Manual reescrito em: {now}")
    add("Status: preparação para aplicativo Windows local; o EXE depende do publish validado no Windows")
    add("")
    add("1. REGRA DE ATUALIZAÇÃO PERMANENTE")
    add("- Este arquivo é o bloco de notas mestre do sistema.")
    add("- Toda atualização deve executar desktop\\update_manual.py após alterar código, conexões, funções, portas, agentes ou ferramentas.")
    add("- O script reescreve este TXT e registra a atualização em desktop\\REGISTRO_ATUALIZACOES.md.")
    add("- O manual não é prova de que um recurso foi testado no Windows; ele separa PRESENTE, PENDENTE WINDOWS e EXTERNO LOCAL.")
    add("")
    add("2. OBJETIVO DA MIGRAÇÃO")
    add("- Retirar a dependência operacional da extensão Chrome.")
    add("- Executar o AURA como aplicativo Windows local com navegador embutido baseado em Chromium.")
    add("- Usar WebView2 como primeira opção de preparação; CEF permanece alternativa para uma distribuição Chromium totalmente independente.")
    add("- A referência à experiência Opera significa compatibilidade/estilo Chromium, não redistribuição de binários, marca ou serviços proprietários da Opera.")
    add("- O pacote-fonte exige publish validado no Windows; ele não contém Setup.exe nem deve ser anunciado como instalador final.")
    add("")
    add("3. POLÍTICA OPERACIONAL E SEGURANÇA")
    add("- PAPER TRADE ONLY: nenhuma rota de ordem real, stake real ou envio financeiro pode ser habilitada por esta migração.")
    add("- Ações restritas continuam sujeitas ao Gatekeeper e a clearance administrativa.")
    add("- O shell local deve usar perfil de navegador isolado e não gravar tokens no código.")
    add("- Dados de captura devem ser identificados por fixture e freshness; payload inválido permanece fail-closed.")
    add("")
    add("4. SERVIÇOS, PORTAS, ROTAS E DEPENDÊNCIAS")
    add("Serviço | Endereço | Contrato principal | Estado do arquivo")
    add("-" * 68)
    for name, address, routes, state in rows:
        add(f"{name} | {address} | {routes} | {state}")
    add("")
    add("Dependências locais esperadas:")
    add("- Windows 10/11, Python 3.14.6 compatível com o pacote do usuário e engine\\venv.")
    add("- NVIDIA RTX 4050 6 GB opcional para IA; Whisper permanece base/CPU/int8 para preservar VRAM do GLM-4.")
    add("- Ollama instalado e modelo glm4:9b-chat-q4_0 disponível; llama3.2:3b pode ser fallback.")
    add("- Edge TTS pt-BR-AntonioNeural como padrão; XTTS por WAV de referência é opcional e depende da instalação Coqui.")
    add(f"- O diagnóstico do Voice deve informar build_id={VOICE_BUILD}; ausência desse campo indica processo antigo na porta 8099.")
    add("- Política masculina estrita: somente Antonio, Humberto, Nicolau ou Donato; fallback feminino, browser speechSynthesis e gTTS estão desativados.")
    add("- WebView2 Runtime para o aplicativo Windows embutido; presença deve ser verificada antes de abrir a janela.")
    add("")
    add("5. AGENTES E MENUS")
    add(f"- Agentes declarados no manifesto: {declared or 'não informado'}.")
    add(f"- Ocorrências de allowlist/contratos detectadas no código: {allowlisted}.")
    add(f"- Handlers/rotinas de execução detectados estaticamente: {handlers}.")
    add(f"- Ferramentas declaradas no manifesto de ativação: {tool_count or 'não informado'}.")
    add("- O Agent Hub desktop possui catálogo local e menus individuais derivados do manifesto e do relatório estático; a extensão permanece legada/transição.")
    add("- Cada agente deve publicar: nome, camada, descrição, estado, funções, payload padrão seguro, modo de inspeção/execução e resultado.")
    add("- Agentes somente-inspeção não devem receber botão de execução enganoso.")
    add("")
    add("6. CAPTURA DO SOKKERPRO SEM EXTENSÃO")
    add("- O WebView2 navega para o SokkerPRO dentro do aplicativo.")
    add("- O host injeta desktop\\capture\\aura-capture.js apenas em origens permitidas e recebe a mensagem AURA_SOKKERPRO_CAPTURE por postMessage/WebMessage.")
    add("- O adaptador deve extrair fixture, times, relógio, placar, escanteios, pressão, eventos, odds e freshness sem inventar valores ausentes.")
    add("- O host encaminha o payload normalizado para POST http://127.0.0.1:8080/api/cornerai/feed.")
    add("- O Bridge normaliza e persiste o feed; o Engine continua responsável por análise, risco, explicação e bloqueios.")
    add("- Autenticação, DOM real do SokkerPRO e compatibilidade com mudanças de layout são testes pendentes no Windows.")
    add("")
    add("7. FERRAMENTAS E CONEXÕES")
    add("- Browser embutido: WebView2/Chromium, perfil isolado, abas, endereço, voltar/avançar, reload, console de status e mensagens host↔página.")
    add("- Backend: Bridge, Engine e Voice locais, iniciados em sequência pelo fluxo de instalação existente.")
    add("- Autoteste: fase pre bloqueia pacote/pastas/portas inválidos; fase post verifica venv/imports; fase final valida health e build do Voice.")
    add("- LLM: Ollama local com GLM-4 9B quantizado; fallback explícito, sem download silencioso fora do contrato.")
    add("- STT: faster-whisper base/cpu/int8.")
    add("- TTS: Edge TTS AntonioNeural; rate/pitch do YAML são normalizados para -4%/-8Hz; fallback gTTS/browser/feminino é rejeitado.")
    add(f"- Diagnóstico Voice: /api/voice/diagnostic informa build_id={VOICE_BUILD}, configured_voice, tts_runtime, engine, gender e fallback; o cliente rejeita metadata não masculina.")
    add("- A WAV masculina é referência documental; ela não é um modelo de clonagem. XTTS só usa a WAV quando Coqui/TTS estiver instalado e explicitamente habilitado.")
    add("- Telegram e integrações externas: opcionais, dependem de tokens/credenciais fornecidos pelo usuário e não devem ser embutidos.")
    add("- Chrome Extension: compatibilidade legada apenas; não é requisito do novo shell local.")
    add("")
    add("8. ARQUIVOS DA PREPARAÇÃO DESKTOP")
    for rel in desktop_files:
        add(f"- {rel} — {file_state(root, rel)}")
    add("")
    add("9. FLUXO DE INICIALIZAÇÃO PREPARADO")
    add("1) O BAT executa o autoteste pre; se houver arquivo ausente, porta ocupada, Ollama indisponível ou pacote incompleto, a instalação é bloqueada.")
    add("2) Somente após o pre-teste aprovado, AURA_INSTALAR_E_INICIAR_TUDO.bat solicita elevação e instala/repara o backend.")
    add("3) O autoteste post verifica engine\\venv, imports críticos, AST Python e política masculina.")
    add("4) O manual mestre é reescrito automaticamente pelo gerador, quando presente.")
    add("5) Ollama e GLM-4 são verificados.")
    add("6) Bridge, Engine e Voice são iniciados e validados nas portas 8080, 8765 e 8099.")
    add("7) O autoteste final valida os health checks, o build do Voice e a voz masculina efetiva antes de declarar sucesso.")
    add("8) O futuro AURA Desktop inicia o shell WebView2 e exibe o dashboard local.")
    add("9) O WebView2 abre SokkerPRO e encaminha capturas ao Bridge, sem extensão Chrome.")
    add("")
    add("10. CHECKLIST PARA O FUTURO EXE")
    add("- [ ] Escolher distribuição Evergreen ou Fixed Version do WebView2 Runtime.")
    add("- [ ] Definir assinatura de código e identidade do aplicativo.")
    add("- [ ] Empacotar runtime Python ou definir pré-requisito formal.")
    add("- [ ] Definir diretório de dados gravável fora da pasta de instalação.")
    add("- [ ] Implementar upgrade/rollback e migração do banco.")
    add("- [ ] Testar firewall, permissões, portas ocupadas e múltiplas instâncias.")
    add("- [ ] Testar login, captura e mudanças do SokkerPRO no WebView2.")
    add("- [ ] Testar RTX 4050 6 GB, Ollama, GLM-4, Voice, microfone e TTS no Windows.")
    add("- [ ] Somente após esses testes gerar o instalador EXE.")
    add("")
    add("11. LIMITAÇÕES E EVIDÊNCIA")
    add("- A estrutura e os contratos podem ser validados no sandbox Linux.")
    add("- A execução real do WebView2, GPU NVIDIA, Ollama, microfone, autenticação SokkerPRO e serviços Windows exige teste no computador do usuário.")
    add("- Nenhuma conclusão de 'operante' deve ser registrada sem log ou health check correspondente.")
    add("")
    add("12. TROCA OBRIGATÓRIA QUANDO HOUVER PROCESSO VOICE ANTIGO")
    add("- Se /api/voice/diagnostic não retornar build_id=" + VOICE_BUILD + ", o processo na porta 8099 é antigo e não deve ser aceito como saudável.")
    add("- Identifique o PID com: Get-NetTCPConnection -LocalPort 8099 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess")
    add("- Encerre somente o PID confirmado: Stop-Process -Id SEU_PID -Force")
    add("- Extraia o pacote em uma pasta nova; não sobrescreva C:\\Users\\salaa\\AppData\\Local\\Programs\\AURA Quant-X\\AURA_QUANT_X\\.")
    add("- Execute AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat na pasta-fonte e confirme o novo build no diagnóstico.")
    add("")
    add("13. PRIMEIRO ARRANQUE COM GLM, MATRIZ V22 E CATÁLOGO COMPLETO")
    add("- A homepage oficial do desktop é https://aura.local/index.html; o build físico Operator OS permanece em desktop\\\\ui\\\\matriz_v22.")
    add("- desktop\\config\\desktop.json declara glmEnabledByDefault=true e matrixUi=v22.")
    add("- O shell consulta o estado do Ollama, mas não o inicia automaticamente; a interface pode abrir em paper trade sem o modelo GLM.")
    add("- O chat V22 consulta /api/glm_chat e permanece GLM_ADVISORY_ONLY, PLAN_ONLY, PAPER TRADE ONLY e execution_allowed=false.")
    add(f"- O catálogo declara {declared or 'não informado'} agentes e {tool_count or 'não informado'} ferramentas; a V22 consulta /api/agents no Engine canónico.")
    add("- A V22 consulta /api/ui/state e mostra sinais de corner_intelligence apenas quando há captura canónica; sem captura, o fallback é demonstrativo.")
    add("")
    add("14. REVISÃO OBRIGATÓRIA DO CONHECIMENTO DO AGENTE")
    add("- O corpus em knowledge\\inbox é candidato e não entra automaticamente na memória semântica.")
    add("- A release inicia com 566 candidatos PENDING_HUMAN_REVIEW, zero aprovados e zero decisões.")
    add("- Use scripts\\aura_knowledge_review.py para status, pending, approve ou reject; claims sem validação permanecem fora do agente.")
    add("- Apenas knowledge\\approved\\knowledge.jsonl pode alimentar o contexto; a memória aprovada e o ledger de decisões são protegidos pelo updater.")
    add("- Valores de odds, EV, Poisson, Hawkes, pressão e escanteios são dados/hipóteses até validação; não são stake, ordem ou garantia.")
    add("")
    add("15. ATUALIZAÇÃO IN-PLACE SEM NOVO EXE")
    add("- Depois da primeira instalação, use AURA_REPARAR_SISTEMA.bat /PLAN ou /HEALTH para diagnóstico e AURA_REPARAR_SISTEMA.bat /APPLY com manifesto aura-inplace-patch-v1 para aplicar código aprovado.")
    add("- O AURA_InPlace.ps1 exige allowlist, SHA-256, path relativo, backup seletivo, sintaxe, guards e health checks; falhas restauram apenas os ficheiros alterados.")
    add("- O reparador não recria engine\\venv, não reinstala PyTorch/CUDA, não faz ollama pull e não altera bancos, configurações locais, modelos, voz, logs, memória aprovada ou decisões.")
    add("- /ROLLBACK update_YYYYMMDD_HHMMSS restaura apenas o backup indicado; /REPAIR_DEPENDENCIES diagnostica e não instala automaticamente.")
    add("")
    add("16. EVIDÊNCIA DESTA ALTERAÇÃO")
    add("- Estrutura, contratos, sintaxe, build V22, allowlist, activation check, gate de conhecimento, testes in-place e guards: VALIDADO_ESTATICAMENTE no staging Linux.")
    add("- EXE WinForms publicado, WebView2, Ollama real, carga GLM, GPU, voz, microfone, login SokkerPRO e rollback Windows: PENDENTE WINDOWS.")
    add("")
    add("FIM DO MANUAL MESTRE")
    return "\n".join(lines) + "\n"


def update(root: Path) -> tuple[Path, Path]:
    manual_path = root / MANUAL_NAME
    manual_path.write_text(render_manual(root), encoding="utf-8")
    changelog_path = root / CHANGELOG_NAME
    changelog_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    entry = (
        f"\n## {now} — {BUILD}\n\n"
        f"Manual mestre reescrito em `{MANUAL_NAME}` após preparação da migração Windows Desktop. "
        "Foram atualizados o inventário de funções, conexões, ferramentas, serviços, agentes, captura e checklist do futuro EXE.\n"
    )
    previous = read_text(changelog_path)
    if entry not in previous:
        changelog_path.write_text(previous.rstrip() + entry + "\n", encoding="utf-8")
    return manual_path, changelog_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    root_value = args.root or os.getenv("AURA_MANUAL_ROOT") or Path(__file__).resolve().parents[1]
    root_value = str(root_value).strip().strip('"').strip("'")
    root = Path(root_value).resolve()
    if args.validate_only:
        print(render_manual(root), end="")
        return 0
    manual, changelog = update(root)
    print(f"MANUAL_UPDATED={manual}")
    print(f"CHANGELOG_UPDATED={changelog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
