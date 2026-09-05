import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("ALFRED_PROJECT_ROOT", Path(__file__).resolve().parent.parent))
DATA_ROOT = Path(os.environ.get("ALFRED_DATA_DIR", str(PROJECT_ROOT / "data" / "alfred")))
JOBS_DIR = DATA_ROOT / "jobs"
BACKUPS_DIR = DATA_ROOT / "backups"
CHECKPOINTS_DIR = DATA_ROOT / "checkpoints"
CAPTURES_DIR = DATA_ROOT / "captures"
CONFIG_PATH = PROJECT_ROOT / "config" / "alfred.json"
TOKEN_PATH = DATA_ROOT / "local_token"
PID_PATH = DATA_ROOT / "alfred.pid"
LOG_PATH = DATA_ROOT / "alfred.log"
PLUGINS_DIR = PROJECT_ROOT / "alfred" / "tools" / "plugins"
STAGING_DIR = DATA_ROOT / "plugins" / "staging"
PLUGIN_REVIEWS_DIR = DATA_ROOT / "plugins" / "reviews"

for _d in (DATA_ROOT, JOBS_DIR, BACKUPS_DIR, CHECKPOINTS_DIR, CAPTURES_DIR,
           PLUGINS_DIR, STAGING_DIR, PLUGIN_REVIEWS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
