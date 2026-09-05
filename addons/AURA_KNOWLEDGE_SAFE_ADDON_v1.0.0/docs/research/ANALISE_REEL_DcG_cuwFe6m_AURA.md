# Análise do Reel e aplicação ao AURA

**URL:** https://www.instagram.com/reel/DcG_cuwFe6m/  
**Perfil:** @thejplabs  
**Conteúdo público capturado:** legenda, hashtags, thumbnail e metadados acessíveis.

## Síntese

O Reel apresenta o **Find Skills** como uma Skill da Vercel capaz de procurar automaticamente outra Skill adequada para uma tarefa no Claude Code. A ideia central é substituir a procura manual em um grande catálogo por uma descoberta orientada por linguagem natural, seguida de filtragem e instalação.

A legenda descreve um fluxo simples: o usuário pede algo como “acha uma skill pra escrever conteúdo” ou “acha uma skill pra adaptar um app web pra mobile”; a ferramenta pesquisa um diretório amplo, filtra resultados considerados confiáveis e instala a Skill no Claude Code por um comando. A documentação pública da Vercel confirma a existência do ecossistema `skills`, o comando `npx skills add <owner/repo>`, a busca com `npx skills find <query>` e a compatibilidade com Claude Code e outros agentes [1] [2].

Para o AURA, o ganho mais importante não é instalar centenas de Skills automaticamente. É criar um **descobridor governado**, que pesquise candidatos, avalie origem, licença, integridade, permissões e compatibilidade, gere um relatório e aguarde aprovação antes de qualquer instalação ou integração.

## Conteúdo visual

A thumbnail do Reel contém o texto:

> “1 SKILL QUE FALTA”

A imagem mostra uma pessoa diante de código, com a marca Claude ao fundo. O título sugere que o vídeo demonstra uma Skill essencial ou ausente, mas o nome **Find Skills** aparece na legenda, não na thumbnail.

O Reel foi exibido com áudio mutado. O HTML público não forneceu um arquivo MP4 acessível; portanto, a análise audiovisual ficou limitada à thumbnail e à legenda. Não foi possível transcrever fala, demonstração de terminal ou textos que possam aparecer em quadros intermediários do vídeo.

## Legenda transcrita

> “A skill do Claude Code que acha a skill certa sozinha, pra qualquer tarefa. Chama Find Skills, é da Vercel.
>
> Se você usa Claude Code pra trabalhar, presta atenção: existe skill pronta pra quase tudo que você faz, e a chance de você não usar nenhuma é alta.
>
> Você instala uma vez. Depois é só pedir em português mesmo: ‘acha uma skill pra escrever conteúdo’ ou ‘acha uma skill pra adaptar um app web pra mobile’.
>
> Ela varre um diretório com mais de 700 mil skills e filtra o lixo. Só passa instalação real, estrela real de GitHub e fonte confiável. E instala direto dentro do teu Claude Code. O setup inteiro é um comando.
>
> No fim é terceirizar a garimpagem: em vez de você vasculhar 700 mil skills, ela vasculha por você.
>
> Qual tarefa tua você mandaria ela procurar primeiro?
>
> Comenta SKILL que eu te mando o guia da Find Skills com o link do repo.”

Hashtags exibidas: `#claudecode`, `#claudeskills`, `#inteligenciaartificial`, `#iaparanegocios` e `#findskills`.

## O que foi confirmado externamente

A documentação oficial da Vercel descreve Skills como capacidades empacotadas que ampliam agentes de IA com comportamentos especializados. Ela informa que o CLI pode instalar pacotes com `npx skills add <owner/repo>`, instalar uma Skill específica com `--skill` e pesquisar o diretório com `npx skills find <query>` [1].

O repositório oficial `vercel-labs/skills` descreve o CLI como uma ferramenta do ecossistema aberto de Skills, compatível com Claude Code, Codex, Cursor e outros agentes. O README documenta comandos de descoberta, instalação, listagem, atualização e remoção, além de opções de escopo global ou de projeto [2].

O repositório oficial `vercel-labs/agent-skills` contém Skills de Vercel para React, Next.js, design web, escrita, automação de navegador, deployment, workflows e outras áreas. O mesmo repositório documenta a estrutura baseada em `SKILL.md`, scripts opcionais e referências auxiliares [3].

| Afirmação do Reel | Situação |
|---|---|
| Existe uma ferramenta/CLI de Skills da Vercel | Confirmada por documentação oficial [1] [2] |
| Pode pesquisar Skills por consulta | Confirmada por `npx skills find <query>` [1] [2] |
| Pode instalar um pacote por comando | Confirmada por `npx skills add <owner/repo>` [1] [2] |
| Funciona com Claude Code | Confirmada pela documentação e pelo README [1] [2] |
| Há mais de 700 mil Skills | Alegação da legenda; não validada independentemente nesta análise |
| Cada resultado tem estrela real e fonte confiável | Alegação do Reel; a existência do filtro específico não foi confirmada na documentação consultada |
| O Find Skills é exatamente uma Skill da Vercel | A legenda afirma isso; as fontes oficiais consultadas confirmam o ecossistema/CLI, mas não permitiram verificar o pacote específico chamado “Find Skills” como uma Skill isolada |

## Aplicação segura ao AURA

O AURA pode aproveitar o conceito como um módulo de **Skill Discovery and Governance**. Esse módulo não deve instalar código diretamente. Sua responsabilidade inicial deve ser pesquisar e produzir um catálogo de candidatos.

| Estágio | Função | Estado recomendado |
|---|---|---|
| Descoberta | Interpretar a solicitação e buscar Skills candidatas | Permitido offline ou em sandbox |
| Triagem | Verificar repositório, licença, atividade, estrutura, hashes e permissões | Permitido com relatório |
| Compatibilidade | Comparar a Skill com o runtime, versão e política do AURA | Permitido sem alteração |
| Simulação | Mostrar arquivos que seriam instalados e possíveis conflitos | Permitido |
| Aprovação | Exigir confirmação explícita do operador | Obrigatório |
| Instalação | Copiar para namespace isolado, com backup e manifesto | Opt-in |
| Validação | Rodar `compileall`, testes e auditoria sem ativar serviços | Obrigatório |
| Integração | Conectar ao `AuraController`, `skill_runtime` ou agentes | Etapa separada |

### Regras de segurança específicas

O AURA não deve confiar em estrelas, popularidade ou nome do repositório como prova suficiente de segurança. A origem deve ser verificada, mas o pacote ainda precisa passar por análise estática. O README do CLI informa que a instalação pode usar repositórios Git, URLs, caminhos locais e arquivos compactados; isso amplia a superfície de risco e exige limites de tamanho, número de arquivos, revisão de scripts e política de dependências [2].

A instalação deve ser **namespaced**, por exemplo em `addons/discovered_skills/<slug>/`, sem sobrescrever Skills existentes. O manifest deve registrar URL, commit ou tag, hash SHA-256, licença, data de análise, arquivos, permissões solicitadas, dependências e resultado dos testes.

O AURA deve rejeitar automaticamente Skills que iniciem serviços no import, usem `subprocess` ou shell sem justificativa, alterem autostart, leiam credenciais, publiquem conteúdo, enviem mensagens, instalem dependências silenciosamente ou tentem alterar `PAPER_TRADE`, `EXECUTION_ALLOWED` ou `GLM_ADVISORY_ONLY`.

## Arquitetura proposta

```text
Pedido em português
        ↓
Skill Discovery Planner
        ↓
Busca por nome, descrição e domínio
        ↓
Source + License + Hash + Permission Audit
        ↓
Compatibility Check com AURA
        ↓
Relatório de candidatos
        ↓
Aprovação explícita
        ↓
Staging namespaced + backup
        ↓
Compileall + testes + release audit
        ↓
Integração opt-in no Skill Runtime
```

## Consultas úteis para o AURA

Exemplos de consultas que o descobridor poderia aceitar são: “encontre uma Skill para auditar acessibilidade sem publicar”; “encontre uma Skill para testar um dashboard em staging”; “encontre uma Skill para revisar Python sem instalar dependências”; “encontre uma Skill para gerar relatório de release com hashes”; e “encontre uma Skill para depuração sistemática com evidências”.

O descobridor deve responder com uma tabela, não com instalação automática:

| Campo | Conteúdo obrigatório |
|---|---|
| Nome | Nome canônico da Skill |
| Fonte | URL completa e repositório |
| Versão | Tag, commit ou release |
| Licença | Licença declarada e compatibilidade |
| Escopo | Projeto ou global |
| Arquivos | Lista e tamanho total |
| Permissões | Rede, subprocesso, escrita, credenciais, navegador |
| Dependências | Presentes, opcionais ou ausentes |
| Riscos | Achados estáticos e limitações |
| Testes | Comandos e resultados |
| Decisão | Candidata, bloqueada ou aguardando revisão |

## Recomendação para o AURA Maximizer

A funcionalidade mais adequada é criar uma Skill local chamada `aura-skill-discovery-governance`. Ela deve encapsular quatro funções: pesquisar candidatos, pontuar compatibilidade, produzir um manifesto e preparar uma instalação plan-only. A função de instalação real deve permanecer fora do agente e exigir aprovação explícita.

A pontuação não deve ser baseada somente em popularidade. Uma política equilibrada poderia dar maior peso a origem verificável, licença compatível, estrutura válida, ausência de efeitos no import, testes reproduzíveis, compatibilidade com Python/Node do host e aderência ao Paper Lock. Popularidade pode ser apenas um sinal secundário.

## Limitações

A extração pública do Reel foi máxima quanto à legenda, hashtags, autor, thumbnail e metadados acessíveis. O vídeo e o áudio não ficaram disponíveis como arquivo público no acesso sem login; por isso, não foi possível transcrever a fala nem confirmar comandos demonstrados na tela.

A contagem de “mais de 700 mil Skills”, a filtragem por “estrela real” e a afirmação de que cada fonte é confiável são declarações do Reel. A documentação oficial confirma o CLI e o ecossistema, mas não confirma, nas páginas consultadas, esses números ou todos esses critérios de filtragem.

### Referências

[1]: https://vercel.com/docs/agent-resources/skills "Vercel — Agent Skills"

[2]: https://github.com/vercel-labs/skills "Vercel Labs — skills CLI"

[3]: https://github.com/vercel-labs/agent-skills "Vercel Labs — official collection of agent skills"

[4]: https://vercel.com/changelog/introducing-skills-the-open-agent-skills-ecosystem "Vercel — Introducing skills, the open agent skills ecosystem"
