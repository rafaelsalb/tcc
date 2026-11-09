# Diagramas dos fluxos de execução

Os diagramas documentam os principais limites do sistema, transformações de dados e artefatos produzidos. O corpus G1 deve estar previamente carregado em `g1_articles`; a aplicação não o importa automaticamente.

## 1. Contexto do sistema

**Entradas:** consultas, parâmetros de busca, comandos de população e conjuntos de avaliação.  
**Saídas:** resultados de busca, estado/resultados de avaliação e arquivos de relatório.  
**Finalidade:** situar os principais componentes e serviços externos antes de detalhar cada fluxo.

```mermaid
flowchart TB
    researcher[Pesquisador] --> web[Interface web]
    researcher --> cli[CLI]

    subgraph application[Aplicação]
        api[Flask API]
        search[SearchService]
        ranking[RankingService]
        population[População do corpus]
        evaluations[Avaliação]
        ner[NERService]
        api --> search
        api --> evaluations
        search --> ranking
        ranking --> ner
    end

    web --> api
    cli -->|avaliação em lote| api
    cli -->|busca direta| search
    cli --> population

    postgres[(PostgreSQL + pgvector)]
    redis[(Redis cache)]
    ollama[Ollama embeddings]
    spacy[spaCy NER]
    spotlight[DBpedia Spotlight opcional]
    datasets[Conjuntos JSON]

    search <-->|cache| redis
    search -->|recuperação| postgres
    search -->|embedding da consulta| ollama
    ranking -->|artigos e entidades| postgres
    population -->|chunks, vetores, entidades| postgres
    population --> ollama
    population --> ner
    ner --> spacy
    ner -.-> spotlight
    evaluations --> datasets
    evaluations -->|snapshots e resultados| postgres
    cli -->|exporta| reports[Relatórios JSON/CSV]
```

## 2. Preparação do corpus e indexação

**Entradas:** artigos já armazenados em `g1_articles`, incluindo URL, título, data, metadados e corpo textual.  
**Saídas:** chunks, embeddings, menções de entidades, relações artigo-entidade e identidades canônicas.  
**Finalidade:** mostrar os processos offline que preparam os dados usados pela recuperação textual e pelo grafo.

```mermaid
flowchart LR
    source[Dump/carga externa] -.-> articles[(g1_articles)]

    articles --> chunking[Chunking: 1024 tokens<br/>overlap 256 + metadados]
    chunking --> chunks[(g1_chunks)]
    chunks --> embedding[Ollama embeddings<br/>qwen3, 768 dimensões]
    embedding --> vectors[(Vetores no PostgreSQL)]

    articles --> extraction[spaCy NER<br/>+ Spotlight opcional]
    extraction --> mentions[Menções e relações<br/>artigo-entidade]
    mentions --> canonicalize[Backfill: filtrar lixo<br/>e canonicalizar aliases]
    canonicalize --> entities[(g1_entities<br/>+ article_entities)]
```

O carregamento do dump é uma etapa externa. A aplicação executa chunking, vetorização, extração de entidades e canonicalização como comandos de população separados.

## 3. Busca online e ranking

**Entradas:** consulta e parâmetros como janela de datas, `top_k`, quorum, unidade de resultado, estágio, ranking e método de seed.  
**Saídas:** chunks recuperados, artigos ordenados com scores e, opcionalmente, dados do grafo, diagnósticos e tempos.  
**Finalidade:** explicar o caminho da requisição desde o cache até a resposta da API.

```mermaid
flowchart LR
    client[Consulta + filtros] --> endpoint[GET /search]
    endpoint --> cache{Cache Redis?}
    cache -->|hit| cached[Resposta pronta]
    cache -->|miss| retrieval[Usar pool em cache ou<br/>embedding + busca no PostgreSQL]
    retrieval --> pool[Chunks + artigos candidatos]
    pool --> ranking[Ranking selecionado:<br/>textual, PPR/grafo,<br/>cross-encoder ou fusão]
    ranking --> response[URLs e chunks ordenados<br/>scores + diagnósticos<br/>grafo quando disponível]
    cached --> response
    response --> client
```

O ranking é configurável; o diagrama agrupa as alternativas para manter o fluxo legível. A resposta atual contém resultados recuperados/ordenados, não uma resposta narrativa gerada por LLM. A sumarização disponível no código não está conectada ao endpoint `/search`.

## 4. Avaliação em lote e painel

**Entradas:** avaliações com consultas e URLs relevantes, além de presets, quorums, rankings, seeds e unidade de resultado.  
**Saídas:** rankings por configuração, métricas, cobertura, tempos e relatórios persistidos ou exportados.  
**Finalidade:** documentar a avaliação experimental e diferenciar o caminho do CLI do caminho persistente do painel.

```mermaid
flowchart LR
    cli[CLI: JSON + configurações] --> validate[Validar consultas e URLs relevantes]
    dashboard[Painel: conjunto/snapshot] --> snapshot[Salvar snapshot da avaliação]
    validate --> tasks[Expandir presets, quorums,<br/>rankings e seeds]
    snapshot --> tasks
    tasks --> execute[Recuperar e ranquear<br/>reutilizando pool quando possível]
    execute --> compare[Comparar ranking<br/>com URLs relevantes]
    compare --> metrics[P/R/F1@k, MRR,<br/>MAP, NDCG e cobertura]
    metrics --> files[CLI: JSONL, JSON e CSV]
    metrics --> database[(Painel: resultados<br/>e artefatos no PostgreSQL)]
    database --> ui[Progresso e resultados]
    database -.-> figures[Figuras PDF/SVG/PNG]
```

No painel, a avaliação é executada pelo gerenciador da aplicação e os resultados são gravados incrementalmente no PostgreSQL. O CLI também pode usar o endpoint de jobs para compartilhar a recuperação; sem reutilização, faz chamadas de busca independentes. A geração de figuras é uma etapa posterior que lê rodadas já persistidas.

## 5. Construção do grafo e ranking PPR

**Entradas:** URLs dos artigos candidatos, entidades associadas, consulta (para `query_entities`) e parâmetros/método de seed.  
**Saídas:** scores e ranking dos artigos candidatos, além de uma representação serializada de nós e arestas.  
**Finalidade:** detalhar a etapa de grafo do fluxo online, em especial como entidades canônicas influenciam o Personalized PageRank.

```mermaid
flowchart LR
    candidates[URLs candidatas + entidades] --> graph_build[Montar grafo artigo-entidade<br/>URI canônica ou superfície]
    graph_build --> prune[Filtrar lixo e podar<br/>k-core, k=4]
    prune --> seeds{Escolher seeds}
    seeds -->|HITS| hits[Entidades por autoridade]
    seeds -->|Louvain| louvain[Entidades por comunidade]
    seeds -->|PPR| top[Top 10% de entidades]
    seeds -->|consulta| query[Entidades da consulta<br/>ou fallback configurado]
    hits --> personalized[PPR personalizado<br/>alpha=0.85]
    louvain --> personalized
    top --> personalized
    query --> personalized
    personalized --> scores[Normalizar scores<br/>e ordenar artigos]
    scores --> ranked[URLs ranqueadas + scores]
    scores --> graph_json[Grafo serializado<br/>para visualização]
```

O diagrama detalha o caminho PPR. Outros rankings de grafo disponíveis — por exemplo, RWR, HITS, SALSA, caminhos e caminhadas — compartilham a preparação do grafo, mas podem usar cálculos e critérios de ordenação diferentes.

## Referências no código

- `src/app.py`: comandos de população e composição dos serviços.
- `src/services/chunking.py`, `src/services/vectorizer.py`, `src/services/ner.py` e `src/services/linking.py`: preparação de chunks, embeddings e entidades.
- `src/api.py`, `src/services/search.py` e `src/services/search_pipeline.py`: API, recuperação e seleção do ranking.
- `src/services/ranking.py`: construção do grafo e PPR.
- `src/services/batch_evaluation.py`, `src/services/batch_search.py` e `src/services/dashboard_runs.py`: avaliação em lote e painel.

## Exportações para o TCC

As figuras foram dimensionadas para caber na área útil de uma página A4 em paisagem, considerando margens de 12 mm. Os SVGs são vetoriais; os PNGs têm resolução de 300 dpi e a mesma dimensão física da figura. Para manter a legibilidade, insira-as em página A4 paisagem.

Para as versões sem cache Redis e sem CLI, consulte [`docs/fluxos_execucao_sem_redis_cli.md`](fluxos_execucao_sem_redis_cli.md).

Para os detalhes técnicos do scraping, chunking, extração/linking de entidades e protocolos de busca, consulte [`docs/fluxos_modulos_tecnicos.md`](fluxos_modulos_tecnicos.md) e sua [versão sem Redis/CLI](fluxos_modulos_tecnicos_sem_redis_cli.md).

| Diagrama | Dimensão física | SVG | PNG (300 dpi) |
|---|---:|---|---|
| Contexto do sistema | 246,1 × 186 mm | [SVG](figuras/fluxos_execucao/01_contexto_sistema_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao/01_contexto_sistema_A4_fit_landscape_300dpi.png) |
| Preparação do corpus | 273 × 85 mm | [SVG](figuras/fluxos_execucao/02_preparacao_corpus_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao/02_preparacao_corpus_A4_fit_landscape_300dpi.png) |
| Busca online | 273 × 60,1 mm | [SVG](figuras/fluxos_execucao/03_busca_online_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao/03_busca_online_A4_fit_landscape_300dpi.png) |
| Avaliação | 273 × 61,6 mm | [SVG](figuras/fluxos_execucao/04_avaliacao_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao/04_avaliacao_A4_fit_landscape_300dpi.png) |
| Grafo e PPR | 273 × 88,5 mm | [SVG](figuras/fluxos_execucao/05_grafo_ppr_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao/05_grafo_ppr_A4_fit_landscape_300dpi.png) |
