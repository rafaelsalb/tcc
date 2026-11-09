# Fluxos técnicos dos módulos G1 — sem cache e sem CLI

Versões alternativas dos cinco diagramas técnicos. Os fluxos mantêm a aquisição, transformação e persistência de dados, mas não mostram a invocação por CLI nem o cache Redis.

Os textos explicativos estão em português brasileiro; nomes de classes, campos e endpoints permanecem como no código.

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

## 2. Segmentação e embeddings

```mermaid
sequenceDiagram
    participant App as Worker de segmentação/vetorização
    participant TC as TokenChunker
    participant DB as PostgreSQL
    participant Ollama

    App->>DB: SQL SELECT artigos pendentes em g1_articles
    DB-->>App: Artigo + metadados
    App->>TC: chunk(texto, 1024 tokens, sobreposição 256)
    TC-->>App: Trechos em tokens
    App->>App: Prefixar título/data/trecho/categorias
    App->>DB: SQL batch_add_chunk, embedding NULL, is_chunked true
    Note over App,DB: O worker repete até não haver artigos pendentes.
    App->>DB: SQL SELECT trechos com embedding NULL
    DB-->>App: Lote de trechos
    App->>Ollama: HTTP JSON POST /api/embed (qwen3, dimensions=768)
    Ollama-->>App: Vetores de embedding
    App->>DB: SQL UPDATE g1_chunks.embedding
    Note over App,DB: O worker repete até não haver trechos pendentes.
```

## 3. Extração de nomes e vinculação inicial

```mermaid
flowchart TB
    articles[(Artigos sem entidades)] --> ner[NERService: processar lote]
    ner --> spacy[spaCy local<br/>nlp.pipe: PER / ORG / LOC + offsets]
    ner -->|HTTP POST form /rest/annotate<br/>text + confidence=0.5| spotlight[DBpedia Spotlight]
    spacy -->|menções extraídas| merge[Combinar pela maior<br/>sobreposição de offsets]
    spotlight -->|Recursos JSON: Resources<br/>offset, surfaceForm, URI| merge
    spotlight -.->|falha: canonical NULL| merge
    merge --> persist[EntityRepository: inserção em lote<br/>SQLAlchemy / PostgreSQL]
    persist --> entities[(g1_entities<br/>text, type, canonical)]
    persist --> links[(article_entities<br/>artigo ↔ entidade)]
```

## 4. Canonicalização de entidades

```mermaid
flowchart LR
    entities[(Entidades existentes)] --> candidates[Marcar lixo<br/>e selecionar entidades sem canonical]
    candidates --> pass1[Passo 1: buscar URI<br/>pela superfície isolada]
    pass1 -.->|HTTP POST form /rest/annotate| spotlight[DBpedia Spotlight<br/>recursos JSON]
    pass1 --> found1{surfaceForm<br/>corresponde?}
    found1 -->|sim| persist1[Salvar URI canônica]
    found1 -->|não| degree[Grau da entidade<br/>é pelo menos 2?]
    degree -->|sim| pass2[Passo 2: consultar com<br/>texto de contexto]
    pass2 -.->|HTTP POST form /rest/annotate| spotlight
    pass2 --> found2{Correspondência<br/>validada?}
    found2 -->|sim| persist2[Salvar URI canônica]
    found2 -->|não| pass3[Passo 3: mesclar sufixos<br/>restantes de forma determinística]
    degree -->|não| pass3
    pass3 --> persist3[SQL UPDATE canonical/is_junk<br/>não resolvidas ficam NULL]
```

## 5. Busca web: módulos e protocolos

```mermaid
flowchart TB
    browser[Navegador] -->|HTTP GET /search<br/>parâmetros de consulta| api[Flask API]
    api -->|Python local| pipeline[search_request]
    pipeline -->|Python local| search[SearchService]
    search -->|HTTP JSON POST /api/embed<br/>exceto busca lexical| ollama[Embeddings Ollama]
    search -->|Python local| repo[ChunkRepository<br/>query_chunks_hybrid]
    repo -->|SQL pelo protocolo PostgreSQL<br/>FTS GIN + pgvector/HNSW| postgres[(PostgreSQL)]
    postgres -->|trechos / posições| repo
    repo --> search
    search --> pipeline
    pipeline -->|Python local run_pipeline| ranker[RankingService<br/>ranking configurável]
    ranker -->|SQL: artigos/entidades| postgres
    ranker -->|Python local, se necessário| ner[NERService + spaCy]
    ner -->|HTTP POST form /rest/annotate| spotlight[DBpedia Spotlight]
    ranker -->|NetworkX em processo| results[URLs ranqueadas + pontuações<br/>trechos + grafo opcional]
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
| Segmentação e embeddings | 233,9 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/02_chunking_embeddings_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/02_chunking_embeddings_A4_landscape_300dpi.png) |
| Extração e vinculação inicial | 124,2 × 273 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/03_extracao_linking_inicial_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/03_extracao_linking_inicial_A4_portrait_300dpi.png) |
| Canonicalização de entidades | 273 × 69,7 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/04_canonicalizacao_entidades_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/04_canonicalizacao_entidades_A4_landscape_300dpi.png) |
| Busca e protocolos | 186 × 215,8 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/05_busca_protocolos_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos_sem_redis_cli/05_busca_protocolos_A4_portrait_300dpi.png) |
