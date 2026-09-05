"""Partilha de processamento GPU entre PCs.
Não transfere VRAM física. O worker remoto corre o trabalho e devolve o resultado.
Tecto 60% VRAM. Pausa se detectar jogo ou pressão de VRAM.
"""
