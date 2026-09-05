#!/usr/bin/env python3
from __future__ import annotations
import os
import re
from pathlib import Path

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
SAFE = re.compile(r'(?<!String\()([A-Za-z0-9_\)\]]+)\.toUpperCase\(\)')
HOOK = '''
  window.addEventListener("error", function (ev) {
    try {
      fetch("http://127.0.0.1:8765/api/telemetry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "matriz", type: "js_error",
          message: String((ev && ev.message) || ""),
          paper_trade: true, execution_allowed: false
        })
      });
    } catch (err) {}
  });
'''


def main() -> int:
    for p in ROOT.glob("desktop/**/index-aCoLBegj.js"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "AURA_TOUPPER_GUARD" in text:
            print("JA_PATCH", p)
            continue
        new, n = SAFE.subn(lambda m: f'String({m.group(1)}??"").toUpperCase()', text)
        p.write_text("/* AURA_TOUPPER_GUARD */\n" + new, encoding="utf-8")
        print("JS_OK", p, n)
    needle = 'console.info("[AURA boot] fetch override ativo -> 127.0.0.1");'
    for p in ROOT.glob("desktop/**/aura-desktop-boot.js"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "js_error" in text:
            print("JA_BOOT", p)
            continue
        if needle in text:
            p.write_text(text.replace(needle, needle + "\n" + HOOK), encoding="utf-8")
            print("BOOT_OK", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
