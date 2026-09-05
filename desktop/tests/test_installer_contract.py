from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_package_marker_exists() -> None:
    marker = (ROOT / "PACKAGE_RELEASE.txt").read_text(encoding="utf-8").strip()
    assert marker == "AURA-QUANT-X-12.7.0-WINDOWS-PROGRAM-HANDOFF-GLM-VOICE-AGENTS-V19-HARDWARE-TWEAKS-SAFE"


def test_master_bat_has_blocking_pre_and_post_final_phases() -> None:
    source = (ROOT / "AURA_INSTALAR_E_INICIAR_TUDO.bat").read_text(encoding="utf-8")
    assert "--phase=pre" not in source
    assert "--phase=post" not in source
    assert "--phase=final" not in source
    assert "--root=\"%ROOT%\"" not in source
    assert "set \"AURA_SELF_TEST_PHASE=pre\"" in source
    assert "set \"AURA_SELF_TEST_PHASE=post\"" in source
    assert "set \"AURA_SELF_TEST_PHASE=final\"" in source
    assert "Pre-teste bloqueante falhou" in source
    assert "Teste pos-instalacao falhou" in source
    assert "Autoteste final falhou" in source
    assert "Codigo de saida: 0" not in source


def test_self_test_is_python_and_has_all_phases() -> None:
    path = ROOT / "desktop/aura_self_test.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    for phase in ("pre", "post", "final"):
        assert f'"{phase}"' in source
    assert "EXPECTED_VOICE_BUILD" in source
    assert "PAPER TRADE" in source
    assert "AURA_SELF_TEST_PHASE" in source
    assert "AURA_SELF_TEST_ROOT" in source
