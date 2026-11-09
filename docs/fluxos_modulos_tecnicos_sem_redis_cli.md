# Fluxos técnicos dos módulos G1 — sem cache e sem CLI

Versões alternativas dos cinco diagramas técnicos. Os fluxos mantêm a aquisição, transformação e persistência de dados, mas não mostram a invocação por CLI nem o cache Redis.

Versão com cache e caminhos CLI: [`docs/fluxos_modulos_tecnicos.md`](fluxos_modulos_tecnicos.md).

## 1. Web scraping G1

```mermaid
sequenceDiagram
    participant C as Crawler/coordenador
    participant G1 as Sitemap e páginas G1
    participant DB as PostgreSQL

    C->>C: Iniciar com data, índice e limites configurados
    C->>G1: HTTPS GET /sitemap.xml (Accept: XML)
    G1-->>C: sitemapindex XML
    C->>C: Parsear índice e selecionar/ordenar sitemaps diários
    loop Cada sitemap diário
        C->>G1: HTTPS GET sitemap diário (XML urlset)
        G1-->>C: loc, lastmod, image_loc
        C->>DB: SQL UPSERT g1_sitemaps e seeds g1_articles
        C->>DB: SQL verificar extrações já concluídas
        DB-->>C: URLs pendentes (ou skip se extraction_status=ok)
        loop URLs pendentes (ThreadPoolExecutor + RateGovernor compartilhado)
            C->>G1: HTTPS GET página HTML (headers, timeout, retry/backoff)
            G1-->>C: HTML, final_url e HTTP status
            C->>C: Trafilatura: HTML → texto e metadados
            alt extração OK
                C->>DB: SQL UPDATE conteúdo, metadados e status
            else fetch/extração falhou
                C->>DB: SQL UPDATE fetch_status, extraction_status e erro
            end
        end
        C->>DB: SQL commit e contadores em g1_sitemaps
    end
    Note over C,DB: Threads fazem rede/extração. A conexão psycopg é usada pelo coordenador.
```

## 2. Chunking e embeddings

```mermaid
sequenceDiagram
    participant App as Chunking/embedding workers
    participant TC as TokenChunker
    participant DB as PostgreSQL
    participant Ollama

    loop Articles with text and no chunks
        App->>DB: SQL SELECT g1_articles pending
        DB-->>App: Article + metadata
        App->>TC: chunk(text, 1024 tokens, overlap 256)
        TC-->>App: Token chunks
        App->>App: Prefix title/date/excerpt/categories
        App->>DB: SQL batch insert g1_chunks, embedding NULL, is_chunked true
    end
    loop Chunks where embedding IS NULL
        App->>DB: SQL SELECT chunk IDs + text
        DB-->>App: Chunk batch
        App->>Ollama: HTTP JSON POST /api/embed (qwen3, dimensions=768)
        Ollama-->>App: Embedding vectors
        App->>DB: SQL UPDATE g1_chunks.embedding
    end
```

## 3. Extração de nomes e linking inicial

```mermaid
sequenceDiagram
    participant App as Entity extraction worker
    participant DB as PostgreSQL
    participant NER as NERService
    participant spaCy
    participant Spotlight as DBpedia Spotlight

    loop Batch of articles without entities
        App->>DB: SQL SELECT URLs + text_content
        DB-->>App: Article batch
        App->>NER: batch_extract_entities_and_store (Python)
        par Local NER
            NER->>spaCy: nlp.pipe(batch_size=16)
            spaCy-->>NER: PER/ORG/LOC spans + offsets
        and Entity linking I/O
            NER->>Spotlight: HTTP POST /rest/annotate (form: text, confidence=0.5)
            Spotlight-->>NER: JSON Resources (offset, surfaceForm, URI)
        end
        NER->>NER: Merge spans by best character overlap
        NER->>DB: SQL batch insert g1_entities + article_entities
    end
    Note over NER,Spotlight: If Spotlight is unavailable, extracted names are stored with canonical=NULL.
```

## 4. Canonicalização de entidades

```mermaid
sequenceDiagram
    participant Canon as EntityCanonicalizer
    participant DB as PostgreSQL
    participant Spotlight as DBpedia Spotlight

    Canon->>DB: SQL ensure canonical/is_junk columns
    Canon->>DB: SQL mark junk and select unlinked PER/ORG/LOC by degree
    loop Pass 1: bare surface
        Canon->>Spotlight: HTTP POST /rest/annotate (form: surface, confidence=0.5)
        Spotlight-->>Canon: JSON Resources
        Canon->>Canon: Validate returned surfaceForm
        Canon->>DB: SQL UPDATE canonical for accepted URI
    end
    loop Pass 2: unresolved entities with degree >= 2
        Canon->>DB: SQL load sample article text
        DB-->>Canon: Context text
        Canon->>Spotlight: HTTP POST /rest/annotate (form: context + surface)
        Spotlight-->>Canon: JSON Resources
        Canon->>Canon: Validate surface match
        Canon->>DB: SQL UPDATE accepted canonical URIs
    end
    Canon->>Canon: Pass 3: deterministic suffix merge
    Canon->>DB: SQL UPDATE canonical, unresolved remain NULL
```

## 5. Busca web: módulos e protocolos

```mermaid
flowchart TB
    browser[Browser] -->|HTTP GET /search<br/>query params| api[Flask API]
    api -->|Python local| pipeline[search_request]
    pipeline -->|Python local| search[SearchService]
    search -->|HTTP JSON POST /api/embed<br/>se não lexical| ollama[Ollama embeddings]
    search -->|Python local| repo[ChunkRepository<br/>query_chunks_hybrid]
    repo -->|SQL via PostgreSQL protocol<br/>FTS GIN + pgvector HNSW| postgres[(PostgreSQL)]
    postgres -->|chunks / ranks| repo
    repo --> search
    search --> pipeline
    pipeline -->|Python local run_pipeline| ranker[RankingService<br/>ranker configurável]
    ranker -->|SQL: artigos/entidades| postgres
    ranker -->|Python local, se necessário| ner[NERService + spaCy]
    ner -->|HTTP POST form /rest/annotate| spotlight[DBpedia Spotlight]
    ranker -->|NetworkX local| results[Ranked URLs + scores<br/>chunks + grafo opcional]
    results --> pipeline
    pipeline --> api
    api -->|HTTP 200 JSON| browser
```

As chamadas entre serviços Python permanecem locais ao processo. A busca web usa HTTP para a API, Ollama e Spotlight e SQL pelo protocolo PostgreSQL para os dados.

## Exportações para o TCC

Os SVGs vetoriais e PNGs a 300 dpi foram dimensionados para a área útil de A4, com margens de 12 mm.

| Diagrama | Tamanho / página | SVG | PNG (300 dpi) |
|---|---:|---|---|
| Scraping G1 | 186 × 211,8 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/01_scraping_g1_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/01_scraping_g1_A4_portrait_300dpi.png) |
| Chunking e embeddings | 218,8 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/02_chunking_embeddings_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/02_chunking_embeddings_A4_landscape_300dpi.png) |
| Extração e linking inicial | 273 × 155,3 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/03_extracao_linking_inicial_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/03_extracao_linking_inicial_A4_landscape_300dpi.png) |
| Canonicalização de entidades | 186 × 205 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/04_canonicalizacao_entidades_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/04_canonicalizacao_entidades_A4_portrait_300dpi.png) |
| Busca e protocolos | 186 × 215,8 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/05_busca_protocolos_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/05_busca_protocolos_A4_portrait_300dpi.png) |
