from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MALE = {"pt-BR-HumbertoNeural", "pt-BR-NicolauNeural", "pt-BR-DonatoNeural"}


def test_yaml_voice_is_approved_male() -> None:
    config = (ROOT / "bridge/jarvis/config.yaml").read_text(encoding="utf-8")
    assert 'provider: "edge"' in config
    assert "HumbertoNeural" in config
    assert "AntonioNeural" not in config
    assert 'xtts_enabled: false' in config
    alternate = (ROOT / "bridge/jarvis/config_voice_masculina.yaml").read_text(encoding="utf-8")
    assert "Francisca" not in alternate


def test_edge_tts_parameters_are_normalized() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from bridge.jarvis_voice_server import _edge_pitch, _edge_rate

    assert _edge_rate(0.92) == "-8%"
    assert _edge_pitch(0.96) == "-4Hz"
    assert _edge_rate("-8%") == "-8%"
    assert _edge_pitch("-4Hz") == "-4Hz"


def test_neural_tts_has_no_silent_non_male_fallback() -> None:
    source = (ROOT / "bridge/jarvis/modules/neural_tts.py").read_text(encoding="utf-8")
    assert "_APPROVED_MALE_VOICES" in source
    assert "VOICE_SELECTION_ERROR" in source
    synth = source[source.index("def synthesize_mp3"):source.index("def cache_stats")]
    assert "_fetch_gtts_chunk" not in synth
    assert "edge_tts_male_unavailable" in synth
    assert "Francisca" not in source


def test_voice_server_reports_effective_tts() -> None:
    source = (ROOT / "bridge/jarvis_voice_server.py").read_text(encoding="utf-8")
    assert 'VOICE_BUILD_ID = os.environ.get("AURA_VOICE_BUILD_ID", "AURA-VOICE-MALE-V3")' in source
    assert '"build_id": VOICE_BUILD_ID' in source
    assert "configured_voice" in source
    assert "tts_runtime" in source
    assert '"gender": runtime.get("gender")' in source
    assert '"fallback": "disabled"' in source
    assert "tts_male_not_ready" in source
    assert "VOICE_PREFLIGHT_FAIL: voz não aprovada" in (ROOT / "bridge/voice_preflight.py").read_text(encoding="utf-8")


def test_clients_reject_wrong_voice_metadata() -> None:
    for relative in ("extensao/visao/voice-assistant.js", "extensao/visao/sidepanel.js", "extensao/src/aura-quantx-adapter.js"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "tts_gender_not_male" in source, relative
        assert "tts_fallback_rejected" in source, relative
    voice_client = (ROOT / "extensao/visao/voice-assistant.js").read_text(encoding="utf-8")
    assert "pt-BR-HumbertoNeural" in voice_client or "Humberto" in voice_client or "hercules" in voice_client.lower()
    assert "speechSynthesis" in voice_client  # apenas catálogo/seleção visual; não é fallback de reprodução


def test_voice_python_files_parse() -> None:
    for relative in ("bridge/jarvis/modules/neural_tts.py", "bridge/jarvis_voice_server.py", "bridge/voice_preflight.py"):
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
