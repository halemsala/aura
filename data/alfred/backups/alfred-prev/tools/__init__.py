# Importar para registar todas as ferramentas no registry.
from . import open_url  # noqa: F401
from . import files     # noqa: F401
from . import typing_tool  # noqa: F401
from . import memory    # noqa: F401
from . import capture   # noqa: F401
from . import system_tools  # noqa: F401
from . import patch  # noqa: F401
from . import jobs_tools  # noqa: F401
from .. import autocorrect  # noqa: F401
from . import tooling  # noqa: F401
from . import control  # noqa: F401
from . import apps  # noqa: F401
from . import skills_search  # noqa: F401
from . import employee  # noqa: F401
from . import gpu_share_tools  # noqa: F401
from . import observe  # noqa: F401
from . import repair_voice  # noqa: F401
from . import aura_ops  # noqa: F401
from . import employee_life  # noqa: F401
from . import hid  # noqa: F401
from . import engineer  # noqa: F401
from ..registry import freeze_core
from ..plugin_loader import load_all_plugins

freeze_core()
load_all_plugins()
