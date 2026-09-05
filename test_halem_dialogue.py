import asyncio
import importlib.util
from pathlib import Path

source = Path('/home/ubuntu/upload/AURA_HARNESS_HALem_PRO.py')
spec = importlib.util.spec_from_file_location('halem_dialogue', source)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

async def main():
    halem = mod.Halem()
    first = await halem.handle('consegue construir novos agentes no aura para novas tarefas?')
    assert halem.dialogue == 'create_agent'
    assert 'uma única mensagem' in first
    second = await halem.handle('um agente que monitore falhas e prepare um relatório')
    assert 'PLANO PENDENTE' in second
    assert halem.pending_action.startswith('plano p-')
    print('dialogue tests: ok')

asyncio.run(main())
