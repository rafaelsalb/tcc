# Fluxos técnicos dos módulos G1

Estes diagramas detalham aquisição do corpus, preparação dos artigos, reconhecimento e resolução de entidades e busca web. Os rótulos nas setas identificam chamadas locais, protocolos de rede e persistência.

> Escopo: `traverse_sitemap.py` é o crawler do corpus G1. `get_data.py` ingere arquivos GDELT ZIP e `get_titles.py` enriquece URLs desse conjunto; são pipelines diferentes e não estão misturados ao crawler G1 abaixo.

Para as variantes sem cache Redis e sem o caminho CLI, consulte [`docs/fluxos_modulos_tecnicos_sem_redis_cli.md`](fluxos_modulos_tecnicos_sem_redis_cli.md).

## 1. Web scraping G1: sitemap → artigo → PostgreSQL

**Entrada:** índice/sitemaps do G1 e parâmetros como data, concorrência e limites.  
**Saída:** registros de `g1_sitemaps` e artigos com conteúdo, metadados e status em `g1_articles`.

```mermaid
sequenceDiagram
    actor CLI
    participant C as Crawler/coordenador
    participant G1 as Sitemap e páginas G1
    participant DB as PostgreSQL

    CLI->>C: traverse_sitemap.py(data, index, RPS, concurrency)
    C->>G1: HTTPS GET /sitemap.xml (Accept: XML)
    G1-->>C: sitemapindex XML
    C->>C: Parsear índice e selecionar/ordenar sitemaps diários
    loop Cada sitemap diário
        C->>G1: HTTPS GET sitemap diário (XML urlset)
        G1-->>C: loc, lastmod, image_loc
        C->>DB: SQL UPSERT g1_sitemaps e seeds g1_articles (psycopg)
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

O crawler mantém um rate governor agregado mesmo com fetch paralelo. Os workers fazem rede/extração; o coordenador usa psycopg para persistir status e conteúdo.

## 2. Chunking do artigo e geração de embeddings

**Entrada:** `g1_articles.text_content` e metadados.  
**Saída:** chunks em `g1_chunks`; em um comando posterior, embeddings de 768 dimensões.

```mermaid
sequenceDiagram
    actor CLI
    participant App as App/ChunkingService
    participant TC as TokenChunker
    participant DB as PostgreSQL
    participant Ollama

    CLI->>App: --populate-chunks
    loop Poll articles without chunks
        App->>DB: SQL SELECT g1_articles pending text
        DB-->>App: Article rows + metadata
        App->>TC: chunk(text, 1024 tokens, overlap 256)
        TC-->>App: Token chunks
        App->>App: Prefix title/date/excerpt/categories
        App->>DB: SQL batch_add_chunk, embedding NULL, is_chunked true
    end
    CLI->>App: --populate-embeddings
    loop Poll chunks where embedding IS NULL
        App->>DB: SQL SELECT chunk IDs + text
        DB-->>App: Chunk batch
        App->>Ollama: HTTP JSON POST /api/embed (qwen3, dimensions=768)
        Ollama-->>App: Embedding vectors
        App->>DB: SQL UPDATE g1_chunks.embedding
    end
```

Chunking e vetorização são comandos separados: o primeiro persiste texto com embedding nulo; o segundo busca esses chunks e grava os vetores.

## 3. Extração de nomes e linking inicial

**Entrada:** corpos textuais de artigos sem entidades.  
**Saída:** menções tipadas e relações artigo-entidade; o link canônico pode ficar nulo se não houver correspondência.

```mermaid
sequenceDiagram
    actor CLI
    participant App
    participant DB as PostgreSQL
    participant NER as NERService
    participant spaCy
    participant Spotlight as DBpedia Spotlight

    CLI->>App: --populate-entities
    loop Batch of articles without entities
        App->>DB: SQL SELECT article URLs + text_content
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
    Note over NER,Spotlight: Spotlight failure leaves extracted mentions unlinked and canonical may be NULL.
```

spaCy e as chamadas I/O ao Spotlight correm em paralelo durante o processamento em lote. O merge usa offsets; a indisponibilidade do Spotlight não impede a extração local.

## 4. Linking/canonicalização de entidades existentes

**Entrada:** entidades `PER`, `ORG` e `LOC` ainda não canônicas.  
**Saída:** `canonical` com URI DBpedia, `is_junk` atualizado ou entidade mantida sem link.

```mermaid
sequenceDiagram
    actor CLI
    participant Canon as EntityCanonicalizer
    participant DB as PostgreSQL
    participant Spotlight as DBpedia Spotlight

    CLI->>Canon: --canonicalize-entities (optional limit)
    Canon->>DB: SQL ensure columns canonical, is_junk
    Canon->>DB: SQL scan entities and mark junk surfaces
    Canon->>DB: SQL select unlinked PER/ORG/LOC ordered by article degree
    loop Pass 1: bare surface
        Canon->>Spotlight: HTTP POST /rest/annotate (form: surface, confidence=0.5)
        Spotlight-->>Canon: JSON Resources
        Canon->>Canon: Validate returned surfaceForm
        Canon->>DB: SQL UPDATE canonical for accepted URI
    end
    loop Pass 2: unresolved entities with degree >= 2
        Canon->>DB: SQL load a sample article text
        DB-->>Canon: Context text
        Canon->>Spotlight: HTTP POST /rest/annotate (form: context + surface)
        Spotlight-->>Canon: JSON Resources
        Canon->>Canon: Validate surface match
        Canon->>DB: SQL UPDATE accepted canonical URIs
    end
    Canon->>Canon: Pass 3: deterministic suffix merge for remaining rows
    Canon->>DB: SQL UPDATE canonical, unresolved remain NULL
    Canon-->>CLI: Link counts and summary report
```

O canonicalizer é um backfill distinto do linking inicial do NER: ele marca lixo e tenta resolver menções que ficaram sem URI, primeiro pela superfície, depois pelo contexto e por fim por uma regra determinística de sufixo.

## 5. Busca web: módulos e protocolos

**Entrada:** `GET /search` com consulta e parâmetros.  
**Saída:** HTTP JSON com chunks/artigos ordenados, scores, diagnósticos e, se aplicável, grafo.

```mermaid
flowchart TB
    browser[Browser] -->|HTTP GET /search<br/>query params| api[Flask API]
    api -->|Python local| pipeline[search_request]
    pipeline <-->|Redis RESP<br/>GET / SETEX, TTL 24 h| redis[(Redis cache)]
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

    cli[CLI: --search] -.->|Python direto<br/>sem API/cache/ranking| search
    search -.->|imprime chunks| terminal[Terminal]
```

As chamadas entre serviços Python são locais ao processo — não REST. As fronteiras de rede são a API Flask, Ollama, Spotlight, Redis e PostgreSQL. O caminho CLI é diferente da busca web: chama `SearchService.search` diretamente e imprime chunks; não executa o pipeline de ranking da API.

## Exportações para o TCC

Os SVGs vetoriais e PNGs a 300 dpi foram dimensionados para a área útil de A4, com margens de 12 mm. A orientação varia conforme a proporção do diagrama.

| Diagrama | Tamanho / página | SVG | PNG (300 dpi) |
|---|---:|---|---|
| Scraping G1 | 214,9 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/01_scraping_g1_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/01_scraping_g1_A4_landscape_300dpi.png) |
| Chunking e embeddings | 231,7 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/02_chunking_embeddings_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/02_chunking_embeddings_A4_landscape_300dpi.png) |
| Extração e linking inicial | 273 × 140,6 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/03_extracao_linking_inicial_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/03_extracao_linking_inicial_A4_landscape_300dpi.png) |
| Canonicalização de entidades | 193,2 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/04_canonicalizacao_entidades_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/04_canonicalizacao_entidades_A4_landscape_300dpi.png) |
| Busca e protocolos | 197,9 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/05_busca_protocolos_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/05_busca_protocolos_A4_landscape_300dpi.png) |
