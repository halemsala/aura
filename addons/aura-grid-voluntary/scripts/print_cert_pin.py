"""Print SHA256 pin of a PEM certificate for AURA_GRID_CERT_PIN."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.pinning import cert_sha256_pem_file
path = sys.argv[1] if len(sys.argv) > 1 else "cert.pem"
print(cert_sha256_pem_file(path))
