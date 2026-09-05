# AURA Grid v6.0 Zero-Trust oriented

## Certificate pinning
```powershell
# After generating cert.pem:
python scripts\print_cert_pin.py cert.pem
# Worker:
$env:AURA_GRID_TLS = "true"
$env:AURA_GRID_CERT_PIN = "<hash>"
$env:AURA_GRID_REQUIRE_CERT_PIN = "true"  # optional hard fail if pin unset
```

## Audit
- Master: `audit_master.jsonl` (`AURA_GRID_MASTER_AUDIT`)
- Worker: `audit_worker.jsonl` (`AURA_GRID_WORKER_AUDIT`)

## Verification
`$env:AURA_GRID_VERIFY_RATE = "0.1"`  # 10% spot-check with local fixed ops

Codec: JSON+zlib default. Pickle only with AURA_GRID_ALLOW_PICKLE (unsafe).


## GPU thermal safety (Worker)

Utilization % alone does not damage GPUs; **temperature and voltage** do.
Defaults (override via env):

| Env | Default | Meaning |
|-----|---------|---------|
| `AURA_GRID_MAX_GPU_TEMP_C` | 75 | Core temp pause |
| `AURA_GRID_MAX_GPU_MEM_TEMP_C` | 85 | VRAM temp (if sensor exists) |
| `AURA_GRID_MAX_HOTSPOT_C` | 95 | Hotspot (if sensor exists) |
| `AURA_GRID_MAX_GPU_PCT` | 95 | Soft util pause |
| `AURA_GRID_MAX_CPU_PCT` | 85 | CPU util pause |

Hardware tip (owner of Terminal 02): MSI Afterburner Power Limit ~80% + custom fan curve is safer than relying only on software pause.


## Grid Manager (monitor de terminais)

O Master grava `grid_status.json` (ou `AURA_GRID_STATUS_FILE`) com telemetria de cada Worker:

- CPU %, RAM %
- GPU % uso, temperatura (°C)
- Potência atual e limite (W), se NVML disponível
- online / last_seen

```powershell
# Uma vez
python scripts\grid_status.py

# Atualizar a cada 3s
python scripts\grid_status.py --watch 3

# JSON bruto
python scripts\grid_status.py --json

# PowerShell
.\windows\Watch-Grid-Status.ps1
```
