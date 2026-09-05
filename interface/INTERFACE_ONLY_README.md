# AURA QUANT-X — Interface Live Desk

Este pacote contém exclusivamente a camada visual do AURA QUANT-X. A entrega foi reorganizada para priorizar a mesa de análise esportiva ao vivo, com placar, logos representativas, timeline, pressão, momentum, xG, radar de mercados, análise contextual da IA, chat AURA e alertas de tela inteira.

A interface usa dados demonstrativos locais para permitir validação visual e de interação sem iniciar Engine, Bridge, Voice, Telegram, agentes, banco, extensões, automações ou chamadas externas. Os controles de ocultar/mostrar módulos e os estados do chat e dos alertas são locais ao navegador.

## Escopo

O release inclui `client/`, manifestos mínimos do frontend e arquivos de configuração necessários para instalar e compilar a interface. Diretórios operacionais do pacote original, como `engine`, `agents`, `bridge`, `desktop`, `scripts`, `addons`, `drizzle` e `server`, foram excluídos deliberadamente.

## Validação

A validação realizada foi `tsc --noEmit` e `vite build`, ambos concluídos sem erros. O build é exclusivamente de frontend. As referências visuais inspiraram o contraste de painéis, a hierarquia de KPIs, as visualizações temporais, os módulos recolhíveis e a presença contextual de IA.
