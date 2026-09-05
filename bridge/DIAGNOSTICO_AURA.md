# AURA QUANT-X Health Check

Execute sempre com o Python do ambiente da Bridge:

```bat
.venv\Scripts\python.exe diagnostico_aura.py
```

O diagnóstico é somente leitura: não instala pacotes, não baixa modelos e não altera a configuração. Ele verifica Python 3.11, NumPy, faster-whisper, CTranslate2, CUDA, criação real do Whisper em `cuda/float16`, Ollama e arquivos essenciais.
