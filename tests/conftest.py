import os, sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def test_home(tmp_path_factory):
    """Home isolada para a allowlist de ficheiros. Nunca toca no Desktop real."""
    home = tmp_path_factory.mktemp("home")
    for d in ("Desktop", "Documents", "Downloads"):
        (home / d).mkdir()
    os.environ["ALFRED_TEST_HOME"] = str(home)
    os.environ["ALFRED_EXEC_ALLOWED"] = "1"   # permite testar ferramentas sensíveis
    from alfred.config import reset_config_cache
    reset_config_cache()
    yield home
    os.environ.pop("ALFRED_TEST_HOME", None)
    os.environ.pop("ALFRED_EXEC_ALLOWED", None)
