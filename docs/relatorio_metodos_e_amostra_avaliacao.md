# Métodos dos resultados e composição da amostra de avaliação

## Métodos considerados

O pipeline separa **classificação** — como os artigos candidatos são ordenados — de **seeding** — quais nós iniciam ou personalizam os métodos de grafo. A tabela descreve as configurações referidas nos resultados:

| Resultado | Método de classificação | Método de seeding |
|---|---|---|
| Fusão RRF | `rrf`: Reciprocal Rank Fusion das listas lexical e vetorial, restrita ao pool híbrido de artigos candidatos. | Nulo: esse ranking não depende de seed nem de grafo. |
| Ensemble RRF – HITS | `ensemble_rrf`: fusão RRF, com pesos iguais, dos rankings componentes. A configuração padrão combina `rrf`, `cross_encoder` e `ppr`. | `hits`: seleciona entidades para personalizar o componente PPR do ensemble; HITS é o seeding do PPR, não um ranking componente separado. |
| HITS ponderado + cross-encoder | `graph_hits_cross_encoder`: aplica um cross-encoder aos artigos candidatos e usa as probabilidades resultantes como pesos das arestas de um grafo bipartido artigo–entidade; HITS produz a ordenação. | `query_entities`: usa entidades PER/ORG/LOC reconhecidas na consulta e encontradas no grafo. Se não houver entidades/arestas utilizáveis, pode recorrer ao método de fallback configurado para aquela execução. |
| SALSA – Louvain | `graph_salsa`: realiza caminhadas alternadas entre entidades e artigos no grafo bipartido, com reinício nos seeds. | `louvain`: detecta comunidades no grafo de entidades projetado e escolhe entidades-seed entre as comunidades. |

**Nota sobre HITS ponderado + cross-encoder:** o identificador de seeding configurado na grade de avaliação funciona como fallback. Quando existem entidades da consulta conectadas aos artigos, o método usa essas entidades diretamente. Portanto, a configuração não deve ser descrita como se Louvain ou HITS fossem sempre os seeds efetivos nesse ranking.

## Lote e filtros da amostra

O último lote documentado é o run `0cca98bd889e49dd89b3993a6407bff5`, criado em **18/10/2026**. A auditoria registra 201 consultas em 26 temas. Para a amostra solicitada, foram considerados os temas com **20 artigos relevantes por consulta**: são 25 temas, com oito formulações/consultas por tema. O tema `rio_security_operation` fica fora desse recorte: possui uma consulta com 10 artigos relevantes.

### Consultas por tema

Cada um dos temas abaixo contribui com oito consultas, uma por formulação, totalizando 200 consultas únicas:

| Tema | Consultas |
|---|---:|
| `acordo_mercosul_uniao_europeia` | 8 |
| `banco_master` | 8 |
| `brics_rio_2025` | 8 |
| `cao_orelha` | 8 |
| `caso_benicio` | 8 |
| `concurso_nacional_unificado_2025` | 8 |
| `cop30_negociacoes` | 8 |
| `crise_venezuela_2026` | 8 |
| `dengue_brasil_2025_2026` | 8 |
| `descontos_inss` | 8 |
| `eleicoes_brasil_2026` | 8 |
| `enem_2025` | 8 |
| `gaza_2025_2026` | 8 |
| `gripe_aviaria_brasil` | 8 |
| `guerra_israel_ira_2025` | 8 |
| `imposto_renda_2026` | 8 |
| `julgamento_nucleo_golpe` | 8 |
| `juliana_marins` | 8 |
| `libertadores_2025` | 8 |
| `metanol_bebidas` | 8 |
| `mundial_clubes_2025` | 8 |
| `operacao_contencao` | 8 |
| `pix_brasil` | 8 |
| `queda_aviao_air_india_2025` | 8 |
| `tarifaco_eua_brasil` | 8 |
| **Total no recorte (25 temas)** | **200** |

### Consultas por formulação

Cada formulação ocorre uma vez em cada um dos 25 temas incluídos:

| Formulação | Consultas |
|---|---:|
| `baseline` (formulação-base) | 25 |
| `broad_theme` (tema amplo) | 25 |
| `information_request` (solicitação de informação) | 25 |
| `keyword` (palavra-chave) | 25 |
| `short_question` (pergunta curta) | 25 |
| `short_theme` (tema curto) | 25 |
| `specific_keywords` (palavras-chave específicas) | 25 |
| `specific_question` (pergunta específica) | 25 |
| **Total no recorte (8 formulações)** | **200** |

### Total e interpretação

- **Lote completo:** 26 temas e 201 consultas.
- **Temas com 20 artigos relevantes incluídos neste relatório:** 25.
- **Consultas únicas no recorte:** **200** (25 temas × 8 formulações).
- **Consultas por configuração:** cada uma das quatro configurações selecionadas cobre as mesmas 200 consultas.

| Configuração selecionada | Consultas |
|---|---:|
| Fusão RRF (`rrf`, independente de seed) | 200 |
| Ensemble RRF com seed HITS (`ensemble_rrf · hits`) | 200 |
| HITS ponderado + cross-encoder (configuração com fallback Louvain) | 200 |
| SALSA com seed Louvain (`graph_salsa · louvain`) | 200 |
| **Total de avaliações consulta–configuração** | **800** |

Assim, a avaliação filtrada engloba **200 consultas distintas** e **800 avaliações consulta–configuração** (4 configurações × 200 consultas). O total 800 conta cada consulta uma vez por configuração; não representa 800 perguntas diferentes.

## Fonte e escopo

Os totais do lote, a distribuição por tema e formulação, e a identificação do tema com 10 artigos relevantes vêm da auditoria da rodada em [`data_audit.md`](viz/data_audit.md). A descrição dos métodos segue as implementações em `src/services/search_pipeline.py` e `src/services/ranking.py`, além da referência de rankings e seeds no `README.md`.
