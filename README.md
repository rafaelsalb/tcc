# Avaliações em lote

## Execução local com Docker Compose

O Compose inicia PostgreSQL com pgvector, Redis, Ollama (e baixa
`qwen3-embedding:0.6b`), DBpedia Spotlight com o modelo português, cria as tabelas
da aplicação e inicia a API. **Ele não importa o corpus G1**: carregue seu dump
depois que o schema estiver pronto.

Requisitos: Docker Engine com Compose v2 e espaço em disco para as imagens e o
modelo Ollama. Para começar:

```bash
cp .env.example .env
# Configure GEMINI_API_KEY se for usar sumarização Gemini.
docker compose up --build -d
docker compose ps
```

Na primeira execução, a inicialização pode levar alguns minutos enquanto imagens,
modelos e schema são preparados. A API fica em <http://localhost:5000>. O serviço
`api` só inicia depois de o schema existir e o modelo de embedding estar baixado.
Spotlight também baixa o modelo de português e pode levar um tempo para ficar
disponível.

Carregue então o dump de dados **compatível com as tabelas criadas**. Para um dump
SQL texto que contenha apenas dados:

```bash
docker compose exec -T postgres psql -U tcc_user -d tcc < /caminho/para/dump.sql
```

Para um arquivo custom-format do `pg_dump`, restaure apenas os dados (o schema já
foi criado pelo serviço `db-schema`):

```bash
docker compose exec -T postgres pg_restore --data-only --no-owner \
  -U tcc_user -d tcc < /caminho/para/dump.dump
```

Se os valores `POSTGRES_USER` ou `POSTGRES_DB` foram alterados no `.env`, use esses
valores nos comandos acima também. A senha definida em `POSTGRES_PASSWORD` é
usada pelo Compose para o banco; não publique as portas em redes não confiáveis
com as credenciais de desenvolvimento padrão.

Para acompanhar logs e parar sem apagar os dados:

```bash
docker compose logs -f api
docker compose down
```

**Não use `docker compose down -v`** se quiser preservar o banco, modelos e cache.
O schema é inicializado no volume novo pelo serviço `db-schema`; esse serviço é
idempotente e pode ser executado novamente sem remover os dados:

```bash
docker compose run --rm db-schema
```

### Executar a API no host, fora do container

As URLs da aplicação em `.env` usam `localhost` para conectar ao Postgres, Redis,
Ollama e Spotlight publicados pelo Compose. Copie `.env.example` para `.env`, suba
as dependências e inicialize o schema:

```bash
docker compose up -d postgres redis ollama-model dbpedia-spotlight
docker compose run --rm db-schema
uv run python src/api.py
```

Assim, a API roda no host enquanto as dependências continuam em containers. Para
a API dentro do Compose, os endpoints usam por padrão os nomes de serviço
(`postgres`, `redis`, `ollama` e `dbpedia-spotlight`); substitua-os via
`DOCKER_POSTGRES_DSN`, `DOCKER_REDIS_URL`, `DOCKER_OLLAMA_HOST` e
`DOCKER_SPOTLIGHT_ENDPOINT` no `.env`. As variáveis sem prefixo `DOCKER_` são
usadas pelo processo executado diretamente no host.

O banco não baixa/popula artigos automaticamente. Ollama, Postgres e Spotlight
mantêm seus dados em volumes Docker. A chave Gemini é necessária apenas para os
recursos que chamam Gemini.

### Executar comandos da aplicação no container

```bash
docker compose exec api uv run --no-sync python -m src --search "consulta"
docker compose exec api uv run --no-sync python -m src --populate-chunks
docker compose exec api uv run --no-sync python -m src --populate-embeddings
```

Os comandos de população são operações longas e devem ser executados um por vez.
Para carregar dump, prefira `psql`/`pg_restore` diretamente no serviço Postgres,
como nos exemplos anteriores.

O script executa buscas e calcula métricas para várias avaliações definidas em
um arquivo JSON. Ele usa o mesmo fluxo de busca e ordenação da aplicação web.

## Pré-requisitos

Configure o arquivo `.env` com `POSTGRES_DSN`, `OLLAMA_HOST` e
`GEMINI_API_KEY`. O banco Postgres, o servidor Ollama e os demais serviços
necessários à aplicação devem estar disponíveis. As URLs relevantes informadas
no arquivo precisam existir na tabela `g1_articles`.

Em um ambiente ainda não configurado, instale as dependências, o modelo spaCy
português usado pela extração de entidades e suba os serviços do projeto:

```bash
uv sync
uv pip install https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl
docker compose up -d
```

O Ollama também precisa estar acessível pelo `OLLAMA_HOST` e ter o modelo
`qwen3-embedding:0.6b` disponível.

## Arquivo de entrada

O arquivo deve ser um objeto JSON com `schema_version` igual a `1` e uma lista
não vazia de avaliações. Cada avaliação deve conter os campos obrigatórios
`id`, `query` e `relevant_urls`, e pode conter `query_formulation`:

```json
{
  "schema_version": 1,
  "evaluations": [
    {
      "id": "politica-01",
      "query": "investigações sobre corrupção",
      "query_formulation": "short_theme",
      "relevant_urls": [
        "https://g1.globo.com/estado/noticia/2025/01/01/materia-01.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/02/materia-02.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/03/materia-03.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/04/materia-04.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/05/materia-05.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/06/materia-06.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/07/materia-07.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/08/materia-08.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/09/materia-09.ghtml",
        "https://g1.globo.com/estado/noticia/2025/01/10/materia-10.ghtml"
      ]
    }
  ]
}
```

Substitua as URLs de exemplo por URLs reais e distintas que existam em
`g1_articles`. **Cada avaliação aceita qualquer quantidade positiva de URLs
relevantes e únicas, ordenadas da mais relevante para a menos relevante.** A
ordem fornecida é preservada e define a referência de cada corte k: somente as
primeiras k URLs contam como relevantes nesse corte. Se houver menos de k URLs,
toda a lista é usada. Os `id`s também devem ser únicos. Campos extras, listas
vazias, URLs inválidas, duplicadas ou ausentes do banco fazem a validação falhar
antes das buscas. O script não determina nem reordena a relevância editorial.
`query_formulation` é uma string não vazia que também aparece no CSV e JSON.
Quando ausente, vale `unspecified`; o método não é inferido do ID da avaliação.

Inicie a API em um terminal e mantenha-a em execução durante a avaliação:

```bash
uv run python src/api.py
```

Em outro terminal, execute:

```bash
uv run python -m src --evaluate-file avaliacoes.json
```

No modo padrão, o script chama `POST /evaluate` uma vez por combinação de
avaliação, nível e quorum. O servidor compartilha a recuperação para calcular
todos os rankings e métodos de seed desse grupo; todas as linhas de resultado
continuam sendo avaliadas e gravadas separadamente. Todos os cortes k são
calculados sobre a mesma resposta, sem buscas adicionais. Por padrão, usa
`http://localhost:5000`; para outra instância, informe `--api-url`:

```bash
uv run python -m src --evaluate-file avaliacoes.json --api-url http://servidor:5000
```

Por padrão, o comando cria `avaliacoes.results.jsonl` como checkpoint detalhado
incremental e `avaliacoes.results.csv` com o resumo atualizado após cada busca.
`avaliacoes.results.json` contém uma visão estruturada, gerada no início e ao
concluir, interromper ou falhar. Para escolher outro caminho para o JSON, use
`--output`; o CSV e o JSONL serão criados ao lado dele:

```bash
uv run python -m src --evaluate-file avaliacoes.json --output resultados/lote.json
```

O CSV usa **UTF-8 com BOM** para facilitar a detecção de acentos em planilhas
(por exemplo, `tarifaço`, `Benício` e `São Paulo`). Apenas o início do arquivo
contém BOM; gravações incrementais e retomadas não inserem marcadores adicionais.
Para ler em Python, use `encoding="utf-8-sig"`. JSON e JSONL continuam em UTF-8
sem BOM. Resultados existentes não foram modificados; CSVs reconstruídos numa
retomada explícita também passam a usar esse formato. Para abrir um CSV antigo
sem conversão, escolha UTF-8 na importação da planilha.

O diretório de saída precisa existir. Para **retomar sem perder progresso**, use
o mesmo arquivo de entrada e caminho de saída, acrescentando `--resume`:

```bash
uv run python -m src --evaluate-file avaliacoes.json --output resultados/lote.json --resume
```

Cada combinação de consulta, nível, método e quorum é persistida no JSONL com
checksum, `flush` e `fsync`. O CSV também é atualizado e sincronizado a cada
resultado. Com `--workers 1` (padrão), as requisições executam no thread principal.
Com `--workers N`, uma fila limitada submete no máximo N grupos/requisições
simultâneos; resultados terminados fora de ordem esperam para serem gravados na
ordem original. Somente resultados dos grupos em execução aguardam em memória
(no máximo N grupos); o histórico é lido em streaming. A função Python
`run_batch_evaluation` retorna somente um resumo, não o lote inteiro em RAM.

Use `--workers N` (inteiro entre 1 e 16) para limitar a concorrência. O padrão
conservador é 1; comece com 2 e aumente apenas após medir CPU, memória, conexões
do banco e latência. Ao interromper com vários workers, requisições já iniciadas
podem continuar no servidor, mas resultados não commitados serão executados de
novo ao retomar. A retomada aceita outro número de workers, pois a concorrência
não muda a identidade nem a ordem das tarefas.

- **Ctrl+C ou SIGTERM:** interrompem o agendamento e exportam a visão parcial;
  com vários workers, até N requisições já iniciadas podem continuar no servidor.
  Trabalhos commitados não são repetidos. O código de saída é 130 ou 143.
- **Falha da API:** preserva os resultados anteriores e interrompe o lote com
  código 1. Corrija a falha e retome com `--resume`.
- **Queda abrupta / SIGKILL:** o JSON estruturado pode estar desatualizado; o
  JSONL é a fonte de verdade. Na retomada, CSV e JSON são reconstruídos a partir
  dos registros confirmados, sem repetir buscas salvas. Uma última linha sem
  terminador é descartada como escrita incompleta. Corrupção em registros
  completos é recusada, não ignorada.
- A busca interrompida **sem resultado salvo** será refeita. Não há retomada no
  meio de uma chamada HTTP e o servidor pode continuar processando uma chamada
  cujo cliente foi interrompido.
- A retomada exige os mesmos IDs, consultas, ordem das URLs relevantes, API,
  configurações de busca e regras de métricas. Não misture versões do corpus ou
  da API: mudanças internas no servidor/banco não são detectadas pelo checkpoint.
- Um lock de arquivo impede dois processos de gravar a mesma saída. O arquivo
  `.json.lock` pode permanecer após terminar; o lock ativo é liberado pelo sistema
  ao fechar o processo. Esta persistência usa primitivas POSIX (Linux).
- `--overwrite` inicia do zero e substitui checkpoint e relatórios; nunca o use
  para retomar. É mutuamente exclusivo com `--resume`. Resultados antigos que
  tenham apenas JSON/CSV, sem checkpoint JSONL, não permitem retomada.

O terminal mostra progresso, configuração, tempo da busca e métricas após cada
resultado, além de `Elapsed: HH:MM:SS` e `Remaining: ~HH:MM:SS`. O tempo decorrido
é da sessão atual; a estimativa usa uma média móvel exponencial em memória,
separada por configuração de busca (preset, quorum, etapa/ranking, seed e unidade).
O ETA considera grupos restantes e o limite de workers; as linhas derivadas de uma
requisição compartilhada contam como uma só. Antes da primeira amostra aparece
`calculating`; ao concluir, `00:00:00`. Retomadas iniciam novas amostras de tempo,
sem contabilizar os grupos pulados nem o período em que o lote ficou parado. A
estimativa é aproximada e pode variar com cache, consulta e carga do sistema.
Para acompanhar o CSV em outro terminal, inclusive após retomadas:

```bash
tail -F resultados/lote.csv
```

### Resumo ao vivo

Cada linha salva também atualiza `resultados/lote.summary.md` (legível) e
`resultados/lote.summary.json` (estruturado), ao lado de `lote.json`/`lote.csv`.
O resumo lista **todos** os temas, estruturas de consulta, conjuntos de
parâmetros, rankings, métodos de seed e etapas, ordenados por média de F1@20.
Inclui precisão, revocação e F1 observados e oráculo em todos os cortes k,
além das contagens de linhas/consultas. O JSON inclui também a cobertura do pool
e o número de amostras de cada métrica. Valores ausentes não viram zeros.

```bash
watch -n 1 cat resultados/lote.summary.md
```

As médias usam as linhas já salvas, incluindo variantes de seed repetidas na
grade para rankings que não usam seed. A classificação de seeds, especificamente,
usa apenas PPR/fusão/MMR; a de etapas usa apenas linhas de comparação de etapas.
O tema é o prefixo do ID antes de `__` (ou o ID inteiro, se não houver separador).
As médias são descritivas: durante o lote há coberturas diferentes e as
formulações de um tema não são observações independentes. P/R/F1 e oráculos usam
a lista completa e fixa `relevant_urls` como conjunto relevante em todos os k.

Os agregados são atualizados em memória, sem reler o histórico a cada linha nem
fazer novas buscas. Os arquivos são substituídos atomicamente para evitar leituras
parciais. Em `--resume`, o resumo é reconstruído uma vez a partir do JSONL, mesmo
se os arquivos de resumo tiverem sido removidos. Uma execução já em andamento
precisa ser reiniciada com as mesmas opções e `--resume` para usar o novo código.

### Comparação de formulações de consulta

`evals_curated_query_variants_stages_2025_2026.json` contém **40 avaliações**: oito
formulações para cada um dos cinco temas curados, sempre com as mesmas 20 URLs
na mesma ordem de relevância, com `query_formulation` explícito. São 30.720 linhas
no modo padrão atual, ou 480 grupos HTTP. Os IDs
terminam em `__keyword`, `__short_theme`, `__specific_keywords`, `__broad_theme`,
`__short_question`, `__specific_question`, `__information_request` e `__baseline`.
Os temas são intercalados por estilo para que as primeiras buscas já mostrem
consultas curtas de todos os temas; a baseline conserva a pergunta original.

```bash
uv run python -m src --evaluate-file evals_curated_query_variants_stages_2025_2026.json
# Depois de uma interrupção, execute o mesmo comando com --resume:
uv run python -m src --evaluate-file evals_curated_query_variants_stages_2025_2026.json --resume
```

Sem opções de restrição, esse comando executa todos os rankings registrados em
`--rankings` com os quatro métodos de seed (`louvain`, `hits`, `ppr_top10` e
`query_entities`). No código atual, são 16 rankings × 4 seeds = 64 combinações
por avaliação, preset e quorum. Para os valores padrão (40 avaliações, três
presets e quatro quorums), são 30.720 linhas/resultados. Rankings que não usam
seed continuam registrados para cada seed por comparabilidade da grade; seus
resultados devem ser idênticos entre seeds.

Para executar apenas parte da grade, use `--rankings`, `--seed-methods`,
`--presets` ou `--quorums`. Por exemplo:

```bash
uv run python -m src \
  --evaluate-file evals_curated_query_variants_stages_2025_2026.json \
  --rankings ppr fused mmr \
  --seed-methods louvain ppr_top10 \
  --presets rapido balanceado \
  --quorums 0.3 0.7 \
  --output resultados/eval_restrito.json
```

Para avaliar somente a meta-fusão, os três componentes por seed configurado são
calculados na mesma pool compartilhada:

```bash
uv run python -m src \
  --evaluate-file evals_definitive_2025_2026.json \
  --rankings ensemble_rrf \
  --ensemble-rankings rrf cross_encoder ppr \
  --seed-methods query_entities \
  --result-unit articles \
  --output resultados/eval_ensemble_rrf.json
```

Use novas saídas para comparar listas de componentes; a configuração compõe o
fingerprint do checkpoint.

O lote padrão não inclui as linhas de comparação lexical/híbrida. Para adicioná-las
na mesma execução, acrescente `--compare-stages`; nesse caso, dez linhas de
comparação de etapas (duas baselines e PPR/fusão para cada um dos quatro seeds)
são adicionadas às 64 linhas de ranking por avaliação, preset e quorum. Com os
defaults completos, isso produz 35.520 linhas (`74 × 40 × 3 × 4`).

### Seed pelas entidades da consulta

`query_entities` roda spaCy NER sobre a consulta e usa as entidades PER/ORG/LOC
para iniciar o PPR. O matching tenta primeiro a URI DBpedia canônica e, quando
não há uma URI compatível, a superfície normalizada. Só entidades ligadas aos
artigos do pool atual podem orientar a caminhada; não se adicionam nós isolados.

- Se a entidade está no grafo após k-core, ela é usada como seed.
- Se está nas menções antes da poda, mas foi removida do core, os artigos
  conectados a ela que sobreviveram ao core tornam-se seeds.
- Se a consulta não produz entidades utilizáveis ou não encontra suporte no
  pool, usa-se o fallback configurável, padrão `hits`.

O resultado inclui `query_entity_count`, `query_entity_matched_count`,
`query_seed_type`, `effective_seed_method` e `query_seed_fallback_reason`. Assim,
é possível separar seed direto, fallback para artigos e fallback para método
tradicional. Com `--compare-stages`, `query_entities` também é testado junto aos
outros seeds. Para escolher outro fallback:

```bash
--seed-methods query_entities --query-seed-fallback louvain
```

É um método experimental: reporte também a taxa de match e fallback; NER/Spotlight
podem não detectar entidades ou vinculá-las a uma URI compartilhada. Consulte
`casos_teste_relevancia_2025_2026.md` e mantenha a mesma pool ao comparar seeds.

Para gerar uma cópia reproduzível com outro nome, sem substituir os arquivos
existentes:

```bash
uv run python scripts/build_query_variants.py --output outras_variantes.json
```

Compare variantes dentro do mesmo tema e configuração. As versões mais amplas
podem ser ambíguas: menor desempenho também pode indicar mudança de intenção,
não só efeito do tamanho da consulta. Este conjunto explora formulações; não é
um experimento que isola perfeitamente cada variável. Documente também o estado
dos caches, modelos, dados e código da API ao comparar execuções.

O arquivo anterior `evals_curated_query_variants_2025_2026.json` e seus resultados
não foram substituídos. Use a nova versão para obter a coluna de formulação;
inputs antigos continuam válidos, com `unspecified` nessa coluna.

## Experimento por etapas e número de artigos

**Reinicie a API com o código atualizado e use um novo caminho de saída.**
Os checkpoints anteriores usam outra configuração/contrato de API e não devem
ser retomados com este experimento. Seus arquivos antigos permanecem intactos.
O contrato de busca agora é `stages_v8`, com namespace de cache `v18`; a versão
do contrato também faz parte da chave. Entradas anteriores não são apagadas nem
reutilizadas. A correção lexical preserva os lexemas normalizados em filtros e
scores, sem aplicar o stemmer português duas vezes (por exemplo, `beníci` não
deve virar `beníc`). Use uma nova saída para não misturar métricas antigas e
corrigidas; checkpoints de versões anteriores são recusados na retomada.

Para comparar os três valores de `top_k` com `limit=1000` fixo e dois valores de quorum:

```bash
uv run python -m src \
  --evaluate-file evals_curated_query_variants_stages_2025_2026.json \
  --compare-stages --result-unit articles \
  --quorums 0.3 0.7 \
  --output resultados/eval_stages_presets.json
```

São **240 grupos de busca e 17.760 linhas CSV** para as 40 consultas (10 resultados
de comparação de etapas e 64 combinações de ranking/seed por grupo). Para retomar,
repita exatamente as mesmas opções e acrescente `--resume`. Também existe
`--seed-methods louvain hits ppr_top10 query_entities` para restringir os métodos;
sem opções de restrição, todos os presets, quorums e quatro métodos são usados.

### Referência rápida: rankings e métodos de seed

Há duas escolhas diferentes: **ranking** decide como ordenar o pool recuperado;
**seed** escolhe os nós iniciais usados pelos métodos de grafo. Os identificadores
abaixo são os nomes aceitos pelo CLI/API, salvo onde indicado.

#### Rankings

| Identificador | O que faz | Usa seed/grafo? |
| --- | --- | --- |
| `ppr` | Ordena os artigos pelo Personalized PageRank (PPR) no grafo artigo–entidade. É o ranking padrão; na busca interativa use `stage=ppr` (sem `ranking=`). | Sim |
| `hybrid_max` | Mantém a ordenação híbrida recuperada: melhor score de chunk por artigo. | Não |
| `rrf` | Combina por Reciprocal Rank Fusion (RRF) as listas lexical e vetorial, restrita aos artigos elegíveis do pool híbrido. | Não |
| `lexical` | Usa o rank lexical dentro do pool híbrido retornado. Diferente de `stage=lexical`, que pode gerar outro pool. | Não |
| `vector` | Usa o rank vetorial dentro do pool híbrido retornado. | Não |
| `ensemble_rrf` | Combina múltiplas listas por RRF de peso igual; default `rrf`, `cross_encoder`, `ppr`. Configure com `ensemble_rankings`. | Conforme componentes |
| `cross_encoder` | Reordena até os primeiros 250 artigos híbridos usando um cross-encoder sobre consulta e primeiro chunk retornado do artigo. Carrega o modelo sob demanda. | Não |
| `fused` | Combina por RRF (peso igual) o ranking híbrido e o ranking PPR. | Sim (PPR) |
| `mmr` | Usa scores PPR com uma passagem greedy de diversidade: penaliza artigos que compartilham muitas entidades com artigos já escolhidos. | Sim (PPR) |
| `graph_rwr` | Random walk with restart no grafo, personalizado pelos seeds. | Sim |
| `graph_hits` | HITS condicionado aos seeds; artigos recebem autoridade em relação às entidades de seed. | Sim |
| `graph_salsa` | Propagação SALSA alternada entre entidades e artigos, com reinício nos seeds. | Sim |
| `graph_path` | Evidência por caminhos curtos: recompensa artigos-seed e artigos ligados a eles por entidades compartilhadas, com decaimento. | Sim |
| `graph_walk` | Propagação limitada de artigos-seed a entidades relacionadas e de volta a artigos, com `graph_hop_decay`. | Sim |
| `graph_fusion` | Combina por RRF o ranking híbrido e `graph_hits` query-conditioned (`rrf_k=60`). | Sim |
| `graph_hits_cross_encoder` | Aplica cross-encoder aos primeiros 250 artigos, converte logits em pesos sigmoid e executa HITS ponderado sobre arestas dos artigos para entidades da consulta. O restante do pool híbrido conserva a ordem original. | Sim |

`graph_hits_cross_encoder` usa somente entidades PER/ORG/LOC reconhecidas na
consulta; as demais entidades não entram na matriz de HITS. Se não houver arestas
entre uma entidade da consulta e os 250 artigos avaliados, usa como fallback o
`seed_method` selecionado. Os diagnósticos informam a quantidade de chunks
reranqueados, documentos ausentes, entidades casadas e motivo do fallback.

`ppr` também aparece como opção em `--rankings` e nos arquivos de avaliação em
lote. Já os rankings `graph_*` aceitam `ranking=<identificador>` na busca
interativa e na avaliação em lote. `fused` é fusão por RRF entre híbrido e PPR;
`graph_fusion` funde híbrido com `graph_hits`; `ensemble_rrf` combina os métodos
configurados. Os rankings sem
seed (`hybrid_max`, `rrf`, `cross_encoder`) podem aparecer repetidos por seed em
uma grade de avaliação para manter a grade comparável; o cálculo não depende da
seed. `ensemble_rrf` depende da seed porque seu componente `ppr` usa o método
selecionado.

As etapas da API não são todas nomes de ranking: `stage=lexical` retorna a
baseline lexical, `stage=hybrid` retorna o ranking híbrido, `stage=ppr` executa
PPR (ou o ranking selecionado por `ranking=`), `stage=fused` combina híbrido e
PPR, e `stage=compare` devolve baselines lexical/híbrida mais PPR e fusão para
cada seed solicitada.

#### Métodos de seed

| Identificador | Seleção dos seeds para PPR/grafo |
| --- | --- |
| `hits` | Calcula HITS no grafo direcionado artigo → entidade e seleciona as entidades com maior authority score. O número selecionado é controlado por `seed_ratio` no serviço (padrão `1.0`). |
| `louvain` | Agrupa entidades em comunidades Louvain e seleciona até três entidades mais conectadas a artigos por comunidade; comunidades pequenas podem ser filtradas. |
| `ppr_top10` | Faz PageRank inicial sem personalização, divide o score de cada entidade pela raiz do número de artigos conectados e seleciona as 10% entidades mais bem pontuadas (arredondado para cima). Não usa HITS. |
| `query_entities` | Extrai entidades PER/ORG/LOC da consulta e usa as que correspondem ao grafo atual. Tenta URI DBpedia canônica e depois superfície normalizada; se a entidade foi removida pelo k-core, pode usar os artigos conectados sobreviventes. |

`query_entities` é o único método que precisa da consulta como seed e pode não
encontrar entidade correspondente. Nesse caso usa `query_seed_fallback`, cujo
padrão é `hits`; opções válidas: `hits`, `louvain` e `ppr_top10`. A métrica
`effective_seed_method` e os diagnósticos `query_seed_fallback_reason` e
`query_seed_type` mostram o que foi efetivamente usado. NER usa o modelo spaCy
português; o vínculo DBpedia é opcional e pode degradar para correspondência por
texto.

Os quatro nomes estão definidos em `SEED_METHODS` em
`src/services/search_pipeline.py`; os rankings são definidos em `RANKINGS` nesse
módulo e em `src/services/batch_search.py`. A implementação PPR/seeds e os nomes
internos dos algoritmos de grafo ficam em `src/services/ranking.py`.

Para ver ou restringir os métodos numa avaliação:

```bash
uv run python -m src --help
uv run python -m src --evaluate-file avaliacoes.json \
  --rankings ppr fused mmr graph_rwr graph_salsa \
  --seed-methods hits query_entities \
  --query-seed-fallback louvain
```

Exemplo para a API interativa:

```text
/search?query=Banco%20Master&stage=ppr&ranking=graph_fusion&seed_method=query_entities&query_seed_fallback=hits
```

### Etapas na API

### Avaliação em lote com reutilização e benchmark

O CLI usa, por padrão, **`POST /evaluate`**: uma recuperação nova por combinação
de consulta/preset/quorum/unidade, compartilhada entre os rankings. O grafo é
construído uma vez; PPR é calculado uma vez por método de seed e reutilizado em
PPR, fusão e MMR. Rankings sem seed (`hybrid_max`, `rrf`, `cross_encoder`) são
calculados uma vez, mas todas as linhas da grade continuam sendo gravadas.
O reranker continua limitado aos primeiros 250 artigos do pool.

O estado reutilizado existe somente durante a requisição: não usa o Redis e não
é compartilhado com buscas da interface. O endpoint **`GET /search` não muda**.
Reinicie a API antes de usar o CLI atualizado e escolha uma nova saída: os
checkpoints antigos não correspondem ao novo modo de execução.

Por padrão, o lote usa um worker. `--workers N` limita quantos grupos de
recuperação podem estar ativos simultaneamente (1–16); apenas até N grupos são
submetidos, sem fila ilimitada. Cada worker faz uma chamada HTTP `/evaluate`;
um grupo reutilizado continua gerando todas as linhas próprias. Um único thread
principal grava checkpoint, CSV e resumo em ordem determinística. Portanto,
respostas que terminam fora de ordem ficam em memória apenas até os grupos
anteriores serem gravados; no máximo N grupos ficam ativos ou aguardando gravação.

Retomadas podem usar outro `--workers`: o limite de concorrência não altera a
identidade das tarefas. Ao interromper, até N chamadas já iniciadas podem ainda
terminar no servidor, mas só resultados em ordem commitados no checkpoint são
considerados salvos; chamadas sem commit podem ser repetidas no `--resume`.
Comece com 2 workers e aumente gradualmente, observando CPU, conexões PostgreSQL,
memória e latência. Concorrência não garante aceleração se o servidor ou o banco
for o gargalo. Evite usar `--benchmark` com vários workers para comparar tempos:
a baseline repetida acrescenta carga e pode competir com o caminho otimizado.

```bash
uv run python -m src \
  --evaluate-file evals_curated_query_variants_stages_2025_2026.json \
  --result-unit articles \
  --workers 2 \
  --output resultados/eval_reuse.json
```

Para medir o ganho, prepare `amostra.json` no mesmo formato de avaliação, com uma
ou poucas consultas representativas, e execute:

```bash
uv run python -m src \
  --evaluate-file amostra.json \
  --result-unit articles --presets rapido --quorums 0.7 \
  --benchmark --output resultados/benchmark_reuse.json
```

`--benchmark` executa o caminho otimizado e depois uma baseline independente
(uma recuperação e ordenação novas por linha de saída). **Isso adiciona trabalho;
não habilite no lote completo só para acelerá-lo.** O relatório `performance`
inclui tempos de recuperação, grafo, PPR, MMR e reranker, contagens de operações,
`speedup = baseline.wall_seconds / optimized.wall_seconds` e `equivalent`.
A equivalência exige a mesma ordem de URLs e scores próximos (tolerância relativa
`1e-6`, absoluta `1e-8`); o CLI recusa salvar um grupo divergente.

A baseline mede a grade independente, não o agrupamento legado de `compare`.
Os tempos são do servidor e não incluem transporte HTTP nem persistência do CLI.
A primeira requisição pode incluir carregamento do modelo; repita a amostra para
avaliar o regime aquecido, mantendo CPU/threads constantes. Alterações do corpus
ou de entidades entre as duas execuções também podem causar divergências.

O JSON/JSONL guarda `performance` em cada resultado. O CSV inclui `mode`,
`computation_reused` (reutilização da saída completa), `group_wall_seconds`,
`baseline_wall_seconds`, `speedup`, `benchmark_equivalent`, `retrieval_calls`,
`graph_builds` e `ppr_runs`. Tempos/contagens do grupo se repetem nas linhas:
**conte uma vez por avaliação/preset/quorum**, não some todas as linhas. O
`elapsed_seconds` também representa a requisição compartilhada, não o custo
isolado de um ranking. O ETA aprende uma duração por requisição do grupo.

Rankings adicionais de grafo: `graph_rwr` (random walk com reinício),
`graph_hits` (HITS condicionado às entidades seed), `graph_salsa`, `graph_path`
(evidência por caminhos curtos), `graph_walk` (propagação limitada) e
`graph_fusion` (RRF entre híbrido e `graph_hits`). Todos usam o mesmo pool de
artigos. Os parâmetros opcionais são `graph_alpha` (padrão `0.85`, intervalo
aberto `(0,1)`) e `graph_hop_decay` (padrão `0.5`, intervalo `[0,1]`);
`graph_mix` permanece aceito por compatibilidade, mas não é usado por
`graph_fusion` desde que passou a usar RRF (`rrf_k=60`).
Exemplo:

```text
/search?query=Banco%20Master&result_unit=articles&ranking=graph_fusion&seed_method=hits
```

Piloto rápido com as 16 consultas de diagnóstico, um preset/quorum/seed e
comparação com baselines (os parâmetros de grafo usam os defaults):

```bash
uv run python -m src --evaluate-file evals_retrieval_diagnostic_pilot.json \\
  --output resultados/graph_ranking_pilot.json --result-unit articles \\
  --presets rapido --quorums 0.3 --seed-methods hits \\
  --rankings ppr hybrid_max rrf fused graph_rwr graph_hits graph_salsa graph_path graph_walk graph_fusion
```

Depois do piloto, rode o conjunto definitivo apenas nos métodos promissores.

Use `--no-reuse` para voltar às requisições legadas de `/search` (em uma saída
separada). Não combine essa opção com `--benchmark`.

Exemplo direto do novo endpoint:

```json
{
  "search": {"query": "Banco Master", "limit": 250, "top_k": 100, "quorum": 0.7, "result_unit": "articles"},
  "configurations": [
    {"mode": "ranking", "stage": "ppr", "ranking": "ppr", "seed_method": "hits"},
    {"mode": "ranking", "stage": "ppr", "ranking": "fused", "seed_method": "hits"},
    {"mode": "ranking", "stage": "ppr", "ranking": "mmr", "seed_method": "hits"}
  ],
  "benchmark": false
}
```

### Parâmetros da busca interativa

`GET /search` aceita `stage=lexical|hybrid|ppr|fused|compare`,
`result_unit=chunks|articles` e `candidate_cap` (padrão 20.000 chunks candidatos).
Os defaults continuam `stage=ppr`, `result_unit=chunks`, `seed_method=hits`.

Além das etapas, `ranking=` seleciona diretamente uma ordenação sobre o mesmo
pool. Inclui as listas individuais `lexical` e `vector`, `rrf`, `cross_encoder`,
`hybrid_max`, PPR, `fused`, `mmr`, rankings `graph_*` e `ensemble_rrf`. O ranking
padrão permanece o fluxo PPR existente. A configuração da ensemble também faz
parte da chave de resposta Redis.

`rrf` agrega, por artigo, o melhor rank de chunk em cada canal dentro do pool
lexical com embedding elegível; rank 1 é o melhor. Só então funde as listas
lexical e vetorial, restringindo o resultado ao pool híbrido retornado. Mudanças
nesse cálculo usam `search_version=stages_v8`/namespace `v18`; reinicie a API
para evitar comparar resultados servidos por um processo antigo.

`ranking=ensemble_rrf` combina por soma RRF de peso igual os rankings-fonte
configurados, usando o mesmo pool híbrido. O padrão é `rrf,cross_encoder,ppr`;
`ensemble_rankings` permite selecionar, por exemplo, canais individuais ou um
seed PPR específico:

```text
/search?query=Banco%20Master&result_unit=articles&ranking=ensemble_rrf&seed_method=query_entities&ensemble_rankings=rrf,cross_encoder,ppr
```

Fontes permitidas incluem rankings lexicais/vetoriais, rerankers e métodos de
grafo, mas não `ensemble_rrf` recursivo. Métodos ausentes não são substituídos
por híbrido; somente artigos ranqueados pelos componentes e presentes no pool
híbrido participam da fusão. RRF usa ranks, não compara escalas de scores.

`ranking=cross_encoder` reranqueia somente os primeiros 250 artigos candidatos,
usando o primeiro chunk retornado de cada artigo como texto do documento no par
consulta–chunk. O chunk é truncado ao orçamento de tokens restante do contexto,
depois de contabilizar consulta e tokens especiais do par; a truncagem do
tokenizer do modelo continua como proteção final. O
modelo padrão é `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`; ele pode ser
substituído por `CROSS_ENCODER_MODEL` e é carregado sob demanda. Exige
`sentence-transformers` disponível no ambiente. Se o modelo/dependência não
estiver disponível, a API retorna erro explícito; os demais rankings não dependem
dele. As opções `llm` e `story_stage` não são implementadas.

| Etapa | Comportamento |
| --- | --- |
| `lexical` | Apenas matching lexical/quorum e `ts_rank`; não gera embedding da consulta nem extrai entidades |
| `hybrid` | RRF entre posições vetorial e textual; sem processamento de grafo |
| `ppr` | PPR normalizado no grafo, com `seed_method` selecionado |
| `fused` | RRF de peso igual entre ranking híbrido de artigos e ranking PPR (`rrf_k=60`) |
| `compare` | Uma recuperação híbrida, baseline lexical e híbrida, mais PPR e fusão para cada seed selecionada |

```text
/search?query=Banco%20Master&top_k=100&result_unit=articles&stage=hybrid
/search?query=Banco%20Master&top_k=100&result_unit=articles&stage=ppr&seed_method=ppr_top10
/search?query=Banco%20Master&top_k=100&result_unit=articles&stage=compare&seed_methods=louvain,hits,ppr_top10
```

Sem bypass, a recuperação é cacheada separadamente da ordenação, sem depender da seed. No
modo `compare`, híbrido, PPR e fusão têm **exatamente os mesmos artigos** e o
mesmo `retrieval_id`. O avaliador recusa respostas que violem esse contrato.
A baseline lexical seleciona seu próprio conjunto por score textual e tem
identificador distinto: sua comparação com o híbrido também envolve mudança de
candidatos, não apenas de ordem. `ts_rank` é uma aproximação textual, não BM25
completo. O filtro lexical continua sendo pré-requisito da busca híbrida; esta
mudança não adiciona uma recuperação vetorial independente para contorná-lo.

### Cache-bypass

`bypass_cache=true` (ou `1`) ignora **leituras e gravações** do cache Redis, tanto
da recuperação quanto da resposta final. A consulta e a ordenação são
recalculadas, sem substituir entradas já existentes. O padrão da API continua
com cache (`false` ou `0`). Valores inválidos são recusados. A resposta confirma
a política com `cache_bypassed: true|false`.

```text
/search?query=Ben%C3%ADcio%20adrenalina&stage=compare&result_unit=articles&bypass_cache=true
```

**Toda avaliação em lote envia `bypass_cache=true` automaticamente**, nos modos
padrão e compare, sem flag adicional. O cliente recusa uma resposta se a API não
confirmar o bypass e registra a política no JSON, CSV (`cache_bypassed`) e
fingerprint do checkpoint. Assim, uma API antiga não pode ignorar a opção
silenciosamente. Reinicie a API antes de usar o avaliador atualizado.

O bypass não desativa caches internos do PostgreSQL, sistema operacional ou
Ollama; tempos ainda podem melhorar com aquecimento. Um `retrieval_id` igual
continua sendo possível quando uma recuperação nova produz os mesmos artigos
e scores. No modo compare, os métodos continuam compartilhando o pool calculado
uma única vez dentro daquela chamada, sem precisar reutilizar cache Redis.

### top_k em artigos

Com `result_unit=articles`, todos os chunks **elegíveis no pool limitado por
candidate_cap** recebem score antes da seleção. O SQL agrupa por URL, usa o maior
score de chunk por artigo, seleciona os top_k artigos e retorna o melhor chunk
representante de cada um. Não soma scores de chunks, nem limita um prefixo de
chunks esperando obter a quantidade desejada de artigos. Portanto, top_k=100
significa até 100 URLs distintas, se disponíveis. Offset também conta artigos.
Não é necessário retornar todos os chunks dos artigos escolhidos: o grafo usa
as URLs e seus corpos. Em modo `chunks`, mantém-se a janela por chunks.

### ppr_top10

Após o k-core existente, calcula-se um PageRank inicial sem personalização.
Cada score é dividido por `sqrt(número de vizinhos opostos)`. **Apenas entidades**
participam da seleção dos `ceil(0.10 × número_de_entidades)` maiores scores,
com desempate pela identidade do nó. Os selecionados recebem pesos iguais que
somam 1; todos os outros nós, inclusive artigos, recebem 0. Executa-se então o
PPR final, mantendo a normalização por raiz do grau. Este método não utiliza
HITS para escolher a seed. `hits` e `louvain` continuam disponíveis.
Se não houver entidades sobreviventes, usa-se fallback uniforme nos artigos e
isso aparece em `seed_fallback`. A interface web também oferece o novo método.

### Leitura dos diagnósticos

Além de P/R/F1 e métricas oráculo, o CSV inclui `mrr@20`, `map@5`, `map@10`,
`map@20`, `ndcg@5`, `ndcg@10`, `ndcg@20`, `stage`, `result_unit`,
`query_formulation`, `retrieval_id`, contagens de chunks/artigos/entidades e:

- `mrr@20`: recíproco do rank do primeiro artigo relevante nos 20 primeiros.
- `map@k`: média da precisão em cada rank relevante até k, normalizada por
  `min(k, quantidade de referências relevantes)`.
- `ndcg@k`: ganho descontado e normalizado com relevância binária; usa todas as
  URLs relevantes, sem depender de sua ordem no arquivo de entrada.

P/R/F1@k, MRR/MAP/NDCG e oráculos usam o conjunto completo de URLs relevantes.
O objeto `ranking_metrics` está presente nos resultados JSON e o resumo ao vivo
agrega essas métricas por configuração e ranking.

- `lexical_reference_in_pool`: referências presentes no pool lexical **após o
  cap**, antes da janela top_k; `hybrid_eligible_reference_in_pool` exige ao menos
  um chunk com embedding nesse pool.
- `reference_in_pool` e `reference_pool_recall`: cobertura da lista relevante
  completa entre os artigos retornados pela etapa, em qualquer posição.
- `oracle_precision@k`, `oracle_recall@k`, `oracle_f1@k`: melhor valor possível
  se os artigos relevantes já presentes fossem reordenados perfeitamente, usando
  como denominador de recall a lista completa de URLs relevantes. A distância até a métrica real mede espaço
  de melhoria da ordenação; um teto baixo aponta perda na recuperação.
- `effective_quorum`: quantidade de lexemas exigida; quorums diferentes podem
  ter o mesmo efeito em consultas curtas.
- `candidate_cap_hit`: o pool atingiu o limite de candidatos; as contagens não
  representam todos os chunks elegíveis do corpus.
- `graph_surviving_articles`, `entity_count`, `ppr_seed_count`, `seed_fallback`:
  efeito do pruning e da seleção de seeds. Campos de grafo ficam vazios nas
  baselines sem grafo. Os diagnósticos completos são obtidos em `--compare-stages`.
- `query_entities` também registra entidades extraídas/mapeadas, tipo de seed,
  método efetivo e motivo do fallback.

O banco é lido em uma transação repeatable-read durante a recuperação para que
contagens e baselines usem o mesmo snapshot. O cap lexical tem desempate por ID
para não trocar candidatos arbitrariamente entre as consultas de diagnóstico.

### Persistência de comparações

Cada chamada `compare` produz dez resultados com os quatro métodos: uma baseline
lexical, uma híbrida e quatro pares PPR/fusão. Cada etapa/método é salva como um
registro independente no JSONL e no CSV, com seu próprio `stage`, `ranking` e
`seed_method`. A requisição HTTP continua sendo compartilhada entre os dez
registros para manter o mesmo pool de recuperação. `completed_results`,
`total_results` e `total_comparison_rows` contam registros individuais; ao retomar,
somente os registros ausentes são gravados, embora o grupo HTTP incompleto possa
ser consultado novamente. `elapsed_seconds` é o tempo da consulta compartilhada
e pode se repetir nos dez registros. Em RAM fica somente o grupo corrente.

A avaliação não transforma URLs fora da referência em julgamentos humanos
negativos ou positivos. A revisão independente de artigos alternativos continua
necessária para medir relevância além da lista editorial curada.

## Configuração usada

O script e a interface usam os mesmos três níveis. `limit` fica fixo em 1000;
somente `top_k` varia:

| Nível | `limit` (configuração HNSW) | `top_k` (chunks ou artigos, conforme unidade) |
|---|---:|---:|
| Rápido | 1000 | 250 |
| Balanceado | 1000 | 500 |
| Profundo | 1000 | 1000 |

São três pools com `limit` constante. Sem `--presets`, o lote executa os três.
`--presets rapido` restringe a execução ao primeiro tamanho; para testar todos, omita
essa restrição ou informe `--presets rapido balanceado profundo`.
Mudanças dos valores alteram o fingerprint: inicie uma nova saída, sem retomar
checkpoints gerados com os valores anteriores.

Cada nível é executado com **Louvain**, **HITS**, **ppr_top10** e **query_entities**, e com quorum
`0.3`, `0.5`, `0.7` e `0.9`. Todas as buscas usam o filtro
de publicação de **1º de junho de 2025 a 30 de junho de 2026**, inclusive. O banco
atualmente contém artigos até 20 de maio de 2026, portanto não há registros para
o restante do período.

O batch executa, por padrão, os rankings `ppr`, `hybrid_max`, `rrf`,
`cross_encoder`, `fused`, `mmr`, os sete rankings `graph_*`, os canais individuais
`lexical`/`vector` e `ensemble_rrf`. Use `--rankings` para restringi-los. Com
`--compare-stages`, dez linhas de comparação de etapas são adicionadas às linhas
desses rankings na mesma execução. `ensemble_rrf` usa por padrão `rrf`,
`cross_encoder` e `ppr`; `--ensemble-rankings` troca os componentes.

O resumo apresenta **Precisão@k, Revocação@k e F1@k para k = 1, 3, 5, 10 e 20**,
em 15 colunas: `precision@1`, `recall@1`, `f1@1`, …, `precision@20`, `recall@20`,
`f1@20`. As URLs recuperadas são deduplicadas, preservando a ordem, antes dos
cortes. Para cada k:

- A referência positiva é a lista completa `relevant_urls` para todo k.
- Acertos são as URLs dessa lista em comum com as primeiras k URLs distintas
  recuperadas.
- Precisão@k divide acertos por k, mesmo quando há menos resultados ou menos
  URLs de referência; posições não preenchidas não geram acertos.
- Revocação@k divide acertos pelo total fixo de artigos relevantes,
  `len(relevant_urls)`, em todo k.
- F1@k é a média harmônica de precisão e revocação; é zero se não houver acertos.

Por exemplo, com referência `[A, B, C, D, E]` e recuperação `[E, A, C]`, em k=3
há três acertos: precisão é 1 e recall é 3/5. Em k=1, E conta como relevante,
embora apareça depois na ordem editorial; recall é 1/5. Com dois artigos
relevantes, ambos recuperados em k=5, precisão é 2/5, recall é 1 e F1 é 4/7.
Assim, estas métricas avaliam recuperação contra uma referência fixa, cuja ordem
editorial não altera o conjunto positivo. A lista não é necessariamente exaustiva
de todos os artigos relevantes do corpus. Não são incluídos HITS@k nem média de
PPR. Estas métricas e oráculos são da avaliação em lote. O endpoint
`POST /metrics` da interface mantém sua semântica anterior e não é usado pelo lote.

O JSON detalhado inclui a lista relevante completa e ordenada, `ks`, a política
`relevance_reference: "all_relevant_urls_fixed"` e os resultados separados por
nível de busca, método de tópicos e quorum. Cada métrica contém seu k e seu
`relevant_total` efetivo; o `relevant_total` externo às métricas e a coluna de
mesmo nome no CSV continuam indicando o tamanho da lista completa. O CSV contém
uma linha por avaliação, ranking, seed, preset e quorum (768 por avaliação no modo
padrão; com `--compare-stages`, são 888 por avaliação). Checkpoints gerados com
a antiga regra de prefixo têm fingerprint de métricas incompatível: use uma nova
saída para a regra fixa e não os retome como se fossem métricas equivalentes.

> **Atenção:** a etapa de ordenação pode extrair e armazenar entidades que ainda
> não existam no banco, assim como acontece no fluxo de busca da aplicação.
