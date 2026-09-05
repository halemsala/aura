

## v12.5.3 — Hardening pós-diagnóstico
- Normalização de versão entre background/content/page-hook/popup/diagnostics/dashboard.
- Storage health agora usa percentual da cota, evitando falso CRITICAL em ~4.5 MB.
- CRITICAL de storage somente em >=90%; WARNING em >=75%; alerta crítico é limpo após recuperação.
- Telemetria inclui `storageQuotaBytes` e `storageRatio`.
