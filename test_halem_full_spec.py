import asyncio
import importlib.util
from pathlib import Path

source = Path('/home/ubuntu/upload/AURA_HARNESS_HALem_PRO.py')
spec = importlib.util.spec_from_file_location('halem_full_spec', source)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

async def main():
    halem = mod.Halem()
    prompt = '# ROLE AND CONTEXT\n' + ('# OBJECTIVE\nCriar um agente de fusão de dados.\n' * 80)
    result = await halem.handle(prompt)
    assert 'PLANO PENDENTE' in result
    assert halem.dialogue is None
    assert halem.pending_action.startswith('plano p-')
    print('full spec tests: ok')

asyncio.run(main())
