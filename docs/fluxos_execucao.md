# Diagramas dos fluxos de execução

Os diagramas documentam os principais limites do sistema, transformações de dados e artefatos produzidos. O corpus G1 deve estar previamente carregado em `g1_articles`; a aplicação não o importa automaticamente.

## 1. Contexto do sistema

**Entradas:** consultas, parâmetros de busca, comandos de população e conjuntos de avaliação.  
**Saídas:** resultados de busca, estado/resultados de avaliação e arquivos de relatório.  
**Finalidade:** situar os principais componentes e serviços externos antes de detalhar cada fluxo.

```mermaid
flowchart LR
    researcher[Pesquisador] --> browser[Interface web]
    researcher --> cli[CLI]

    subgraph app[Aplicação]
        api[Flask API]
        search[SearchService]
        ranking[RankingService]
        ner[NERService]
        population[Comandos de população]
        evaluations[Gerenciador de avaliações]
    end

    browser -->|consultas e avaliações| api
    cli -->|avaliação em lote via HTTP| api
    cli -->|busca direta| search
    cli --> population
    cli -->|exporta resultados| reports
    api --> search
    api --> evaluations
    search --> ranking
    ranking --> ner

    postgres[(PostgreSQL + pgvector)]
    redis[(Redis: cache de busca)]
    ollama[Ollama: embeddings]
    spacy[spaCy: NER em português]
    spotlight[DBpedia Spotlight: link opcional]
    evalfiles[(Arquivos JSON de avaliações)]
    reports[(Relatórios JSON/CSV)]

    search <-->|cache de recuperação/resposta| redis
    search -->|consulta híbrida e artigos| postgres
    ranking -->|artigos, entidades e relações| postgres
    population -->|chunks, vetores e entidades| postgres
    population -->|vetorização| ollama
    ner --> spacy
    ner -.->|link de entidades| spotlight
    evaluations -->|lê conjuntos| evalfiles
    evaluations -->|snapshots, estado e resultados| postgres
    api -->|resposta JSON| browser
```

## 2. Preparação do corpus e indexação

**Entradas:** artigos já armazenados em `g1_articles`, incluindo URL, título, data, metadados e corpo textual.  
**Saídas:** chunks, embeddings, menções de entidades, relações artigo-entidade e identidades canônicas.  
**Finalidade:** mostrar os processos offline que preparam os dados usados pela recuperação textual e pelo grafo.

```mermaid
flowchart TD
    source[Dump ou carga externa do corpus] -.->|pré-requisito; fora da aplicação| articles[(g1_articles)]

    subgraph chunk_index[Índice textual]
        articles --> pending_chunks[Selecionar artigos sem chunks]
        pending_chunks --> chunker[TokenChunker: 1024 tokens, overlap 256]
        chunker --> enrich[Adicionar título, data, trecho e categorias]
        enrich --> chunks[(g1_chunks; embedding inicialmente NULL)]
        chunks --> pending_vectors[Selecionar chunks sem embedding]
        pending_vectors --> embed[VectorizerService]
        embed --> ollama[Ollama: qwen3-embedding:0.6b, 768 dimensões]
        ollama --> vectors[(Atualizar g1_chunks.embedding)]
    end

    subgraph entity_index[Índice de entidades]
        articles --> pending_entities[Selecionar artigos sem entidades]
        pending_entities --> ner[NERService: análise em lote]
        ner --> spacy[spaCy pt_core_news_sm: texto, tipo e offsets]
        ner --> spotlight[DBpedia Spotlight: offsets, superfície e URI]
        spacy --> merge[Associar menções e links por sobreposição]
        spotlight --> merge
        spotlight -.->|indisponível: menções ficam sem link| merge
        merge --> entity_rows[(g1_entities)]
        merge --> article_entity_rows[(article_entities)]

        entity_rows -.->|comando de backfill posterior| canonicalize[Canonicalizar entidades]
        canonicalize --> junk[Marcar superfícies descartáveis]
        canonicalize -.->|consultas de link| spotlight
        junk --> bare[Passo 1: ligar superfície isolada ao Spotlight]
        bare --> context[Passo 2: tentar contexto para entidades frequentes]
        context --> suffix[Passo 3: mesclar sufixos de forma determinística]
        suffix --> canonical[(Atualizar canonical e is_junk)]
    end

    vectors --> retrieval_ready[Representação vetorial para recuperação]
    canonical --> graph_ready[Entidades resolvidas para construção do grafo]
    article_entity_rows --> graph_ready
```

O carregamento do dump é uma etapa externa. A aplicação executa chunking, vetorização, extração de entidades e canonicalização como comandos de população separados.

## 3. Busca online e ranking

**Entradas:** consulta e parâmetros como janela de datas, `top_k`, quorum, unidade de resultado, estágio, ranking e método de seed.  
**Saídas:** chunks recuperados, artigos ordenados com scores e, opcionalmente, dados do grafo, diagnósticos e tempos.  
**Finalidade:** explicar o caminho da requisição desde o cache até a resposta da API.

```mermaid
flowchart TD
    client[Interface web ou cliente HTTP] --> request[GET /search: consulta e parâmetros]
    request --> validate[Validar e normalizar parâmetros]
    validate --> response_cache{Resposta completa no Redis?}
    response_cache -->|sim| cached_response[Resposta em cache]
    response_cache -->|não| retrieval_cache{Recuperação no Redis?}

    retrieval_cache -->|sim| retrieval[Pool de chunks e rankings textuais]
    retrieval_cache -->|não| search_service[SearchService]
    search_service --> lexical_only{Busca lexical apenas?}
    lexical_only -->|não| query_embedding[Gerar embedding da consulta]
    query_embedding --> ollama[Ollama]
    ollama --> retrieve[Consulta lexical/vetorial no PostgreSQL]
    lexical_only -->|sim| retrieve
    retrieve --> retrieval

    retrieval --> pipeline[Pipeline de ranking]
    pipeline --> choice{Ranking solicitado}
    choice -->|lexical, vector, hybrid| text_rank[Ordenar candidatos por sinais textuais/vetoriais]
    choice -->|PPR ou ranking de grafo| graph_rank[Construir/usar grafo de candidatos]
    choice -->|cross-encoder| cross_encoder[Reordenar chunks candidatos com a consulta]
    choice -->|RRF ou ensemble| fusion[Fundir listas de rankings]

    text_rank --> assemble[Montar resposta JSON]
    graph_rank --> assemble
    cross_encoder --> assemble
    fusion --> assemble
    assemble --> optional_graph{Grafo produzido pelo ranking ou solicitado?}
    optional_graph -->|sim| graph_payload[Anexar nós, links e metadados do grafo]
    optional_graph -->|não| cache_response[Armazenar resposta no Redis]
    graph_payload --> cache_response
    cache_response --> output[Retornar resultados, artigos, rankings e diagnósticos]
    cached_response --> output
    output --> client
```

O ranking é configurável; o diagrama agrupa as alternativas para manter o fluxo legível. A resposta atual contém resultados recuperados/ordenados, não uma resposta narrativa gerada por LLM. A sumarização disponível no código não está conectada ao endpoint `/search`.

## 4. Avaliação em lote e painel

**Entradas:** avaliações com consultas e URLs relevantes, além de presets, quorums, rankings, seeds e unidade de resultado.  
**Saídas:** rankings por configuração, métricas, cobertura, tempos e relatórios persistidos ou exportados.  
**Finalidade:** documentar a avaliação experimental e diferenciar o caminho do CLI do caminho persistente do painel.

```mermaid
flowchart TD
    cli_file[CLI: --evaluate-file] --> validate[Validar JSON e verificar URLs relevantes no banco]
    validate --> expand[Expandir consultas em configurações: preset, quorum, ranking e seed]
    expand --> cli_mode{Reutilizar recuperação?}
    cli_mode -->|sim| eval_jobs[POST /evaluate/jobs]
    cli_mode -->|não| search_calls[Chamadas a /search por configuração]

    eval_json[Arquivos evals*.json] --> dashboard_select[Selecionar conjunto/snapshot no painel]
    dashboard_select --> dashboard_start[POST /dashboard/runs]
    dashboard_start --> snapshot[Salvar snapshot do conjunto e configurações]
    snapshot --> dashboard_manager[DashboardRunManager]
    dashboard_manager --> evaluate_request[evaluate_request: compartilhar recuperação entre rankings]

    eval_jobs --> search_core[Recuperação e ranking]
    search_calls --> search_core
    evaluate_request --> search_core

    search_core --> ranked[URLs ranqueadas e scores por configuração]
    ranked --> compare[Comparar com relevant_urls]
    compare --> metrics[Métricas: P/R/F1@k, MRR, MAP, NDCG e cobertura]
    metrics --> cli_outputs[CLI: checkpoint JSONL, resultados JSON e resumo CSV]
    metrics --> dashboard_store[(PostgreSQL: runs, resultados e artefatos)]
    dashboard_store --> dashboard_ui[Estado, progresso e resultados no painel]
    dashboard_store -.-> figures[Opcional: gerar figuras PDF/SVG/PNG]
```

No painel, a avaliação é executada pelo gerenciador da aplicação e os resultados são gravados incrementalmente no PostgreSQL. O CLI também pode usar o endpoint de jobs para compartilhar a recuperação; sem reutilização, faz chamadas de busca independentes. A geração de figuras é uma etapa posterior que lê rodadas já persistidas.

## 5. Construção do grafo e ranking PPR

**Entradas:** URLs dos artigos candidatos, entidades associadas, consulta (para `query_entities`) e parâmetros/método de seed.  
**Saídas:** scores e ranking dos artigos candidatos, além de uma representação serializada de nós e arestas.  
**Finalidade:** detalhar a etapa de grafo do fluxo online, em especial como entidades canônicas influenciam o Personalized PageRank.

```mermaid
flowchart TD
    candidates[Pool de URLs candidatas] --> load_articles[Carregar artigos candidatos]
    load_articles --> load_entities[Carregar entidades existentes ou extrair as ausentes]
    load_entities --> identity[Identidade: URI canônica; senão, texto de superfície]
    identity --> filter[Excluir entidades descartáveis]
    filter --> bipartite[Montar grafo bipartido artigo-entidade]
    bipartite --> prune[Podar com k-core, k=4]
    prune --> survives{Há grafo sobrevivente?}
    survives -->|não| fallback[Fallback: preservar nós de artigos candidatos]
    survives -->|sim| seed_method
    fallback --> seed_method{Selecionar método de seed}

    seed_method -->|HITS| hits[Selecionar entidades por autoridade]
    seed_method -->|Louvain| louvain[Comunidades e entidades representativas]
    seed_method -->|PPR top 10%| top_entities[Entidades com maior PageRank ajustado por grau]
    seed_method -->|query_entities| query_ner[Extrair entidades da consulta e casar com o grafo]
    query_ner --> query_match{Há correspondência?}
    query_match -->|sim| query_seeds[Usar entidades da consulta como seeds]
    query_match -->|não| query_fallback[Fallback configurado: HITS, Louvain ou PPR top 10%]

    hits --> personalize[Construir personalização]
    louvain --> personalize
    top_entities --> personalize
    query_seeds --> personalize
    query_fallback --> personalize
    personalize --> pagerank[Executar Personalized PageRank: alpha=0.85]
    pagerank --> normalize[Normalizar scores de entidades/artigos pelo grau]
    normalize --> rank_articles[Ordenar nós de artigo e produzir scores]
    rank_articles --> ranked_output[URLs ordenadas e scores]
    rank_articles --> serialize[Serializar nodes, links e metadados]
    serialize --> graph_output[Grafo para resposta/visualização]
```

O diagrama detalha o caminho PPR. Outros rankings de grafo disponíveis — por exemplo, RWR, HITS, SALSA, caminhos e caminhadas — compartilham a preparação do grafo, mas podem usar cálculos e critérios de ordenação diferentes.

## Referências no código

- `src/app.py`: comandos de população e composição dos serviços.
- `src/services/chunking.py`, `src/services/vectorizer.py`, `src/services/ner.py` e `src/services/linking.py`: preparação de chunks, embeddings e entidades.
- `src/api.py`, `src/services/search.py` e `src/services/search_pipeline.py`: API, recuperação e seleção do ranking.
- `src/services/ranking.py`: construção do grafo e PPR.
- `src/services/batch_evaluation.py`, `src/services/batch_search.py` e `src/services/dashboard_runs.py`: avaliação em lote e painel.
