from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
manifest_path = root / "agents" / "activation_manifest.json"
out_path = root / "desktop" / "ui" / "agents.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
report_path = root / "ARQUIVO_LEGADO" / "documentacao" / "raiz" / "AURA_agents_static_report.json"
report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
report_by_id = {item.get("id"): item for item in (report.get("agents") or []) if isinstance(item, dict)}
items = []
for key, value in (manifest.get("agents") or {}).items():
    if not isinstance(value, dict):
        continue
    detail = report_by_id.get(key, {})
    items.append({
        "id": key,
        "name": detail.get("name") or key.split(":", 1)[-1].replace("_", " ").replace(".py", "").strip(),
        "layer": value.get("layer", detail.get("layer", "unknown")),
        "status": value.get("status", detail.get("status", "unknown")),
        "path": value.get("path", detail.get("file", "")),
        "implementationState": detail.get("implementation_state", "unknown"),
        "inspectionOnly": detail.get("implementation_state") == "inspect_only",
        "functions": detail.get("runnable_functions", []),
        "allFunctions": detail.get("functions", []),
        "actions": detail.get("actions", ["status", "inspect"]),
        "paperTradeOnly": True,
    })
result = {
    "version": manifest.get("version", "unknown"),
    "agentCount": manifest.get("agent_count", len(items)),
    "toolCount": manifest.get("tool_count", 0),
    "installer": "AURA_INSTALAR_E_INICIAR_TUDO.bat",
    "paperTradeOnly": True,
    "agents": items,
}
out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"AGENT_CATALOG_WRITTEN={out_path}")
print(f"AGENT_CATALOG_COUNT={len(items)}")
