# Instalação F — AURA Final Check e mapa do sistema

## Escopo

Esta instalação adiciona `scripts/aura_final_check.py`, um verificador de aceitação do pacote AURA, e `docs/AURA_ESTADO_DO_SISTEMA.md`, um mapa documental dos módulos e pendências descritos no anexo.

A Instalação F é independente das instalações A, B, C, D e E. Ela não altera o servidor de voz, o CommandCenter, o Agent Skill Engine ou qualquer rotina de inicialização.

## Modos de execução

O modo rápido executa verificações locais de sintaxe e imports, grava o relatório `AURA_FINAL_CHECK.md` e não consulta Ollama, portas locais, banco, journals, dotnet ou variáveis externas.

O modo completo, quando executado manualmente pelo usuário, pode verificar dependências opcionais, endpoints locais, banco, journals e compilação .NET. Essas verificações são somente leitura, mas podem iniciar subprocessos de importação, testes e `dotnet build`; por isso não são executadas durante esta instalação.

```text
python scripts/aura_final_check.py --quick
python scripts/aura_final_check.py
python scripts/aura_final_check.py --verbose
```

## Proteções e correções aplicadas

O verificador usa `PYTHONPATH` explícito nos subprocessos de import e self-test, corrige a exclusão por caminho de diretórios de dados, trata dependências opcionais como informativas e não transforma a ausência de uma dependência opcional em falha fatal.

O modo rápido retorna antes das verificações de rede e de ambiente. O inventário continua apontando arquivos ausentes como falhas informativas no modo completo, permitindo distinguir uma árvore incompleta de uma falha de import.

O script não inicia serviços, não habilita autostart, não instala pacotes, não faz `ollama pull`, não envia dados a terceiros e não altera as políticas `PAPER_TRADE=true`, `EXECUTION_ALLOWED=false` e `GLM_ADVISORY_ONLY=true`.

## Estado do sistema

O mapa em `docs/AURA_ESTADO_DO_SISTEMA.md` é documentação de referência derivada do anexo. Ele não constitui uma confirmação de que todos os módulos ou serviços listados existem na árvore atual. O relatório gerado pelo Final Check é a fonte de verificação do estado observado.

## Reversão

O backup independente está em `.install-backups/installation-f-20260825_074709/`. Para reverter somente esta instalação, remova `scripts/aura_final_check.py`, `docs/AURA_ESTADO_DO_SISTEMA.md` e o diretório `addons/installation_f_final_check`, seguindo o `BACKUP_MANIFEST.txt` correspondente. Não altere os arquivos das instalações A, B, C, D ou E.
