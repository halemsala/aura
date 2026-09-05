#!/usr/bin/env bash
# Stage-only: does not activate Computer Use or install drivers.
set -euo pipefail
echo "AURA CUA guarded connector — stage only. computer_use_enabled=false"
echo "Use Windows Install-AURA-CUA-Safe.ps1 on the real host. No services started."
exit 0
