# Auditoria dos dados para visualização

## Identificação da rodada

- **Run ID:** `0cca98bd889e49dd89b3993a6407bff5`
- **Criada em:** 2026-10-18 13:50:01 UTC
- **Estado:** `completed`; 6.432/6.432 resultados persistidos
- **Snapshot de avaliações:** `994e4d6959b27e57`
- **Unidade de análise:** consulta dentro do tema; estatísticas principais por configuração de ranking/semente
- **Fonte:** `evaluation_runs`, `evaluation_run_results`, `evaluation_run_artifacts` e o snapshot imutável referenciado pela rodada. A consulta foi somente de leitura.

A rodada reúne 201 consultas em 26 temas, provenientes de snapshots atuais de `evals_additional_themes_2025_2026.json`, `evals_additional_themes_round2_2025_2026.json`, `evals_definitive_2025_2026.json` e `evals.json`. Vinte e cinco temas têm oito consultas cada; `rio_security_operation` tem uma. Duzentas consultas têm 20 URLs de referência e uma tem 10. Portanto, o tamanho do conjunto de referência não é constante. Oito formulações aparecem uma vez em cada um dos 25 temas maiores (25 consultas por formulação); a consulta de `rio_security_operation` está como `unspecified`.

Os identificadores de tema presentes são: `acordo_mercosul_uniao_europeia`, `eleicoes_brasil_2026`, `gripe_aviaria_brasil`, `guerra_israel_ira_2025`, `mundial_clubes_2025`, `brics_rio_2025`, `concurso_nacional_unificado_2025`, `crise_venezuela_2026`, `dengue_brasil_2025_2026`, `enem_2025`, `gaza_2025_2026`, `imposto_renda_2026`, `libertadores_2025`, `pix_brasil`, `queda_aviao_air_india_2025`, `banco_master`, `cao_orelha`, `caso_benicio`, `cop30_negociacoes`, `descontos_inss`, `julgamento_nucleo_golpe`, `juliana_marins`, `metanol_bebidas`, `operacao_contencao`, `tarifaco_eua_brasil` e `rio_security_operation`.

## Protocolo e esquema observado

- Busca: `search_version=stages_v9`, janela de publicação de 2025-06-01 a 2026-06-30.
- Unidade recuperada: `articles`; preset único `rapido` (`limit=1000`, `top_k=250`); quorum único `0.3`.
- Cada consulta tem oito rankings e quatro métodos de seed: `louvain`, `hits`, `ppr_top10` e `query_entities`. Foram gravadas 32 combinações ranking–seed por consulta.
- Rankings efetivamente presentes: `hybrid_max`, `rrf`, `cross_encoder`, `fused`, `graph_salsa`, `graph_fusion`, `graph_hits_cross_encoder` e `ensemble_rrf`.
- **Não** há linhas de ranking independentes `lexical`, `vector` ou `ppr` neste protocolo. Os campos de recuperação lexical/vetorial são diagnósticos do pool, não rankings de comparação separados.
- Cada linha inclui precisão, revocação e F1 em `k=1,3,5,10,20`; `MRR@20`; `MAP@5/10/20`; `NDCG@5/10/20`; `reference_pool_recall`; e métricas oráculo de precisão, revocação e F1 nos cinco cortes. Todos os 6.432 resultados têm esses campos.
- Tempos: `computation_seconds`, `retrieval_seconds`, `group_elapsed_seconds`; `step_timings` contém `ranking_seconds`, `graph_seconds`, `graph_article_fetch_seconds`, `graph_entity_load_extract_seconds`, `graph_assembly_seconds`, `graph_pruning_seconds`, `ppr_seconds`, `mmr_seconds` e `cross_encoder_seconds`. `retrieval_steps` contém `query_embedding_seconds`, `hybrid_query_seconds`, `result_processing_seconds`, `article_lookup_seconds` e `search_service_seconds`.
- Diagnósticos observados incluem contagens de candidatos/artigos/entidades/seeds, método efetivo de seed, correspondência e fallback de entidades da consulta, quorum efetivo, estado do limite de candidatos, campos do cross-encoder e parâmetros/métodos de grafo. Sua presença varia por método; valores ausentes não significam zero.

### Integridade e política de análise

Os 201 grupos de consulta têm exatamente 32 linhas e 32 combinações distintas ranking–seed, sem combinações duplicadas, ausentes ou incompletas. Ao deduplicar as repetições esperadas dos rankings independentes de seed (`hybrid_max`, `rrf`, `cross_encoder`), restam **4.623 observações consulta–configuração**: 23 configurações por consulta (três rankings independentes e cinco rankings dependentes de seed × quatro seeds). A deduplicação é analítica; as linhas originais permanecem no banco.

As comparações abaixo usam consultas pareadas e a política macro do gerador: média das consultas dentro de cada tema, seguida de média com peso igual entre os 26 temas. Os intervalos são percentis bootstrap de 95% sobre **26 temas**, com 1.000 reamostragens; são descritivos, não testes de significância. O tema com uma consulta conta como uma unidade de reamostragem e deve ser destacado como tal.

## Variação de parâmetros e limites dos dados

Há apenas um preset e um quorum; não há variação de `top_k` nem de `limit`. Os diagnósticos registram um único valor para `graph_alpha=0.85`, `graph_hop_decay=0.5`, `graph_fusion_rrf_k=60` e `graph_mix=0.3`. **Não há sweep** de alpha, peso RRF ou mix. A documentação do projeto também descreve `graph_fusion` como RRF com `rrf_k=60`; `graph_mix` não deve ser interpretado como um peso experimental neste run.

Todos os resultados são `mode=ranking`, `stage=ppr`. Há métricas e contagens de diagnóstico da execução, mas não há exportação de nós/arestas nem observações de grau, tamanho de comunidades ou traço de convergência. Assim, esta rodada não sustenta CCDF de graus, distribuição de tamanhos Louvain ou curva de convergência. Também não é uma avaliação GDELT nem uma série temporal de artigos.

## Estatísticas descritivas e resultados observados

### Distribuição de F1@20 por consulta

Valores abaixo são média, desvio-padrão amostral, mínimo, máximo e assimetria entre **201 consultas** para configurações representativas. São descritivos por consulta e não substituem a média macro por tema usada na comparação principal.

| Ranking · seed | n | Média | DP | Mín. | Máx. | Assimetria |
|---|---:|---:|---:|---:|---:|---:|
| `hybrid_max` · independente | 201 | 0,2338 | 0,1636 | 0,000 | 0,700 | 0,602 |
| `rrf` · independente | 201 | 0,2348 | 0,1635 | 0,000 | 0,700 | 0,609 |
| `cross_encoder` · independente | 201 | 0,2237 | 0,1518 | 0,000 | 0,650 | 0,618 |
| `ensemble_rrf` · `louvain` | 201 | 0,2391 | 0,1518 | 0,000 | 0,650 | 0,479 |
| `graph_fusion` · `query_entities` | 201 | 0,1928 | 0,1335 | 0,000 | 0,650 | 0,700 |
| `graph_salsa` · `query_entities` | 201 | 0,1098 | 0,0896 | 0,000 | 0,400 | 0,676 |

`MRR@20` varia de 0 a 1; nas configurações principais seu DP fica aproximadamente entre 0,27 e 0,39, com assimetria positiva mais forte em `graph_salsa`. `NDCG@20` também tem mínimo 0; os máximos das configurações representativas ficam entre 0,30 e 0,76. Consulte os dados normalizados do gerador para estatísticas por configuração de todos os cortes; não agregue as 6.432 linhas como observações independentes.

### Médias macro por tema e incerteza descritiva

| Ranking · seed | F1@20 (IC bootstrap 95%) | MRR@20 (IC bootstrap 95%) | NDCG@20 (IC bootstrap 95%) |
|---|---:|---:|---:|
| `hybrid_max` · independente | 0,2304 (0,1805–0,2855) | 0,5265 (0,4281–0,6329) | 0,2552 (0,1999–0,3159) |
| `rrf` · independente | 0,2337 (0,1829–0,2880) | 0,5220 (0,4259–0,6263) | 0,2560 (0,2044–0,3173) |
| `cross_encoder` · independente | 0,2184 (0,1705–0,2657) | 0,5543 (0,4575–0,6525) | 0,2510 (0,1972–0,3081) |
| `ensemble_rrf` · `louvain` | 0,2377 (0,1904–0,2865) | 0,4854 (0,3967–0,5802) | 0,2528 (0,2048–0,3051) |
| `ensemble_rrf` · `query_entities` | 0,2358 (0,1916–0,2834) | 0,4961 (0,4018–0,5914) | 0,2536 (0,2064–0,3040) |
| `graph_fusion` · `query_entities` | 0,1930 (0,1567–0,2330) | 0,4101 (0,3208–0,5127) | 0,2029 (0,1636–0,2460) |
| `graph_hits_cross_encoder` · `louvain` | 0,1837 (0,1493–0,2184) | 0,4845 (0,3920–0,5759) | 0,2097 (0,1720–0,2477) |
| `graph_salsa` · `query_entities` | 0,1083 (0,0804–0,1387) | 0,2314 (0,1597–0,3117) | 0,1048 (0,0769–0,1317) |

`rrf` e `hybrid_max` têm resultados próximos em F1@20/NDCG@20. `ensemble_rrf` com seed `louvain` tem o maior ponto estimado de F1@20 entre as configurações deste run, mas a diferença macro pareada contra `hybrid_max` é pequena (+0,0074). `cross_encoder` tem maior MRR@20 entre as três baselines medidas, mas ponto estimado menor em F1@20. Os rankings de grafo isolados listados acima ficam abaixo de `hybrid_max` nos três pontos estimados; isso é evidência descritiva deste run, não uma conclusão inferencial.

### Cobertura versus qualidade do ranking

O `reference_pool_recall` é idêntico entre rankings para cada consulta porque os rankings compartilham o pool recuperado. Sua média macro por tema é **0,7654** (bootstrap descritivo de 95%: 0,6933–0,8402). O F1@20 oráculo dentro do pool tem média macro **0,7590** (0,6796–0,8390). Esses valores são teto/cobertura do pool, não qualidade do ranking nem desempenho no corpus completo. A diferença em relação aos F1@20 dos rankings indica espaço de ordenação dentro do pool.

### Diferenças pareadas contra `hybrid_max`

Todas as diferenças abaixo usam os mesmos 201 IDs de consulta; a estatística é a média das diferenças dentro de cada tema e, depois, média igual entre temas. Valores exatos para estas e demais configurações devem permanecer em tabela/CSV junto às figuras.

| Ranking · seed | Pares | Δ F1@20 | Δ MRR@20 | Δ NDCG@20 |
|---|---:|---:|---:|---:|
| `rrf` · independente | 201 | +0,0033 | −0,0045 | +0,0008 |
| `cross_encoder` · independente | 201 | −0,0119 | +0,0279 | −0,0042 |
| `ensemble_rrf` · `louvain` | 201 | +0,0074 | −0,0411 | −0,0025 |
| `ensemble_rrf` · `query_entities` | 201 | +0,0055 | −0,0304 | −0,0016 |
| `graph_fusion` · `query_entities` | 201 | −0,0373 | −0,1163 | −0,0524 |
| `graph_salsa` · `query_entities` | 201 | −0,1220 | −0,2951 | −0,1504 |

Não interpretar os intervalos bootstrap como testes de hipótese. Não há motivo para afirmar significância com base em sobreposição ou não sobreposição visual dos intervalos.

### Tempos e diagnósticos

- `computation_seconds` é tempo de cálculo do ranking, não latência total. Para `cross_encoder`, a média por consulta é 58,26 s (DP 13,83; mínimo 30,96; máximo 93,97; assimetria 0,56). A amplitude entre configurações vai de milissegundos a mais de 100 s, portanto um gráfico runtime–qualidade provavelmente precisará de eixo logarítmico e deve nomear precisamente a métrica.
- `retrieval_seconds` é separado e compartilhado entre rankings na consulta: após deduplicar para 201 recuperações, média 80,99 s, DP 165,72, mediana 21,72, mínimo 1,16, máximo 848,48 e assimetria 3,07. Isso não deve ser somado às linhas repetidas por ranking nem confundido com `computation_seconds`.
- `group_elapsed_seconds` também é informação de grupo repetida nas linhas de ranking; contar uma vez por consulta/preset/quorum/unidade. `step_timings` são componentes aninhados e não devem ser somados como tempos disjuntos.
- Há diagnósticos de correspondência de entidades, fallback, seeds e contagens do grafo em subconjuntos de linhas. Eles permitem uma figura de diagnóstico por consulta/configuração se a deduplicação for correta, mas não representam distribuição topológica de nós/arestas.

## Estratégia de figuras sustentada por este run

1. **Composição da avaliação:** mostrar os 26 temas, formulações e tamanhos de referência. Evidenciar que há um tema com uma consulta e 10 referências, enquanto os outros têm oito consultas e 20 referências.
2. **Cobertura e teto do pool:** separar `reference_pool_recall` e F1@20 do oráculo; mostrar pontos de consulta e `n`, deixando explícito que pool/coverage não é ranking.
3. **Qualidade:** dot/interval plot por configuração para F1@20, MRR@20 e NDCG@20, com média macro por tema, IC bootstrap sobre 26 temas e contagem de consultas/temas. Destacar apenas baselines observadas e um subconjunto legível; manter apêndice/tabela completa para as 23 configurações.
4. **Comparação de componentes e seeds:** diferenças pareadas contra `hybrid_max` com linha zero, número de pares e tabela CSV; facetar métodos de seed nos rankings que realmente dependem de seed. Não repetir os rankings independentes como quatro observações.
5. **Cortes:** curvas em `k=1,3,5,10,20` são sustentadas pelas métricas armazenadas; preservar consulta/tema como unidade e evitar sobrecarregar as curvas com todas as 23 configurações.
6. **Runtime–qualidade:** separar tempo de ranking de tempo de recuperação. Para comparação baseada em `computation_seconds`, usar escala logarítmica dada a amplitude observada, marcar pontos individuais ou configuração resumida e incluir uma tabela de tempos.
7. **Diagnósticos do grafo:** pontos por consulta para entidade detectada/correspondida, fallback e contagens observadas, com amostras e valores ausentes visíveis. Não chamar contagens de nós/arestas de distribuição de grau ou comunidade.

Rótulos de figuras em português brasileiro. Manter identificadores crus e definições do protocolo nos manifestos/tabelas. Saídas PDF/SVG e PNG a 300 DPI são adequadas; dimensionamento deve oferecer presets configuráveis de coluna e largura completa.
