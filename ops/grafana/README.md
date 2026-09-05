# Grafana + Prometheus — AURA V25

## Subir Prometheus (Docker exemplo)
```bash
docker run -d --name aura-prom -p 9090:9090 \
  -v %CD%/ops/prometheus:/etc/prometheus \
  prom/prometheus --config.file=/etc/prometheus/prometheus.yml
```

## Subir Grafana
```bash
docker run -d --name aura-graf -p 3000:3000 grafana/grafana
```
1. Data source Prometheus: http://host.docker.internal:9090
2. Import: ops/grafana/aura_v25_dashboard.json

## Sem Docker
- Instale Prometheus e aponte `--config.file=ops/prometheus/prometheus.yml`
- Grafana Import JSON do dashboard
