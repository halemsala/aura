@echo off
cd /d "%~dp0\.."
mkdir ARQUIVO_LEGADO\servers_antigos 2>nul
move /Y engine\server_elite_gpu.py ARQUIVO_LEGADO\servers_antigos\ 2>nul
move /Y engine\server_gpu_master.py ARQUIVO_LEGADO\servers_antigos\ 2>nul
move /Y engine\server_multi_agents_elite.py ARQUIVO_LEGADO\servers_antigos\ 2>nul
move /Y engine\server_multi_agents_v11.py ARQUIVO_LEGADO\servers_antigos\ 2>nul
move /Y engine\server_tier1_quant.py ARQUIVO_LEGADO\servers_antigos\ 2>nul
echo Legacy servers moved (or already absent).
