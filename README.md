# Avaliações em lote

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
não vazia de avaliações. Cada avaliação deve conter **exatamente** os campos
`id`, `query` e `relevant_urls`:

```json
{
  "schema_version": 1,
  "evaluations": [
    {
      "id": "politica-01",
      "query": "investigações sobre corrupção",
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
`g1_articles`. **Cada avaliação precisa ter pelo menos 10 URLs relevantes
únicas.** Os `id`s também devem ser únicos. Campos extras, URLs inválidas,
duplicadas ou ausentes do banco fazem a validação falhar antes das buscas.

Para executar:

```bash
uv run python -m src --evaluate-file avaliacoes.json
```

Por padrão, o comando cria `avaliacoes.results.json` com os resultados
detalhados e `avaliacoes.results.csv` com o resumo das métricas. Para escolher
outro caminho para o JSON, use `--output`; o CSV será criado ao lado dele:

```bash
uv run python -m src --evaluate-file avaliacoes.json --output resultados/lote.json
```

O diretório de saída precisa existir. Para substituir arquivos de saída já
existentes, acrescente `--overwrite`.

## Configuração usada

Sem opções por avaliação, o script usa os padrões da interface: nível
**Balanceado** (`limit=200` e `top_k=30`), método de tópicos **Louvain**,
quorum `0.7` e sem filtros de data. As métricas calculadas são Precisão@k e
Revocação@k para `k = 1, 3, 5, 10, 20`.

O JSON detalhado inclui as URLs relevantes e ordenadas, as configurações e as
métricas de cada avaliação. O CSV contém uma linha por avaliação.

> **Atenção:** a etapa de ordenação pode extrair e armazenar entidades que ainda
> não existam no banco, assim como acontece no fluxo de busca da aplicação.
