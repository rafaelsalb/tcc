# Fluxos técnicos dos módulos G1

Estes diagramas detalham aquisição do corpus, preparação dos artigos, reconhecimento e resolução de entidades e busca web. Os rótulos nas setas identificam chamadas locais, protocolos de rede e persistência.

Os textos explicativos estão em português brasileiro; nomes de classes, campos, comandos e endpoints permanecem como no código.

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

O crawler mantém um controlador de taxa agregado mesmo com downloads paralelos. As threads fazem rede e extração; o coordenador usa psycopg para persistir status e conteúdo.

## 2. Segmentação do artigo e geração de embeddings

**Entrada:** `g1_articles.text_content` e metadados.  
**Saída:** trechos em `g1_chunks`; em um comando posterior, embeddings de 768 dimensões.

```mermaid
sequenceDiagram
    actor CLI
    participant App as Aplicação / ChunkingService
    participant TC as TokenChunker
    participant DB as PostgreSQL
    participant Ollama

    CLI->>App: --populate-chunks
    App->>DB: SQL SELECT artigos pendentes em g1_articles
    DB-->>App: Artigo + metadados
    App->>TC: chunk(texto, 1024 tokens, sobreposição 256)
    TC-->>App: Trechos em tokens
    App->>App: Prefixar título/data/trecho/categorias
    App->>DB: SQL batch_add_chunk, embedding NULL, is_chunked true
    Note over App,DB: Repetir o ciclo até não haver artigos pendentes.
    CLI->>App: --populate-embeddings
    App->>DB: SQL SELECT IDs dos trechos com embedding NULL
    DB-->>App: Lote de trechos
    App->>Ollama: HTTP JSON POST /api/embed (qwen3, dimensions=768)
    Ollama-->>App: Vetores de embedding
    App->>DB: SQL UPDATE g1_chunks.embedding
    Note over App,DB: Repetir o ciclo até não haver trechos pendentes.
```

Segmentação e vetorização são comandos separados: o primeiro persiste texto com embedding nulo; o segundo busca esses trechos e grava os vetores.

## 3. Extração de nomes e vinculação inicial

**Entrada:** corpos textuais de artigos sem entidades.  
**Saída:** menções tipadas e relações artigo-entidade; o link canônico pode ficar nulo se não houver correspondência.

```mermaid
flowchart TB
    cli[CLI: --populate-entities] --> select_articles[SQL: artigos sem entidades<br/>com text_content]
    select_articles --> ner[NERService: processar lote]
    ner --> spacy[spaCy local<br/>nlp.pipe: PER / ORG / LOC + offsets]
    ner -->|HTTP POST form /rest/annotate<br/>text + confidence=0.5| spotlight[DBpedia Spotlight]
    spacy -->|menções extraídas| merge[Combinar pela maior<br/>sobreposição de offsets]
    spotlight -->|Recursos JSON: Resources<br/>offset, surfaceForm, URI| merge
    spotlight -.->|falha: canonical NULL| merge
    merge --> persist[EntityRepository: inserção em lote<br/>SQLAlchemy / PostgreSQL]
    persist --> entities[(g1_entities<br/>text, type, canonical)]
    persist --> links[(article_entities<br/>artigo ↔ entidade)]
```

spaCy e as chamadas de rede ao Spotlight correm em paralelo durante o processamento em lote. A combinação usa offsets; a indisponibilidade do Spotlight não impede a extração local.

## 4. Vinculação e canonicalização de entidades existentes

**Entrada:** entidades `PER`, `ORG` e `LOC` ainda não canônicas.  
**Saída:** `canonical` com URI DBpedia, `is_junk` atualizado ou entidade mantida sem link.

```mermaid
flowchart LR
    cli[CLI: --canonicalize-entities] --> candidates[Marcar superfícies lixo<br/>e selecionar PER/ORG/LOC sem canonical]
    candidates --> pass1[Passo 1: buscar URI<br/>pela superfície isolada]
    pass1 -.->|HTTP POST form /rest/annotate| spotlight[DBpedia Spotlight<br/>recursos JSON]
    pass1 --> found1{surfaceForm<br/>corresponde?}
    found1 -->|sim| persist1[Salvar URI canônica]
    found1 -->|não| degree[Grau da entidade<br/>é pelo menos 2?]
    degree -->|sim| pass2[Passo 2: tentar novamente<br/>com texto de contexto]
    pass2 -.->|HTTP POST form /rest/annotate| spotlight
    pass2 --> found2{Correspondência<br/>validada?}
    found2 -->|sim| persist2[Salvar URI canônica]
    found2 -->|não| pass3[Passo 3: mesclar sufixos restantes<br/>de forma determinística]
    degree -->|não| pass3
    pass3 --> persist3[SQL UPDATE canonical/is_junk<br/>sem resolução: canonical NULL]
```

O canonicalizador é um processo retroativo distinto da vinculação inicial do NER: marca superfícies lixo e tenta resolver menções sem URI, primeiro pela superfície, depois pelo contexto e por fim por uma regra determinística de sufixo.

## 5. Busca web: módulos e protocolos

**Entrada:** `GET /search` com consulta e parâmetros.  
**Saída:** HTTP JSON com trechos e artigos ranqueados, pontuações, diagnósticos e, se aplicável, grafo.

```mermaid
flowchart TB
    browser[Navegador] -->|HTTP GET /search<br/>parâmetros de consulta| api[Flask API]
    api -->|Python local| pipeline[search_request]
    pipeline <-->|Redis RESP<br/>GET / SETEX, TTL 24 h| redis[(Cache Redis)]
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

    cli[CLI: --search] -.->|chamada Python direta<br/>sem API/cache/ranking| search
    search -.->|imprime trechos recuperados| terminal[Terminal]
```

As chamadas entre serviços Python são locais ao processo — não REST. As fronteiras de rede são a API Flask, Ollama, Spotlight, Redis e PostgreSQL. O caminho CLI é diferente da busca web: chama `SearchService.search` diretamente e imprime trechos; não executa o pipeline de ranking da API.

## Exportações para o TCC

Os SVGs vetoriais e PNGs a 300 dpi foram dimensionados para a área útil de A4, com margens de 12 mm. A orientação varia conforme a proporção do diagrama.

| Diagrama | Tamanho / página | SVG | PNG (300 dpi) |
|---|---:|---|---|
| Scraping G1 | 214,9 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/01_scraping_g1_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/01_scraping_g1_A4_landscape_300dpi.png) |
| Segmentação e embeddings | 245,3 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/02_chunking_embeddings_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/02_chunking_embeddings_A4_landscape_300dpi.png) |
| Extração e vinculação inicial | 107,8 × 273 mm, retrato | [SVG](figuras/fluxos_modulos_tecnicos/03_extracao_linking_inicial_A4_portrait.svg) | [PNG](figuras/fluxos_modulos_tecnicos/03_extracao_linking_inicial_A4_portrait_300dpi.png) |
| Canonicalização de entidades | 273 × 69,4 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/04_canonicalizacao_entidades_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/04_canonicalizacao_entidades_A4_landscape_300dpi.png) |
| Busca e protocolos | 197,9 × 186 mm, paisagem | [SVG](figuras/fluxos_modulos_tecnicos/05_busca_protocolos_A4_landscape.svg) | [PNG](figuras/fluxos_modulos_tecnicos/05_busca_protocolos_A4_landscape_300dpi.png) |
