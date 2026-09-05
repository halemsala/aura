# aura-video-computer-use-deployment

Camada de governança Video + Computer Use para AURA.

- video.mode=dry_run por padrão
- execução só com `--execute` + `AURA_VIDEO_EXECUTION_APPROVED=true`
- computer_use.enabled=false
- Não publica, não faz upload, não sobrescreve origem
- Não substitui AURA_VIDEO_GROK_COMPLETE_DEPLOYMENT se já instalado
