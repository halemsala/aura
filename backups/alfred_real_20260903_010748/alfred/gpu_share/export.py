"""python -m alfred.gpu_share.export — gera o ZIP do worker."""
import json
from .manager import export_pack

if __name__ == "__main__":
    print(json.dumps(export_pack(), ensure_ascii=False, indent=2))
