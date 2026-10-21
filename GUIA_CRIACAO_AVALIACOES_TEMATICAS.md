# Guia para criar avaliações temáticas

## Etapa separada: gerar candidatos de temas

Antes da curadoria descrita abaixo, é possível gerar candidatos de forma
reproduzível a partir das entidades já armazenadas em `article_entities`. Esta
etapa não escolhe os 20 artigos relevantes: ela sugere temas e calcula uma medida
de prevalência para ajudar a selecionar temas de dificuldades diferentes.

Execute:

```bash
uv run python -m src \
  --generate-themes resultados/temas_2025_2026.json
```

O algoritmo considera entidades não marcadas como lixo em artigos com data de
publicação dentro do intervalo inclusivo (padrão `2025-06-01` a `2026-06-30`).
Identidades canônicas são usadas quando disponíveis; caso contrário, usa-se o
texto da entidade. Para cada entidade isolada e cada par de entidades que aparece
no mesmo artigo, conta-se o número de URLs distintas que contêm todas as
entidades do conjunto. Os candidatos são ordenados por contagem decrescente e,
em empates, pela identidade das entidades. O resultado seleciona até cinco
candidatos por faixa:

| Faixa | Artigos correspondentes |
|---|---:|
| rara | 10–49 |
| média | 50–199 |
| comum | 200–1000 |

Os valores são parâmetros de entrada e podem ser alterados. Por exemplo:

```bash
uv run python -m src \
  --generate-themes resultados/temas.json \
  --theme-date-from 2025-01-01 --theme-date-to 2025-12-31 \
  --theme-min-articles 5 --theme-max-articles 500 \
  --theme-band-edges 25 100 --theme-per-band 8 \
  --theme-max-entities 2
```

`--theme-band-edges` define limites superiores exclusivos das faixas internas;
com os padrões, as faixas são `[10, 50)`, `[50, 200)` e `[200, 1001)`. O máximo
de entidades considerado é um ou dois. A seleção é determinística para o mesmo
conteúdo do banco e os mesmos parâmetros. Como os temas dependem das entidades
armazenadas, alterações posteriores nessas anotações podem alterar a saída.

Revise a coerência dos candidatos antes de usá-los como temas de avaliação: a
presença conjunta de entidades é uma regra objetiva de contagem, mas não garante
que o conjunto represente uma necessidade de informação coerente. A contagem é
uma estatística de prevalência, não substitui a curadoria dos artigos relevantes.

## Contar entidades em avaliações já concluídas

O total de artigos para entidades pode ser calculado depois que uma rodada do
Painel de avaliações termina. O cálculo usa o período salvo na rodada; para uma
rodada antiga sem período salvo, informe `date_range`. Informe URIs canônicas
quando disponíveis; valores sem URI são comparados ao texto armazenado da entidade
exatamente. Cada artigo conta uma vez e precisa corresponder a todas as entidades.

Para várias rodadas, crie um arquivo JSON:

```json
{
  "schema_version": 1,
  "runs": [
    {
      "run_id": "ID_DA_RODADA",
      "themes": {
        "banco_master": ["Banco Master"],
        "banco_master_fgc": ["Banco Master", "http://pt.dbpedia.org/resource/Fundo_Garantidor_de_Créditos"]
      }
    }
  ]
}
```

Execute `uv run python -m src --attach-theme-counts-file mapeamento.json`. Opcionalmente,
adicione `"date_range": {"from": "2025-06-01", "to": "2026-06-30"}` dentro de
um item de `runs` para substituir o período salvo. A rodada precisa estar concluída.
O arquivo pode conter vários itens `runs`.

No painel, abra uma rodada concluída e expanda **Contar artigos por entidades do
tema**. O painel mostra uma linha por tema (não por consulta); informe as entidades
separadas por vírgulas. A lista será aplicada uma vez ao tema, compartilhada por
todas as formulações de consulta. Também é possível carregar um arquivo de
mapeamento; o painel usa a entrada referente à rodada aberta. Revise as datas e
clique em **Calcular contagens**. O resultado é salvo como artefato da rodada e
pode ser consultado novamente ao reabri-la.

Este processo serve para montar uma avaliação de busca cujo objetivo é verificar
se o sistema encontra as **20 notícias do G1 mais úteis para informar uma pessoa
que pesquisou sobre um tema**. Faça a curadoria dos artigos antes de comparar os
rankings: a lista de referência não deve ser simplesmente o top 20 de um método
que será avaliado.

## 1. Fixe o tema e o período

Escreva uma frase curta que descreva uma necessidade de informação coerente. O
tema deve ser específico o bastante para que seja possível decidir se uma notícia
ajuda a informar o leitor, mas amplo o bastante para ter cobertura ao longo do
período. Evite juntar assuntos independentes em um único tema.

Use em todas as buscas da avaliação o período inclusivo:

- **De:** `2025-06-01`
- **Até:** `2026-06-30`

Considere a data de publicação da notícia. Não misture artigos de fora desse
intervalo para completar a lista. Se não existirem 20 notícias suficientemente
relevantes no período, use a quantidade encontrada e registre a limitação; não
inclua notícias irrelevantes só para chegar a 20.

Antes de procurar artigos, anote:

1. O que um leitor deveria entender depois de ler sobre o tema?
2. Quais eventos, pessoas, instituições, lugares ou consequências definem o
   assunto?
3. Quais subaspectos seriam importantes para uma explicação equilibrada?

Por exemplo, para uma crise financeira, os subaspectos podem incluir origem,
cronologia, investigação, liquidação, correntistas, impacto em instituições e
respostas oficiais. Adapte-os ao tema; não force categorias que não se aplicam.

## 2. Crie variantes de consulta

Use as oito formulações abaixo para cada tema. Elas devem expressar a **mesma
necessidade de informação**, variando a forma de perguntar — não o assunto ou o
período. Os nomes são valores literais de `query_formulation` e também devem ser
usados no sufixo do `id`.

| `query_formulation` | Como escrever | Exemplo: crise do Banco Master |
|---|---|---|
| `keyword` | Palavras-chave centrais, sem transformar a consulta em pergunta. | `Banco Master crise liquidação FGC` |
| `short_theme` | Tema em poucas palavras. | `crise do Banco Master` |
| `specific_keywords` | Termos específicos: atores, evento, instituição ou consequência. | `Banco Master liquidação Banco Central ressarcimento FGC` |
| `broad_theme` | Descrição natural e abrangente do assunto. | `crise no Banco Master e seus impactos` |
| `short_question` | Pergunta curta de orientação geral. | `O que aconteceu com o Banco Master?` |
| `specific_question` | Pergunta delimitada sobre um aspecto concreto. | `Como a liquidação do Banco Master afetou correntistas e investidores?` |
| `information_request` | Pedido para explicar o tema e seus principais aspectos. | `Explique a crise do Banco Master, as suspeitas de fraude, a liquidação e os impactos para correntistas.` |
| `baseline` | A pergunta original, sem reformulação. | `crise no Banco Master e seus impactos` |

Evite diferenças que mudem a intenção. Por exemplo, uma variante sobre a
investigação criminal e outra apenas sobre investimentos pessoais podem medir
necessidades distintas, não o efeito da formulação.

## 3. Encontre candidatos no corpus

Use a busca principal da interface para procurar notícias dentro do período
fixado. Pesquise com as variantes, sinônimos, nomes de pessoas e instituições,
nomes anteriores do assunto e termos usados nas notícias. Use um nível de busca
mais profundo durante a descoberta para ampliar o conjunto de candidatos; depois
revise os artigos individualmente.

A busca é uma ferramenta de descoberta, não um julgamento de relevância. Examine
o artigo completo — não apenas título, trecho ou posição no ranking — antes de
incluí-lo. A busca por título da aba **Avaliação** pode ajudar a localizar uma
URL conhecida no banco. O arquivo final só aceita URLs que existam em
`g1_articles`.

Para cada candidato, confirme:

- Foi publicado entre `2025-06-01` e `2026-06-30`, inclusive.
- É uma notícia do G1 pertinente ao tema definido.
- Seu conteúdo ajuda o leitor a entender o assunto, e não apenas menciona uma
  palavra-chave incidentalmente.
- A URL é a URL canônica da notícia e ainda corresponde a um artigo do banco.
- Não é uma duplicata exata de outra URL já escolhida.

## 4. Selecione e ordene até 20 artigos relevantes

Inclua notícias que contribuam de forma substantiva para informar sobre o tema:
por exemplo, explicadores, fatos centrais, cronologia, atores e instituições,
consequências, respostas ou desdobramentos importantes. Não é necessário cobrir
todas essas categorias quando elas não fizerem sentido para o tema.

Exclua menções incidentais, notícias sobre homônimos ou assuntos paralelos,
conteúdo que só compartilhe uma palavra-chave e versões duplicadas sem informação
adicional. Uma atualização posterior pode ser incluída quando acrescentar um
desdobramento relevante, não apenas por ser mais recente.

Escolha as **20 notícias que, em conjunto, melhor informariam o leitor** e
ordene-as da mais para a menos útil como referência editorial. Mantenha esse
mesmo conjunto e a mesma ordem em todas as variantes de consulta do tema. Isso
permite comparar formulações sobre uma referência comum, em vez de mudar a
definição de relevância a cada consulta.

No contrato atual, precisão, revocação e F1 usam a lista completa de URLs
relevantes como conjunto positivo em todos os valores de k. Portanto, a ordem da
lista não muda esses cálculos; ela é preservada como prioridade editorial e para
facilitar a revisão. O total de artigos relevantes — normalmente 20 — continua
sendo o denominador da revocação.

## 5. Monte o arquivo JSON

Crie um arquivo UTF-8 com `schema_version: 1`. Cada variante é uma avaliação
separada. O `id` combina um prefixo comum do tema com o nome exato da formulação,
separados por `__`. As URLs relevantes devem ser distintas e existir no banco.

Estrutura ilustrativa (use **todas as URLs selecionadas** em cada variante):

```json
{
  "schema_version": 1,
  "evaluations": [
    {
      "id": "banco_master__keyword",
      "query": "Banco Master crise liquidação FGC",
      "query_formulation": "keyword",
      "relevant_urls": [
        "https://g1.globo.com/economia/noticia/2025/11/18/noticia-exemplo-1.ghtml",
        "https://g1.globo.com/economia/noticia/2025/11/19/noticia-exemplo-2.ghtml"
      ]
    },
    {
      "id": "banco_master__short_question",
      "query": "O que aconteceu com o Banco Master?",
      "query_formulation": "short_question",
      "relevant_urls": [
        "https://g1.globo.com/economia/noticia/2025/11/18/noticia-exemplo-1.ghtml",
        "https://g1.globo.com/economia/noticia/2025/11/19/noticia-exemplo-2.ghtml"
      ]
    }
  ]
}
```

As duas URLs acima são somente exemplos de formato; substitua-as por URLs reais.
Repita a lista completa e idêntica de URLs nas oito variantes. Não inclua campos
extras. Os campos obrigatórios são `id`, `query` e `relevant_urls`; informe também
`query_formulation` para que os resultados possam ser agrupados por estilo.

## 6. Valide e execute

Use um nome de arquivo que identifique o conjunto e período, por exemplo
`evals_crise_bancaria_2025_2026.json`. A avaliação em lote valida o formato e
verifica se todas as URLs relevantes existem no banco antes de iniciar as
buscas. Para um piloto, limite preset e quorum e use `result_unit=articles`:

```bash
uv run python -m src \
  --evaluate-file evals_crise_bancaria_2025_2026.json \
  --output resultados/eval_crise_bancaria.json \
  --result-unit articles \
  --presets rapido \
  --quorums 0.3 0.7
```

Por padrão, são avaliados todos os rankings e métodos de seed. Para um teste
menor, restrinja-os com `--rankings` e `--seed-methods`; para remover métodos da
grade padrão, use `--exclude-rankings` e `--exclude-seed-methods`. A mesma grade
também pode ser iniciada e acompanhada na aba **Painel de avaliações**.

## Checklist antes de considerar o conjunto pronto

- [ ] O tema representa uma única necessidade de informação.
- [ ] Todas as buscas usam o período fixo, de 1º de junho de 2025 a 30 de junho
  de 2026.
- [ ] As variantes mudam a formulação, não o assunto pretendido.
- [ ] Cada URL foi aberta e julgada pelo conteúdo completo.
- [ ] Há até 20 artigos substantivamente relevantes; a lista não foi preenchida
  com resultados fracos apenas para atingir uma quantidade.
- [ ] As URLs são únicas, pertencem ao banco e estão na mesma ordem nas variantes.
- [ ] `id` e `query_formulation` correspondem à variante e são únicos/consistentes.
- [ ] Os resultados serão comparados com a mesma unidade, preset e quorum.
