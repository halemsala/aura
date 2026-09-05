# AURA MAX — corrigir Hermes sem popups

## Diagnóstico encontrado

O pacote contém várias rotinas que abrem páginas explicitamente. O problema mais directo está em `AURA_HERMES_V10_ULTRA.bat`, que chama `start "" http://127.0.0.1:8777/chat` e `start "" http://127.0.0.1:8778/`. Existe ainda um caminho mais agressivo em `scripts/aura_programmer_agent.py`: depois de cada reparo ele gera `RELATORIO_ERROS_LATEST.html` e chama `os.startfile(...)` no Windows. Se algum instalador, monitor ou operador relançar estas rotinas, cada ciclo cria uma nova janela.

O segundo problema é de configuração. O chat Hermes escolhe o modelo por variáveis de ambiente e ainda tem `qwen2.5:3b-instruct` como fallback, enquanto o catálogo principal também define `llama3.2:3b`. Assim, ter `qwen3:8b` instalado não significa que ele esteja a ser usado.

## O que a entrega faz

O ficheiro `AURA_CORRIGIR_HERMES_MAX.bat` chama o auxiliar PowerShell na raiz do pacote. A versão corrigida remove a barra final de `C:\aura\` antes de passar o caminho, evitando que o Windows transforme o argumento em `C:\aura\"`. O auxiliar:

1. Cria um backup datado antes de modificar qualquer ficheiro.
2. Bloqueia a abertura automática de relatórios através de `AURA_NO_BROWSER=1`.
3. Corrige o agente programador para guardar o relatório sem abrir HTML.
4. Faz o BAT ultra respeitar `AURA_NO_BROWSER=1` quando ele existir.
5. Configura `qwen3:8b`, `OLLAMA_KEEP_ALIVE=20m`, `num_ctx=4096`, `num_predict=1024` e `num_gpu=99`.
6. Desliga o caminho GLM/cloud, mantendo o processamento no Ollama local.
7. Reinicia apenas um Hermes cujo comando seja reconhecido como `AURA_RUN_HERMES.py` ou `hermes_v10_chat_api.py`; um processo desconhecido que ocupe a porta 8777 não é terminado.
8. Inicia Bridge, Engine, Matriz, Control, Voice e Hermes apenas quando a porta correspondente está livre.
9. Faz warmup do Qwen3 e grava o estado em `logs_supervisor\AURA_MAX_BOOT_LATEST.json`.
10. Não abre o navegador, não mata o Ollama e não altera `paper_trade=true` nem `execution_allowed=false`.

> O aumento de capacidade é limitado pelo modelo local de 8B e pela VRAM disponível. O BAT melhora a selecção, a estabilidade e a execução técnica de baixo risco; não transforma um modelo 8B numa capacidade ilimitada nem autoriza acções destrutivas sem confirmação.

## Instalação

Copie estes dois ficheiros para a raiz da instalação, por exemplo `C:\aura`, ao lado de `engine`, `bridge`, `hermes_v10` e `scripts`:

```text
AURA_CORRIGIR_HERMES_MAX.bat
AURA_CORRIGIR_HERMES_MAX.ps1
```

Feche apenas as janelas do Hermes que pretende substituir e execute `AURA_CORRIGIR_HERMES_MAX.bat` como utilizador normal. O BAT fica agora aberto por defeito em modo diagnóstico, para poderes ver o resultado e o código de erro. Depois de confirmares que está tudo bem, podes usar `AURA_CORRIGIR_HERMES_MAX.bat /AUTO_CLOSE`; em caso de erro, o modo diagnóstico força a janela a permanecer aberta. Não é necessário abrir o navegador. Se for necessário executar sem recarregar o Hermes que já está activo, use:

```bat
AURA_CORRIGIR_HERMES_MAX.bat /KEEP_HERMES
```

Nesse modo, o novo modelo só será carregado no próximo reinício do Hermes.

## Verificação

Consulte:

```text
logs_supervisor\aura_max_fix.log
logs_supervisor\AURA_MAX_BOOT_LATEST.json
logs_supervisor\hermes.out.log
logs_supervisor\hermes.err.log
```

Para abrir o chat manualmente, use apenas quando quiser:

```text
http://127.0.0.1:8777/chat
```

O BAT não abre esta URL automaticamente.

## Rollback

O auxiliar cria uma pasta semelhante a:

```text
backups\aura_max_20260902_153000\
```

Para reverter, pare o Hermes, copie os ficheiros da pasta de backup de volta para os respectivos caminhos originais e reinicie os serviços. Não apague os backups até confirmar que o novo arranque está estável.

## Limite deliberado de autonomia

O modo técnico fica mais autónomo para diagnóstico, reinício idempotente, validação de sintaxe e correcções previstas pelo pacote. A confirmação `AUTORIZO`, o modo paper-trade e a protecção do Ollama continuam activos. Remover estes limites daria ao chat poder para executar comandos ou alterar dados sem uma fronteira verificável, o que não é uma correcção de eficiência.
