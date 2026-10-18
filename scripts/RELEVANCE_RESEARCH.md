# Pesquisa reutilizável de casos de relevância

`relevance_research.py` reúne os scripts de estatísticas, amostragem, descoberta,
leitura dirigida e conferência usados em `casos_teste_relevancia_2025_2026.md`.
Não importa a aplicação, não chama modelos, não usa avaliações anteriores para
descobrir candidatos e não altera o banco. Usa as dependências já existentes:
Python 3.11, `psycopg` e `python-dotenv`.

**Não é um classificador automático de relevância.** Os padrões encontram
candidatos; um avaliador lê e registra a seleção, a ordem, as justificativas e
as evidências. O script valida esses registros, mas não comprova que o julgamento
editorial está correto. Ausência da seleção não significa irrelevância.

## 1. Preparação e segurança

Execute da raiz do repositório. Os comandos que consultam o banco precisam de
`POSTGRES_DSN` no ambiente ou no `.env` da raiz. Variáveis do ambiente prevalecem.
DSNs `postgresql://`, `postgresql+psycopg://` e `postgresql+psycopg2://` são aceitos.
Não passe credenciais na linha de comando. A conexão usa transação somente de
leitura, timeout de conexão de 10 segundos e timeout de consulta de 60 segundos.
As mensagens de erro PostgreSQL omitem os detalhes de conexão.

Opções globais devem vir **antes** do subcomando:

```bash
uv run python scripts/relevance_research.py --help
uv run python scripts/relevance_research.py --start 2025-06-01 --end 2026-05-20 stats
```

Os limites são inclusivos e filtram `date_published`, não a data de atualização.
Também existem `--env-file CAMINHO` e `--timeout-ms 60000`.
Não são necessários Ollama, Gemini, spaCy ou Redis.

Os exemplos gravam em `/tmp/opencode/relevance-research`, separado dos artefatos
da pesquisa original. Escolha outro diretório para uma nova coleta. Os JSONs
contêm corpos completos e podem ser grandes: arquive-os fora do Git. Arquivos
existentes não são sobrescritos sem `--force`. Não há remoção automática de dados.

## 2. Inspecionar o corpus sem partir de temas predefinidos

```bash
uv run python scripts/relevance_research.py stats
uv run python scripts/relevance_research.py sample --limit 850
```

`stats` mostra quantidade, intervalo, disponibilidade de títulos/corpos e totais
mensais. `sample` imprime JSON com títulos, datas e URLs, ordenado por `md5(url)`
com desempate por URL. A amostra é determinística para um corpus inalterado,
não uma garantia de representatividade ou de cobertura de toda a imprensa.

## 3. Descobrir e exportar candidatos

```bash
uv run python scripts/relevance_research.py discover --output-dir /tmp/opencode/relevance-research/candidates
uv run python scripts/relevance_research.py discover --theme master --theme inss --output-dir /tmp/opencode/relevance-research/another-snapshot
```

`scripts/relevance_patterns.json` preserva os dez padrões exploratórios originais.
Para pesquisa independente, crie outro objeto JSON `{ "identificador": "regex" }`
e forneça `--patterns CAMINHO`. A sintaxe é de **regex PostgreSQL**, aplicada ao
título sem diferenciar maiúsculas/minúsculas (`~*`), não regex Python nem busca
semântica. Identificadores de arquivo aceitam letras ASCII, números, `_` e `-`.
Os padrões são passados como parâmetros SQL, nunca interpolados na consulta.

Cada arquivo contém padrão, janela, instante da exportação e artigos ordenados
por data e URL. Os artigos preservam título, URL primária/final, corpo, data de
publicação, captura, extração e atualização no sitemap. A consulta completa é
mantida no script, sem depender de índices numéricos antigos.

A prévia favorece títulos com palavras como “entenda”, “cronologia” e “liquidação”
antes de ordenar por data; isso replica a triagem original, **não o ranking final
de relevância**. `--preview 65` controla seu tamanho. A contagem inclui ruído.

## 4. Revisar títulos e corpos

```bash
uv run python scripts/relevance_research.py titles /tmp/opencode/relevance-research/candidates/master.json --offset 0 --limit 65
uv run python scripts/relevance_research.py bodies /tmp/opencode/relevance-research/candidates/master.json --indices 0 1
uv run python scripts/relevance_research.py review /tmp/opencode/relevance-research/candidates/master.json --indices 0 1
```

Índices começam em zero e só identificam posições **dentro daquele snapshot**.
Não devem ser reutilizados após uma nova exportação. Também é possível selecionar
com `--urls URL1 URL2`, ou usar julgamentos estáveis por URL:

```bash
uv run python scripts/relevance_research.py review /tmp/opencode/relevance-research/candidates/master.json --selection /tmp/opencode/relevance-research/selection.json --theme M
```

`bodies` imprime o corpo completo. `review` replica a leitura dirigida original:
primeiros 1.250 caracteres e até 750 caracteres de até dois parágrafos posteriores
com termos factuais. Descarta chamadas de outros conteúdos e privilegia parágrafos
de 95–700 caracteres. **Pode omitir contexto, defesa e correções**; é auxílio de
triagem, não substituto da leitura integral. Nenhum comando assiste áudio/vídeo.
Os leitores também aceitam os arrays JSON produzidos pelos scripts temporários.

## 5. Registrar a curadoria manual

Formato JSON mínimo, com uma lista ordenada por tema:

```json
{
  "version": 1,
  "themes": [
    {
      "id": "M",
      "name": "Crise do Banco Master",
      "articles": [
        {
          "rank": 1,
          "url": "URL primária exata de g1_articles",
          "date": "2026-03-04",
          "title": "Título exato, podendo omitir apenas o sufixo | G1",
          "rationale": "Explicação editorial da inclusão e da prioridade.",
          "evidence": "Trecho literal, contínuo e sensível a maiúsculas do corpo",
          "notes": "Limitações, versão da defesa, hipótese superada etc."
        }
      ]
    }
  ]
}
```

Para reaproveitar **as decisões já documentadas** no relatório desta pesquisa:

```bash
uv run python scripts/relevance_research.py import-report casos_teste_relevancia_2025_2026.md --output /tmp/opencode/relevance-research/selection.json
```

Isso apenas importa o Markdown; não refaz a descoberta nem atribui relevância.
Os hashes por tema da seção de rastreabilidade também são importados como
`snapshot_sha256`, quando presentes, para conferir a versão original do corpus.
O importador aceita o formato específico do relatório: cabeçalhos `### M01 —
Relevância 1`, linha de data/título/link e campos `Motivo` e `Evidência no corpo`.
Preserva a justificativa e as notas após a citação. Para um novo estudo, escreva
o JSON diretamente ou mantenha esse formato editorial. O script não gera as
justificativas automaticamente e não reescreve o relatório.

## 6. Validar contra o banco ou contra snapshots

```bash
uv run python scripts/relevance_research.py validate --report casos_teste_relevancia_2025_2026.md --expected-count 20
uv run python scripts/relevance_research.py validate --selection /tmp/opencode/relevance-research/selection.json --expected-count 20
uv run python scripts/relevance_research.py validate --selection /tmp/opencode/relevance-research/selection.json --snapshots /tmp/opencode/relevance-research/candidates/master.json /tmp/opencode/relevance-research/candidates/inss.json /tmp/opencode/relevance-research/candidates/tarifaco.json /tmp/opencode/relevance-research/candidates/metanol.json /tmp/opencode/relevance-research/candidates/benicio.json --expected-count 20
```

Sem `--snapshots`, a conferência busca as URLs diretamente no banco, inclusive
as que estejam fora da janela, para apontar o erro. Com `--snapshots`, é offline
e não lê `.env`. Snapshots divergentes para a mesma URL são recusados: escolha
uma versão em vez de misturar coletas silenciosamente.

O JSON de resultado informa:
- Erros: URL ausente, título/data divergentes, publicação fora do recorte,
  justificativa/citação/corpo ausentes, evidência não literal, ranks fora de ordem,
  URL ou corpo idêntico repetidos **dentro do tema** e quantidade incorreta quando
  `--expected-count` é informado. Uma mesma URL pode ser relevante em dois temas.
- Avisos: captura/atualização ausente, ilegível ou posterior ao corte. Avisos
  não tornam o resultado inválido; exigem análise temporal do pesquisador.
- SHA-256 por tema com a mesma serialização descrita no relatório original.
  Se o tema na seleção tiver o campo opcional `snapshot_sha256`, a divergência
  é um erro, mesmo quando o trecho citado continua igual. `--report` e a seleção
  importada do relatório original já incluem esses hashes. Para uma nova pesquisa,
  arquive o hash da versão revisada, sem reutilizar uma referência antiga por acaso.
- Prefixos de 1, 3, 5, 10 e 20 URLs, quando há artigos suficientes. Não completa
  listas curtas com ruído e não transforma os demais candidatos em negativos.

Código de saída: `0` para conferência válida, `1` para erros; erros de argumentos
do argparse usam `2`. Estatísticas e conferências imprimem JSON em stdout, de
modo que possam ser arquivados por redirecionamento. Guarde também os snapshots:
hashes não são backups e as tabelas podem mudar.

**Métricas:** manter a mesma referência ao variar k. Estes conjuntos são curados,
não exaustivos. Recall calculado apenas sobre suas URLs mede recuperação dessa
referência, não de todos os documentos relevantes. Relevância atual e compreensão
histórica são tarefas distintas, especialmente quando uma hipótese foi superada.

## 7. Verificações locais sem serviços

```bash
uv run python -m unittest discover -s scripts/tests -v
```

Estas verificações são específicas do novo script, com dados sintéticos e sem
mocks de serviços. Não importam a aplicação nem substituem os testes de integração
existentes. Para conferir o banco real, use `stats`, `discover` e `validate`.
