#!/usr/bin/env bash
# Lab self-signed cert for AURA Grid TLS (LAN). Not a public CA.
set -euo pipefail
OUT="${1:-.}"
openssl req -x509 -newkey rsa:2048 -keyout "$OUT/key.pem" -out "$OUT/cert.pem"   -days 365 -nodes -subj "/CN=aura-grid-lab"
echo "Wrote $OUT/cert.pem and $OUT/key.pem"
echo "Worker: export AURA_GRID_TLS=true AURA_GRID_TLS_INSECURE=true  # lab only"
echo "Or: AURA_GRID_TLS_CA=$OUT/cert.pem with check_hostname=false for self-signed"
