# Reel DclGpkxyb1U — evidências e aplicação no AURA

## Fatos públicos confirmados

A legenda do Reel, publicado por `maestrosdaiahub`, apresenta a ferramenta **Soup** como open source e gratuita e descreve a técnica **layer streaming**. A postagem afirma que um modelo de 8B parâmetros pode usar cerca de 3,3 GB de VRAM em vez de 16 GB, rodando em uma GPU de notebook com 4 GB e alcançando 119 tokens/segundo durante treinamento.

A verificação em fontes públicas encontrou o repositório `https://github.com/MakazhanAlpamys/Soup`, o site `https://trysoup.dev/` e uma descrição técnica independente em `https://gigazine.net/gsc_news/en/20260806-soup-fine-tune-llm/`. O repositório informa licença Apache-2.0, Python 3.10–3.12 e que layer streaming é beta. As medições publicadas referem-se a condições específicas e não são garantia para outros computadores.

## Conhecimento transferido para o AURA

O AURA pode usar uma Skill para analisar configurações de fine-tuning local, diferenciar pesos de ativações/logits, advertir sobre batch e comprimento de sequência, gerar fingerprint de configuração e exigir benchmark antes de qualquer uso. O AURA não deve assumir que menor VRAM significa menor custo total ou maior velocidade.

## Limitações

O vídeo/áudio do Reel não ficou disponível como arquivo público para transcrição nesta sessão. Comandos ou demonstrações adicionais não foram tratados como fatos. O pack criado não contém o repositório Soup nem instala seus extras; contém somente uma ponte offline e a Skill de governança.
