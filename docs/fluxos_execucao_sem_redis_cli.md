# Fluxos de execução — versões sem cache Redis e sem CLI

Estas versões mantêm os cinco fluxos da documentação principal, mas mostram apenas os caminhos da interface web e dos serviços centrais. Os diagramas 2 e 5 não precisaram de alterações porque já não mostravam Redis nem CLI.

## 1. Contexto do sistema

**Entradas:** consultas pela interface web, conjuntos de avaliação e artigos existentes.  
**Saídas:** resultados de busca, avaliações persistidas e artefatos de análise.  
**Finalidade:** apresentar a aplicação, os serviços externos e o PostgreSQL sem os detalhes de cache e dos comandos de linha de comando.

```mermaid
flowchart TB
    researcher[Pesquisador] --> browser[Interface web]

    subgraph application[Aplicação]
        api[Flask API]
        search[SearchService]
        ranking[RankingService]
        population[Preparação offline do corpus]
        evaluations[Avaliação do painel]
        ner[NERService]
        api --> search
        api --> evaluations
        search --> ranking
        ranking --> ner
    end

    browser --> api
    postgres[(PostgreSQL + pgvector)]
    ollama[Ollama embeddings]
    spacy[spaCy NER]
    spotlight[DBpedia Spotlight opcional]
    datasets[Conjuntos JSON]

    search -->|recuperação| postgres
    search -->|embedding da consulta| ollama
    ranking -->|artigos e entidades| postgres
    postgres -->|artigos pendentes| population
    population -->|chunks, vetores e entidades| postgres
    population --> ollama
    population --> ner
    ner --> spacy
    ner -.-> spotlight
    evaluations --> datasets
    evaluations -->|snapshots e resultados| postgres
    api -->|resposta JSON| browser
```

## 2. Preparação do corpus e indexação

**Entradas:** artigos já armazenados em `g1_articles`.  
**Saídas:** chunks, embeddings e relações entre artigos e entidades.  
**Finalidade:** mostrar a preparação offline que alimenta a recuperação textual e o grafo.

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

## 3. Busca online e ranking

**Entradas:** consulta e parâmetros de busca.  
**Saídas:** artigos e chunks ordenados, scores, diagnósticos e, quando disponível, dados do grafo.  
**Finalidade:** mostrar a recuperação e o ranking sem o ramo de cache.

```mermaid
flowchart LR
    client[Consulta + filtros] --> endpoint[GET /search]
    endpoint --> retrieval[Embedding quando necessário<br/>+ recuperação no PostgreSQL]
    retrieval --> pool[Chunks + artigos candidatos]
    pool --> ranking[Ranking selecionado:<br/>textual, PPR/grafo,<br/>cross-encoder ou fusão]
    ranking --> response[URLs e chunks ordenados<br/>scores + diagnósticos<br/>grafo quando disponível]
    response --> client
```

## 4. Avaliação pelo painel

**Entradas:** conjuntos JSON com consultas e URLs relevantes, mais as configurações da rodada.  
**Saídas:** métricas, resultados e artefatos persistidos no PostgreSQL, apresentados no painel.  
**Finalidade:** mostrar o fluxo de avaliação do painel sem o caminho de execução em lote do CLI.

```mermaid
flowchart LR
    datasets[Conjunto de avaliação:<br/>consultas + URLs relevantes] --> start[Painel: salvar snapshot<br/>e escolher configurações]
    start --> search[Executar recuperação<br/>e rankings por configuração]
    search --> compare[Comparar ranking<br/>com URLs relevantes]
    compare --> metrics[P/R/F1@k, MRR,<br/>MAP e NDCG]
    metrics --> database[(Persistir rodada,<br/>resultados e artefatos)]
    database --> ui[Progresso e resultados]
    database -.-> figures[Gerar figuras]
```

## 5. Construção do grafo e ranking PPR

**Entradas:** URLs candidatas, entidades associadas e método de seed.  
**Saídas:** URLs ranqueadas com scores e grafo serializado para visualização.  
**Finalidade:** detalhar o cálculo de PPR; este fluxo já não dependia de Redis nem de CLI.

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

## Exportações A4

As figuras cabem na área útil de uma página A4 em paisagem, com 12 mm de margens. Os SVGs são vetoriais e os PNGs têm resolução de 300 dpi.

| Diagrama | Dimensão física | SVG | PNG (300 dpi) |
|---|---:|---|---|
| Contexto do sistema | 247,3 × 186 mm | [SVG](figuras/fluxos_execucao_sem_redis_cli/01_contexto_sistema_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao_sem_redis_cli/01_contexto_sistema_A4_fit_landscape_300dpi.png) |
| Preparação do corpus | 273 × 85 mm | [SVG](figuras/fluxos_execucao_sem_redis_cli/02_preparacao_corpus_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao_sem_redis_cli/02_preparacao_corpus_A4_fit_landscape_300dpi.png) |
| Busca online | 273 × 74 mm | [SVG](figuras/fluxos_execucao_sem_redis_cli/03_busca_online_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao_sem_redis_cli/03_busca_online_A4_fit_landscape_300dpi.png) |
| Avaliação pelo painel | 273 × 40,2 mm | [SVG](figuras/fluxos_execucao_sem_redis_cli/04_avaliacao_painel_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao_sem_redis_cli/04_avaliacao_painel_A4_fit_landscape_300dpi.png) |
| Grafo e PPR | 273 × 88,5 mm | [SVG](figuras/fluxos_execucao_sem_redis_cli/05_grafo_ppr_A4_fit_landscape.svg) | [PNG](figuras/fluxos_execucao_sem_redis_cli/05_grafo_ppr_A4_fit_landscape_300dpi.png) |
