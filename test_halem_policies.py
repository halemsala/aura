import importlib.util
from pathlib import Path

source = Path('/home/ubuntu/upload/AURA_HARNESS_HALem_PRO.py')
spec = importlib.util.spec_from_file_location('halem', source)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert mod.safe_name('Agente Teste') == 'agente-teste'
assert mod.repo_url('https://github.com/org/repo') == 'https://github.com/org/repo'
for bad in ('http://github.com/org/repo', 'https://evil.example/repo', 'https://github.com/org/repo?x=1'):
    try:
        mod.repo_url(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
print('policy tests: ok')
