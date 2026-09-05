# CornerAI AURA Unified 12.5.8 — Compatibilidade de navegador

## Opera

O `manifest.json` desta distribuição usa a API de Sidebar do Opera (`sidebar_action`) e não declara a permissão Chrome `sidePanel`, evitando o erro `Permission 'sidePanel' is unknown.` observado no gerenciador de extensões do Opera.

## Chrome

A API nativa `chrome.sidePanel` é suportada pelo Chrome com a permissão `sidePanel` e a chave `side_panel`. Para uma build especificamente voltada ao Chrome, use uma variante de manifest que restaure esses dois campos.

## Integridade de escanteios

A revisão não considera mais uma discrepância como alinhada apenas porque a diferença é pequena. Para aprovação automática, os eventos individuais precisam bater exatamente com as estatísticas por lado. Em caso de timeline parcialmente carregada no início da partida, o estado fica `AGUARDANDO`/`REVIEW` sem criar eventos sintéticos.
