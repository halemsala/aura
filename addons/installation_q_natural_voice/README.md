# Instalação Q — Natural Voice

## Escopo

Esta instalação adiciona `engine/agents/natural_voice.py`, extraído do `pasted_content_17.txt`, como uma camada opcional de síntese de voz com autodetecção de Chatterbox, Kokoro, F5-TTS e fallback para edge-tts.

O módulo foi instalado **separadamente**. Os hunks H-NV1 e H-NV2 do anexo não foram aplicados automaticamente: `bridge/jarvis_voice_server.py`, `jarvis_command_center.py` e o startup global permanecem inalterados. A ativação futura exige revisão específica, teste de latência, confirmação de privacidade e decisão explícita.

## Estado seguro

Nenhum pacote `pip` foi instalado. Chatterbox, Kokoro, F5-TTS, PyTorch, soundfile e modelos de voz não foram baixados. O módulo não abre microfone, não inicia servidor, não cria autostart e não faz chamadas de rede durante importação ou self-test padrão.

A autodetecção é feita somente quando `NaturalVoiceEngine` é instanciado. Backends opcionais que estejam ausentes ou quebrados são tratados como indisponíveis e o módulo conserva o fallback. A síntese real no self-test exige a variável explícita `AURA_NATURAL_VOICE_SELFTEST_SYNTHESIS=1`.

## Arquivos

| Arquivo | Função |
|---|---|
| `engine/agents/natural_voice.py` | Cópia canônica instalada |
| `addons/installation_q_natural_voice/natural_voice_from_pasted_content_17.py` | Cópia rastreável do addon Q |
| `addons/installation_q_natural_voice/INSTALL_Q_MANIFEST.txt` | Hashes, backup e estado de integração |
| `addons/installation_q_natural_voice/README.md` | Documentação desta instalação |

## Validação

O teste estrutural recomendado é:

```text
python engine/agents/natural_voice.py
```

O resultado esperado em ambiente sem engines opcionais é detecção de `edge-tts` como fallback, verificação do estado e do singleton, com síntese real marcada como `SKIP` por padrão. A validação não deve instalar dependências ou ativar o servidor de voz.

## Ativação futura

A instalação de qualquer backend deve ser feita individualmente, com revisão da licença, tamanho dos modelos, diretório persistente, consumo de VRAM/RAM e necessidade de rede. A integração no voice server e o comando de ajuste de emoção devem ser tratados em uma instalação posterior e independente; não fazem parte da Instalação Q atual.

## Reversão

O backup anterior está em `.install-backups/installation-q-natural-voice-20260825_094328/`. Como o arquivo canônico não existia antes desta instalação, o backup registra essa ausência. Para reverter somente Q, remova o arquivo canônico, o diretório do addon e preserve as demais instalações.
