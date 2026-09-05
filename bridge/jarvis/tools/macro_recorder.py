# bridge/jarvis/tools/macro_recorder.py
"""
Gravador de latências reais para macros WhatsApp/Telegram Desktop.

Como usar (Windows, com WhatsApp Desktop aberto):
  1) python -m bridge.jarvis.tools.macro_recorder
  2) Siga as instruções no terminal (Enter em cada passo)
  3) O script grava tempos REAIS da sua máquina em
     bridge/jarvis/tools/macros_latencies.json

O whatsapp_operator / telegram_operator leem esse ficheiro
e substituem os sleeps padrão.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent / "macros_latencies.json"

STEPS_WHATSAPP = [
    ("after_focus", "Foque o WhatsApp Desktop (clique na janela) e pressione Enter aqui"),
    ("after_ctrl_f", "Pressione Ctrl+F no WhatsApp; quando a caixa de busca aparecer, Enter aqui"),
    ("after_type_contact", "Digite um nome de contato e AGUARDE a lista filtrar; Enter quando filtrar"),
    ("after_enter_contact", "Pressione Enter para abrir a conversa; Enter aqui quando a conversa abrir"),
    ("after_paste_text", "Cole um texto (Ctrl+V) no campo de mensagem; Enter quando o texto aparecer"),
    ("after_paste_file", "Cole um arquivo (Ctrl+V); Enter quando o preview do anexo carregar"),
    ("after_send", "Pressione Enter para enviar; Enter aqui quando a mensagem/arquivo for enviado"),
]


def _measure(label: str, prompt: str) -> float:
    input(f"\n[{label}] {prompt}\n  → ")
    t0 = time.perf_counter()
    input("  Agora faça a ação e pressione Enter AQUI assim que a UI reagir...\n  → ")
    dt = time.perf_counter() - t0
    print(f"  ✓ {label} = {dt:.3f}s")
    return round(dt, 3)


def main() -> int:
    print("=" * 60)
    print("AURA Macro Latency Recorder")
    print("Mede os sleeps REAIS da sua máquina para WhatsApp/Telegram.")
    print("Os valores vão para:", OUT)
    print("=" * 60)

    app = input("App a calibrar [whatsapp/telegram] (default=whatsapp): ").strip().lower() or "whatsapp"
    if app not in ("whatsapp", "telegram"):
        print("App inválido.")
        return 1

    print("\nAbra o", app.title(), "Desktop e deixe-o visível.")
    input("Pronto? Enter para começar...")

    measured = {}
    for key, prompt in STEPS_WHATSAPP:
        measured[key] = _measure(key, prompt.replace("WhatsApp", app.title()))

    # type_interval é preferência de digitação, não latência de UI
    measured["type_interval"] = 0.06

    data = {}
    if OUT.is_file():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data[app] = measured
    data["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["notes"] = "Gerado por macro_recorder.py — substitua se a máquina mudar."

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n✅ Gravado em", OUT)
    print(json.dumps(measured, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
