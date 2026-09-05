# Auditoria e correção da voz AURA QUANT-X

## Resultado executivo

A causa do áudio antigo/feminino e do erro `No module named 'faster_whisper'` foi confirmada: a consulta estava chegando a um **processo Voice legado** instalado em `C:\Users\salaa\AppData\Local\Programs\AURA Quant-X\AURA_QUANT_X\`, que já ocupava a porta 8099. Esse processo não tinha os campos de diagnóstico introduzidos na versão corrigida e utilizava uma venv sem as dependências atuais.

O pacote final não tenta mascarar essa situação. Ele identifica a versão do Voice pelo build `AURA-VOICE-MALE-V3`, recusa considerar um processo sem esse build como saudável e instrui o usuário a encerrar somente o PID confirmado antes de iniciar a instalação nova.

## Falhas confirmadas

O diagnóstico anexado pelo usuário mostrou `ok: false`, `stt: não carregado`, `llm: não resolvido` e `No module named 'faster_whisper'`. Ele também não continha `build_id`, `tts_runtime`, `configured_voice`, `gender` ou `fallback`. A combinação desses sinais comprova que o endpoint consultado era de uma geração anterior do servidor, e não do arquivo corrigido no novo pacote.

Havia ainda uma inconsistência de parametrização: `base_rate: 0.96` e `base_pitch: 0.88` eram multiplicadores, enquanto o Edge TTS recebe strings como `-4%` e `-8Hz`. Esses valores agora são normalizados antes da síntese.

## Correções aplicadas

| Ponto | Correção | Evidência no pacote |
|---|---|---|
| Identidade da versão | `VOICE_BUILD_ID = "AURA-VOICE-MALE-V3"` no servidor e no health/diagnóstico | Teste de contrato e verificador independente aprovados |
| Processo antigo na porta 8099 | BAT mestre e launcher do Voice recusam servidor sem o build esperado | `ensure_voice_service` e validação do diagnóstico |
| Venv do Voice | Launcher usa exclusivamente `engine\\venv\\Scripts\\python.exe` | Preflight e verificador estático aprovados |
| Voz autoritativa | Edge masculino por padrão; XTTS por WAV quando explicitamente ativado | Configuração e ativador reversível validados |
| Lista masculina | Antonio, Humberto, Nicolau e Donato | Allowlist no TTS e no preflight |
| Fallback gTTS | Removido do caminho de síntese; erro explícito quando Edge TTS masculino não está disponível | `VOICE_SELECTION_ERROR` e `edge_tts_male_unavailable` |
| Fallback de navegador | Clientes não reproduzem áudio por `speechSynthesis` como fallback silencioso | Clientes validam metadata do áudio |
| Perfil alternativo | `pt-BR-FranciscaNeural` removida dos arquivos de configuração avaliados | Verificador independente aprovado |
| Parâmetros | `0.96` → `-4%`; `0.88` → `-8Hz` | Teste de normalização aprovado |
| Diagnóstico | Expõe `build_id`, `configured_voice`, `tts_runtime`, `engine`, `gender`, `ready` e `fallback` | Teste de contrato aprovado |
| Resposta TTS | `/api/voice/neural` e `/api/voice/tts` retornam voz/engine efetivas e `fallback=disabled` | Código e teste estático aprovados |
| Clientes | Sidepanel, voice-assistant e adaptador rejeitam gênero não masculino e fallback legado | Sintaxe dos três clientes aprovada |
| Preflight | Reprova dependências ausentes, asset inválido, perfil ausente ou voz fora da allowlist | `voice_preflight.py` validado |
| Instalação | Instalador usa `python -m pip`, verifica `faster_whisper` e registra logs | BAT mestre e instalador arquivado auditados |

## Correção da instalação Windows

O BAT mestre foi ajustado para funcionar em caminhos com espaços, como `Nova pasta`. A elevação agora relança diretamente o próprio BAT com `Start-Process`, e a abertura dos launchers usa quoting compatível com `cmd.exe`. Todos os BATs foram normalizados para terminadores de linha CRLF; isso evita que o CMD interprete comandos com o primeiro caractere truncado, como ocorreu com as mensagens `'et'` e `'f'`. O autoteste não depende mais de argumentos de linha de comando: o BAT define `AURA_SELF_TEST_ROOT` e `AURA_SELF_TEST_PHASE` para cada fase, e o Python usa essas variáveis como canal principal. Isso evita que barras invertidas finais e aspas de caminhos Windows sejam interpretadas como parâmetros inválidos.

A distribuição conserva os BATs oficiais de instalação, inicialização e ativação/restauração na raiz e inclui os launchers auxiliares em `ARQUIVO_LEGADO\\BAT_PS1`. Se essa pasta auxiliar não existir após a extração, o pacote está incompleto ou foi extraído por cima de uma instalação anterior.

## Sobre a WAV masculina

A WAV `voz_masculina_referencia.wav` é mantida como referência documental. Uma gravação de referência não é, por si só, um modelo de clonagem. Para que o áudio seja sintetizado no timbre da gravação, seria necessário instalar e habilitar um engine compatível, como XTTS/Coqui, com seus pesos e dependências. O pacote mantém Edge TTS como caminho padrão porque XTTS altera dependências, consumo de VRAM e compatibilidade com Python/Torch.

O caminho padrão corrigido é Edge TTS `pt-BR-AntonioNeural`, uma voz neural masculina remota. Para usar o timbre do WAV, execute `AURA_ATIVAR_VOZ_REFERENCIA.bat`, que instala o extra opcional Coqui TTS somente após confirmação e ativa XTTS em CPU com backup. Se o extra falhar, a configuração Edge permanece intacta e pode ser restaurada com `AURA_RESTAURAR_VOZ_EDGE.bat`.

## Evidência de validação

A validação no sandbox aprovou os testes Python de contrato do Voice e do Desktop, a sintaxe JavaScript dos clientes, o runtime advisory dos agentes, o verificador independente e a cópia de distribuição com hashes relativos, build do Voice, manual, BATs de proteção de processo e ausência dos artefatos proibidos. Foram observados apenas quatro avisos de depreciação do FastAPI sobre `on_event`; eles não causaram falha e ficam como melhoria técnica futura.

| Validação | Resultado |
|---|---:|
| Testes Python Voice/Desktop | 13 aprovados |
| Sintaxe JavaScript dos clientes | 3 arquivos aprovados |
| Verificador independente do ZIP | aprovado |
| Hashes no pacote | 588 aprovados |
| Arquivos no ZIP | 589, incluindo `SHA256SUMS.txt` |
| Logs, bancos, JSONL, PYCs e `__pycache__` no ZIP | 0 encontrados |
| Runtime Windows, GPU, microfone, Ollama e Edge TTS | pendente de execução no computador do usuário |

## Procedimento Windows obrigatório

Extraia `AURA_QUANT_X_v12.7.0_VOICE_FIX_FINAL.zip` em uma **pasta completamente nova**. Não sobrescreva a instalação antiga e não execute o BAT a partir de `C:\Users\salaa\AppData\Local\Programs\AURA Quant-X\AURA_QUANT_X\`.

Antes de executar o novo instalador, abra o PowerShell e identifique o processo que ocupa a porta 8099:

```powershell
Get-NetTCPConnection -LocalPort 8099 -State Listen |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

Confirme que o PID pertence ao Voice antigo e encerre somente esse PID:

```powershell
Stop-Process -Id SEU_PID -Force
```

Em seguida, abra o arquivo **`AURA_INSTALAR_E_INICIAR_TUDO.bat`** da pasta nova como Administrador. Ele instala ou repara a venv `engine\\venv`, verifica `faster-whisper`, inicializa Bridge, Engine e Voice na sequência e mantém as janelas dos serviços abertas. Ele não encerra processos automaticamente.

Depois valide a identidade do processo ativo:

```powershell
Invoke-RestMethod http://127.0.0.1:8099/api/voice/diagnostic |
  ConvertTo-Json -Depth 8
```

A resposta da versão correta deve conter, no mínimo, os seguintes valores:

```text
build_id: AURA-VOICE-MALE-V3
configured_voice: pt-BR-AntonioNeural
gender: male
fallback: disabled
```

O campo `ready` só deve ser considerado operacional quando o carregamento do STT/LLM terminar sem erro. A ausência de `build_id` ou a mensagem `No module named 'faster_whisper'` significa que o processo antigo ainda está ativo ou que a instalação nova não foi concluída; nesse caso, não usar o áudio nem iniciar uma segunda instância.

## Limitações honestas

A auditoria de código, contratos, hashes e estrutura foi concluída no sandbox. A confirmação do som masculino efetivo, do carregamento de `faster-whisper`, da detecção CUDA da RTX 4050, do Ollama/GLM-4, do microfone, da autenticação no SokkerPRO e do WebView2 exige execução no Windows do usuário. O sistema continua estritamente em **PAPER TRADE ONLY**.
