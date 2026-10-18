# Casos adicionais de relevância — 2025/2026

2 temas adicionais, com **20 artigos ordenados por tema e 40 URLs distintas**. Seleção editorial assistida por IA, não ground truth exaustiva nem revisão humana independente.

## Método e limites

- Pesquisa realizada em 2026-10-15.
- Fonte exclusiva: `g1_articles`, consultada em transação somente de leitura. Nenhuma busca web ou ranking da aplicação foi utilizado.
- Janela inclusiva: `2025-06-01` a `2026-05-20`, por `date_published`. Publicações fora do corpus não foram incluídas.
- Necessidade informacional: compreender uma história continuada, suas causas, evidências, marcos, contrapontos e consequências.
- Descoberta dirigida por candidatos antes não curados no relatório original. Busca de títulos por expressões regulares; contagens incluem ruído e não medem relevância.
- Leitura dirigida do início e de passagens específicas do corpo, não leitura integral de todos os candidatos. Vídeos e áudios não foram assistidos; somente o texto armazenado foi julgado.
- A prioridade é editorial, não cronológica: síntese, mecanismo, marcos e limites probatórios vêm antes de detalhes adicionais. Todos os 20 documentos selecionados são positivos.
- Ausência na seleção significa não julgado, não necessariamente irrelevante. Há sobreposição factual entre sínteses e notícias de marcos; corpos idênticos foram excluídos.
- Datas, URLs primárias, presença do corpo, unicidade e literalidade das evidências foram verificadas no banco. Hashes registram a versão do texto consultado, não prova externa de veracidade.
- A seleção não foi otimizada pelos resultados de nenhum método de busca. Não houve teste de desempenho dessas consultas nesta curadoria.

## Arquivos para avaliação

- `evals_additional_round2_curated_2025_2026.json`: 2 consultas completas, uma por tema.
- `evals_additional_round2_query_variants_2025_2026.json`: 16 consultas, com as mesmas oito estruturas usadas na avaliação anterior, intercaladas por estilo.
- `relevance_additional_round2_selection_2025_2026.json`: justificativas, evidências literais, datas e hashes por artigo.
- Em cada tema, todas as estruturas usam exatamente as mesmas 20 URLs na mesma ordem. Prefixos de tamanho 1/3/5/10/20 são aninhados.
- Atenção: o avaliador atual compara em k com `relevant_urls[:k]`; isso não é recall contra os 20 positivos fixos em todos os cortes. A curadoria não altera essa regra.

## Visão geral

| Tema | Candidatos com corpo >200 caracteres | Intervalo selecionado | Datas / meses distintos |
|---|---:|---|---:|
| Operação Contenção: ação na Penha/Alemão e apuração das mortes | 119 | 2025-10-28 a 2026-04-02 | 14 / 5 |
| Trama golpista: julgamento e execução das penas do núcleo crucial | 649 | 2025-06-11 a 2026-04-30 | 16 / 10 |

## Operação Contenção: ação na Penha/Alemão e apuração das mortes

**ID:** `operacao_contencao`

**Consulta completa:** O que aconteceu na Operação Contenção de 28 de outubro de 2025 nos complexos da Penha e do Alemão, quais foram as consequências e como evoluíram as investigações e o controle das provas?

**Delimitação:** Megaoperação de 28/10/2025 nos complexos da Penha e do Alemão, planejamento, impacto coletivo, preservação de provas e controle judicial. Exclui outras incursões chamadas Contenção, obras de contenção, perfis de mortos e reações sem evidência central.

**Cautelas:** Os balanços de mortos, presos e armas variam ao longo das atualizações; não somar números de reportagens distintas. Antecedentes ou classificação policial não provam autoria nem justificam cada morte. Federalização foi solicitada, não confirmada. Denúncias do MPRJ contra policiais não são condenações, nem prova automática de execução de todas as vítimas. Uma fala sobre efeito ínfimo foi expressamente descrita pela PM como opinião pessoal. A checagem distingue vídeos antigos de outras operações dos registros desta ação. O corpo do explicador do Muro do Bope tem um lapso 'terça-feira (29)'; o evento aqui delimitado é o de 28/10. Conteúdos retratam o texto armazenado, não um snapshot garantidamente congelado na data de publicação.

**Hash do conjunto consultado:** `ae21fb9e0569ab90faaca276c9d5ebd97bee9bdba0be6e199186f81e694063cf`

### operacao_contencao — Relevância 01

**2025-10-30 — [O que se sabe e o que falta esclarecer sobre a megaoperação no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/10/30/o-que-se-sabe-e-o-que-falta-esclarecer-sobre-a-megaoperacao-nos-complexos-do-alemao-e-penha.ghtml)**

**Motivo:** Síntese de fatos e lacunas centrais, com posições oficiais e cobranças de transparência.

**Evidência no corpo:** “Entre as muitas perguntas sem resposta estão: o que aconteceu com as gravações das câmeras policiais, como se deu o chamado “muro do Bope”, de que forma ocorreram as mortes na mata e quem eram, de fato, as vítimas.”

### operacao_contencao — Relevância 02

**2025-10-29 — [INFOGRÁFICO: número de mortos, localização e impactos da megaoperação contra o CV no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/10/29/infografico-megaoperacao-rio.ghtml)**

**Motivo:** Panorama textual de escala, localização e impactos; não depende da leitura do infográfico.

**Evidência no corpo:** “mobilizou 2,5 mil agentes civis e militares e provocou bloqueios em vias, suspensão de aulas em 83 escolas e paralisação de linhas ônibus.”

### operacao_contencao — Relevância 03

**2025-10-29 — ['Muro do Bope': entenda estratégia da polícia em megaoperação no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/10/29/muro-do-bope-entenda-estrategia-da-policia-em-megaoperacao-mais-letal-do-rio-de-janeiro.ghtml)**

**Motivo:** Explica o mecanismo tático conforme a versão do secretário, sem tratá-lo como reconstituição pericial independente.

**Evidência no corpo:** “policiais entraram pela área da Serra da Misericórdia para cercar os criminosos e empurrá-los em direção à mata”

### operacao_contencao — Relevância 04

**2025-11-10 — [Megaoperação no Rio: Moraes aponta contradições e determina envio de laudos e dados de prisões | G1](https://g1.globo.com/politica/noticia/2025/11/10/megaoperacao-no-rio-moraes-aponta-contradicoes-e-pede-relatorios-sobre-prisoes-e-mandados.ghtml)**

**Motivo:** Marco de fiscalização judicial: contradições nos números e exigências de documentos e provas.

**Evidência no corpo:** “o ministro apontou que há divergências entre as informações divulgadas pelo governo estadual, por meio da Secretaria de Segurança Pública, e de outros órgãos, como o Ministério Público.”

### operacao_contencao — Relevância 05

**2026-04-02 — [Megaoperação Contenção: PGR pede ao STF laudos das 122 mortes | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2026/04/02/pgr-vai-ao-supremo-por-acesso-aos-laudos-das-mortes-da-megaoperacao-contencao.ghtml)**

**Motivo:** Desdobramento de abril de 2026 mostra que acesso aos laudos e cadeia de custódia permaneciam em discussão.

**Evidência no corpo:** “A Secretaria de Segurança Pública do RJ informou que todos os dados solicitados, como laudos e imagens, já foram encaminhados ao STF.”

### operacao_contencao — Relevância 06

**2025-10-29 — [Operação contra o Comando Vermelho: corpos encontrados na mata são levados para a Praça da Penha; número oficial de mortos salta para 121 | G1](https://g1.globo.com/jornal-nacional/noticia/2025/10/29/operacao-contra-o-comando-vermelho-corpos-encontrados-na-mata-sao-levados-para-a-praca-da-penha-numero-oficial-de-mortos-salta-para-121.ghtml)**

**Motivo:** Marco da descoberta de corpos na mata e revisão do balanço, com consequências para moradores.

**Evidência no corpo:** “Moradores das comunidades da região do Alemão e da Penha resgataram corpos da mata onde houve o principal confronto.”

### operacao_contencao — Relevância 07

**2025-11-18 — [Megaoperação na Penha e Alemão: Relatório ao STF tem divergências | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/11/18/relatorio-megaoperacao-governo-rj-ao-stf.ghtml)**

**Motivo:** Compara balanços públicos com documento entregue ao STF, em vez de assumir que as contagens são estáveis.

**Evidência no corpo:** “apresentou divergências nos números de presos e apreensões em relação ao divulgado.”

### operacao_contencao — Relevância 08

**2025-12-02 — [MPRJ denuncia PMs por crimes na Megaoperação Contenção | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/12/02/mprj-oferece-novas-denuncias-contra-policiais-militares-por-crimes-na-megaoperacao-contencao.ghtml)**

**Motivo:** Responsabilização criminal concreta de agentes por atos registrados nas câmeras; acusação ainda não é condenação.

**Evidência no corpo:** “Os delitos foram registrados pelas câmeras operacionais portáteis utilizadas pelos próprios agentes.”

### operacao_contencao — Relevância 09

**2025-12-19 — [MPF pede federalização de megaoperação no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/12/19/mpf-pede-federalizacao-das-investigacoes-da-megaoperacao-no-rio.ghtml)**

**Motivo:** Explica o pedido excepcional de deslocamento de competência e suas condições institucionais.

**Evidência no corpo:** “Caso o PGR endosse a solicitação, caberá ao Superior Tribunal de Justiça (STJ) decidir ou não pela federalização do caso.”

### operacao_contencao — Relevância 10

**2025-11-07 — [Megaoperação no Rio: MPF acompanhará investigação | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/11/07/conselho-libera-mpf-para-acompanhar-investigacao-sobre-megaoperacao-no-rio.ghtml)**

**Motivo:** Diferencia acompanhamento do MPF e disputa de competência, anterior ao pedido de federalização.

**Evidência no corpo:** “A medida reverte uma liminar anterior que havia restringido a participação do MPF”

### operacao_contencao — Relevância 11

**2026-02-05 — [Moraes manda governo do Rio enviar imagens de megaoperação no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2026/02/05/moraes-manda-governo-do-rj-enviar-imagens-de-megaoperacao.ghtml)**

**Motivo:** Ordem posterior de remessa das imagens para perícia e cobrança sobre controle externo da atividade policial.

**Evidência no corpo:** “o material seja encaminhado para perícia, com transcrição e elaboração de laudo técnico, e encaminhado ao Supremo.”

### operacao_contencao — Relevância 12

**2025-10-31 — [Polícia identifica 109 mortos em megaoperação no Rio e afirma que 78 tinham ficha criminal | G1](https://g1.globo.com/jornal-nacional/noticia/2025/10/31/policia-identifica-109-mortos-em-megaoperacao-no-rio-e-afirma-que-78-tinham-ficha-criminal.ghtml)**

**Motivo:** Documenta o que a polícia divulgou sobre identificação e antecedentes, sem estender essa classificação a todos os mortos.

**Evidência no corpo:** “Segundo as autoridades de segurança do estado, dos 117 suspeitos mortos, 109 foram identificados”

### operacao_contencao — Relevância 13

**2025-11-03 — [Cláudio Castro diz a Alexandre de Moraes que megaoperação no Rio seguiu determinações do Supremo | G1](https://g1.globo.com/jornal-nacional/noticia/2025/11/03/claudio-castro-diz-a-alexandre-de-moraes-que-megaoperacao-no-rio-seguiu-determinacoes-do-supremo.ghtml)**

**Motivo:** Contraponto do governo estadual e contexto dos protocolos da ADPF das Favelas.

**Evidência no corpo:** “Cláudio Castro afirmou que a megaoperação da semana passada contra o Comando Vermelho respeitou as determinações do STF.”

### operacao_contencao — Relevância 14

**2025-10-29 — [Megaoperação no Rio: PF cita contato, mas decidiu não participar | G1](https://g1.globo.com/politica/noticia/2025/10/29/megaoperacao-diretor-da-pf-cita-contato-de-forcas-do-rio-mas-avaliacao-foi-de-que-operacao-nao-era-razoavel.ghtml)**

**Motivo:** Versão federal sobre os contatos operacionais e a decisão de não participar, sem confundir com apoio posterior à perícia.

**Evidência no corpo:** “a avaliação da direção regional da PF foi de que a operação "não era razoável"”

### operacao_contencao — Relevância 15

**2025-10-28 — [Megaoperação no Rio: Ministério da Justiça diz que tem atendido a todos pedidos do governo estadual | G1](https://g1.globo.com/politica/noticia/2025/10/28/nota-mj-operacao-rio-de-janeiro.ghtml)**

**Motivo:** Registra a divergência sobre pedidos de apoio e o histórico da Força Nacional no estado.

**Evidência no corpo:** “A pasta também afirma que atendeu a todos os 11 pedidos de renovação feitos pelo governo do Rio”

### operacao_contencao — Relevância 16

**2025-10-30 — [Megaoperação no Alemão: Lewandowski envia peritos da PF ao RJ | G1](https://g1.globo.com/politica/blog/andreia-sadi/post/2025/10/30/entrevista-ricardo-lewandowski-megaoperacao-estudio-i.ghtml)**

**Motivo:** Medida concreta de reforço técnico federal para identificação de corpos e exames periciais.

**Evidência no corpo:** “20 peritos da Polícia Federal (PF) ao Rio de Janeiro para auxiliar nas investigações e perícias”

### operacao_contencao — Relevância 17

**2025-11-06 — [Megaoperação no Rio teve efeito 'ínfimo' sobre o CV, diz PM | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/11/06/subsecretario-inteligencia-pm-rj-reuniao-megaoperacao-congresso.ghtml)**

**Motivo:** Questiona eficácia estratégica da ação e inclui a ressalva institucional da própria PM.

**Evidência no corpo:** “a fala "não representa o posicionamento institucional da Corporação, tratando-se de opinião de caráter pessoal"”

### operacao_contencao — Relevância 18

**2025-10-29 — [Veja o que está funcionando no dia seguinte a megaoperação no Rio | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/10/29/comercio-universidades-inss-veja-o-que-esta-funcionando-no-dia-seguinte-a-megaoperacao-no-rio.ghtml)**

**Motivo:** Impactos coletivos em educação, trabalho e serviços no dia seguinte, além do balanço policial.

**Evidência no corpo:** “o comércio, o INSS e instituições de ensino do Rio modificaram o funcionamento nesta quarta (29), suspendendo atividades presenciais ou adotando o trabalho remoto”

### operacao_contencao — Relevância 19

**2025-11-22 — [Morre quinto policial baleado na megaoperação contra o Comando Vermelho, em outubro, no Rio | G1](https://g1.globo.com/jornal-nacional/noticia/2025/11/22/morre-quinto-policial-baleado-na-megaoperacao-contra-o-comando-vermelho-em-outubro-no-rio.ghtml)**

**Motivo:** Atualiza consequência humana e composição do balanço após a operação, não como perfil biográfico.

**Evidência no corpo:** “Morreu, neste sábado (22), o quinto policial baleado na megaoperação contra o Comando Vermelho, em outubro, no Rio de Janeiro.”

### operacao_contencao — Relevância 20

**2025-10-28 — [Veja o que é #FATO ou #FAKE sobre a megaoperação no Rio de Janeiro | G1](https://g1.globo.com/fato-ou-fake/noticia/2025/10/28/veja-o-que-e-fato-ou-fake-sobre-a-megaoperacao-no-rio-de-janeiro.ghtml)**

**Motivo:** Controle de desinformação: evita usar imagens de outras ações ou geradas por IA como prova desta operação.

**Evidência no corpo:** “É #FAKE que vídeo de PMs do Bope furtando casas tenha ocorrido nesta terça-feira; vídeo é antigo e mostra outra operação”


## Trama golpista: julgamento e execução das penas do núcleo crucial

**ID:** `julgamento_nucleo_golpe`

**Consulta completa:** Como evoluiu a ação penal contra Bolsonaro e os sete integrantes do núcleo crucial da trama golpista, quais foram os fundamentos da condenação e o que aconteceu com os recursos, a execução das penas e a proposta de dosimetria?

**Delimitação:** Ação penal do núcleo crucial, com Bolsonaro e sete aliados: acusação, defesa, votos, condenação, recursos, execução e consequências funcionais/legislativas. Exclui os demais núcleos como histórias autônomas, outras condenações de Bolsonaro, manifestações, sanções estrangeiras e comentário eleitoral incidental.

**Cautelas:** Distinguir indiciamento, pedido da PGR, voto individual, julgamento colegiado e trânsito em julgado. A prisão preventiva de novembro de 2025 não se confunde com execução da condenação iniciada depois. Mauro Cid tem calendário e regime próprios. A posição de Fux é divergência, não resultado final. Pedidos de perda de patente não são expulsões já consumadas. O veto de janeiro ao PL da Dosimetria foi derrubado em abril; no texto de abril a promulgação/publicação e revisão das penas ainda eram etapas subsequentes, não redução automática nem soltura. O artigo de condenação do JN contém um lapso ao chamar de quarta-feira (11) a véspera: a data do resultado selecionado é 11/09/2025.

**Hash do conjunto consultado:** `a1e865594f6f8081f912a95ed154fa8f311045b28ce8a77582e0db6255473cf1`

### julgamento_nucleo_golpe — Relevância 01

**2025-11-25 — [Bolsonaro preso: veja os principais pontos da condenação | G1](https://g1.globo.com/politica/noticia/2025/11/25/lideranca-de-bolsonaro-ligacao-com-8-de-janeiro-relembre-os-principais-pontos-da-condenacao.ghtml)**

**Motivo:** Síntese da condenação e do estágio de execução, com composição do núcleo e situação distinta do delator.

**Evidência no corpo:** “o relator Alexandre de Moraes declarou que não cabem mais recursos no caso e abriu caminho para a execução das penas na prisão.”

### julgamento_nucleo_golpe — Relevância 02

**2025-09-11 — [Primeira Turma do STF condena Bolsonaro por tentativa de golpe de Estado e mais 4 crimes a 27 anos e 3 meses de prisão | G1](https://g1.globo.com/jornal-nacional/noticia/2025/09/11/primeira-turma-do-stf-condena-bolsonaro-por-tentativa-de-golpe-de-estado-e-mais-4-crimes-a-um-total-de-27-anos-e-3-meses-de-prisao.ghtml)**

**Motivo:** Marco do julgamento colegiado, maioria formada e divergência, distinguindo resultado de votos anteriores.

**Evidência no corpo:** “acompanharam o relator Alexandre de Moraes e o ministro Flávio Dino pela condenação de Bolsonaro e dos outros réus do núcleo crucial da trama golpista.”

### julgamento_nucleo_golpe — Relevância 03

**2025-09-01 — [JN mostra quais são as acusações e o que dizem as defesas do núcleo crucial da trama golpista | G1](https://g1.globo.com/jornal-nacional/noticia/2025/09/01/jn-mostra-quais-sao-as-acusacoes-e-o-que-dizem-as-defesas-do-nucleo-crucial-da-trama-golpista.ghtml)**

**Motivo:** Expõe os papéis individuais e o material da acusação ao lado das respostas defensivas antes do julgamento.

**Evidência no corpo:** “o procurador-geral da República listou manuscritos, gravações, troca de mensagens eletrônicas, planilhas e arquivos digitais apreendidos pela Polícia Federal.”

### julgamento_nucleo_golpe — Relevância 04

**2025-11-25 — [Moraes declara sentenças definitivas em ação por tentativa de golpe e determina começo das execuções das penas de Bolsonaro e outros seis | G1](https://g1.globo.com/politica/noticia/2025/11/25/moraes-declara-sentencas-definitivas-em-acao-por-tentativa-de-golpe-e-determina-comeco-das-execucoes-das-penas.ghtml)**

**Motivo:** Marco processual da execução e fundamento da inadmissibilidade de novos recursos, diferente da preventiva anterior.

**Evidência no corpo:** “Moraes decidiu que o ex-presidente deverá cumprir a sentença na Superintendência Regional da Polícia Federal do Distrito Federal, onde Bolsonaro já está em prisão preventiva desde sábado.”

### julgamento_nucleo_golpe — Relevância 05

**2026-04-30 — [PL da Dosimetria: Congresso derruba veto de Lula e beneficia Bolsonaro; texto segue para promulgação | G1](https://g1.globo.com/politica/noticia/2026/04/30/pl-da-dosimetria-camara-veto.ghtml)**

**Motivo:** Atualização legislativa do fim do recorte: derrubada do veto e passos ainda necessários para vigência.

**Evidência no corpo:** “Após a promulgação e publicação oficial, a nova regra passa a valer.”

### julgamento_nucleo_golpe — Relevância 06

**2025-09-09 — [Em voto para condenar Bolsonaro e mais 7 réus, Moraes cita fatos que visaram a impedir posse de Lula ou executar golpe de Estado | G1](https://g1.globo.com/jornal-nacional/noticia/2025/09/09/em-voto-para-condenar-bolsonaro-e-mais-7-reus-moraes-cita-fatos-que-visaram-a-impedir-posse-de-lula-ou-executar-golpe-de-estado.ghtml)**

**Motivo:** Fundamentos do relator e discussão sobre autonomia dos crimes; voto atribuído e não substituto do acórdão.

**Evidência no corpo:** “os crimes de tentativa de golpe de Estado e de abolição violenta do Estado Democrático de Direito devem ser punidos separadamente e não podem ser unificados.”

### julgamento_nucleo_golpe — Relevância 07

**2025-09-11 — [Saiba penas que a Primeira Turma do STF impôs a Bolsonaro e 7 aliados condenados por tentativa de golpe de Estado | G1](https://g1.globo.com/jornal-nacional/noticia/2025/09/11/saiba-penas-que-a-primeira-turma-do-stf-impos-a-bolsonaro-e-7-aliados-condenados-por-tentativa-de-golpe.ghtml)**

**Motivo:** Detalha as penas e regimes individuais e explica por que a condenação de setembro não iniciou automaticamente a execução.

**Evidência no corpo:** “O Supremo entende que o cumprimento da pena só começa quando forem esgotados os recursos.”

### julgamento_nucleo_golpe — Relevância 08

**2025-08-15 — [Como começou investigação da trama golpista que levou a julgamento de Bolsonaro? | G1](https://g1.globo.com/politica/noticia/2025/08/15/julgamento-de-bolsonaro-relembre-a-investigacao-e-o-comeco-do-processo-no-stf-sobre-a-trama-golpista.ghtml)**

**Motivo:** Cronologia dos antecedentes probatórios e da divisão processual, apesar de a publicação estar dentro da janela de 2025.

**Evidência no corpo:** “O g1 relembra as principais fases da investigação e do processo penal.”

### julgamento_nucleo_golpe — Relevância 09

**2025-06-11 — [Minuta, 'Punhal Verde e Amarelo' e reuniões: o que os réus disseram sobre os pontos-chave da ação sobre tentativa de golpe | G1](https://g1.globo.com/politica/noticia/2025/06/11/minuta-punhal-verde-e-amarelo-e-reunioes-o-que-os-reus-disseram-sobre-os-principais-pontos-da-acao-sobre-tentativa-de-golpe.ghtml)**

**Motivo:** Compara depoimentos sobre minuta, reuniões e planos, registrando divergências entre réus.

**Evidência no corpo:** “A Primeira Turma do Supremo Tribunal Federal encerrou nesta terça-feira (10) o interrogatório dos oitos réus do chamado "núcleo crucial" da trama golpista.”

### julgamento_nucleo_golpe — Relevância 10

**2025-09-10 — [Fux vota para absolver Bolsonaro no julgamento da trama golpista; placar está em 2 a 1 pela condenação | G1](https://g1.globo.com/jornal-nacional/noticia/2025/09/10/fux-vota-para-absolver-bolsonaro-no-julgamento-da-trama-golpista-placar-esta-em-2-a-1-pela-condenacao.ghtml)**

**Motivo:** Contraponto jurisdicional central: fundamentos da divergência absolutória de Fux.

**Evidência no corpo:** “Fux concluiu a análise da denúncia contra Jair Bolsonaro e absolveu o ex-presidente dos cinco crimes.”

### julgamento_nucleo_golpe — Relevância 11

**2025-07-15 — [PGR pede condenação de Bolsonaro por tentativa de golpe de Estado | G1](https://g1.globo.com/politica/noticia/2025/07/15/pgr-pede-condenacao-de-bolsonaro-por-tentativa-de-golpe-de-estado.ghtml)**

**Motivo:** Alegações finais da acusação e tipificação, como pedido anterior à decisão judicial.

**Evidência no corpo:** “As acusações fazem parte das alegações finais apresentadas na ação penal que apura a tentativa de ruptura institucional planejada pelo núcleo próximo ao ex-presidente.”

### julgamento_nucleo_golpe — Relevância 12

**2025-08-14 — [STF recebe alegações finais das defesas de Bolsonaro e mais seis réus do ‘núcleo crucial’ da tentativa de golpe | G1](https://g1.globo.com/jornal-nacional/noticia/2025/08/14/stf-recebe-alegacoes-finais-das-defesas-de-bolsonaro-e-mais-seis-reus-do-nucleo-crucial-da-tentativa-de-golpe.ghtml)**

**Motivo:** Argumentos específicos das defesas e distinção da imputação contra Ramagem.

**Evidência no corpo:** “Todos alegaram inocência.”

### julgamento_nucleo_golpe — Relevância 13

**2025-11-08 — [STF mantém condenação de Bolsonaro e seis réus na tentativa de golpe; veja perguntas e respostas | G1](https://g1.globo.com/politica/noticia/2025/11/08/stf-mantem-condenacao-de-bolsonaro-e-seis-reus-na-tentativa-de-golpe-veja-perguntas-e-respostas.ghtml)**

**Motivo:** Explica rejeição dos primeiros embargos, limites recursais e o calendário ainda aberto naquele momento.

**Evidência no corpo:** “Como ainda há possibilidade de novos recursos, as penas não podem ser executadas neste momento.”

### julgamento_nucleo_golpe — Relevância 14

**2025-10-30 — [Após defesa não apresentar recurso, Moraes determina início do cumprimento da pena de Mauro Cid por tentativa de golpe | G1](https://g1.globo.com/politica/noticia/2025/10/30/apos-defesa-nao-apresentar-recurso-moraes-determina-inicio-do-cumprimento-da-pena-de-cid.ghtml)**

**Motivo:** Demonstra por que a execução começou antes para o delator e com regime diferente dos demais condenados.

**Evidência no corpo:** “Mauro Cid foi o único entre os 8 réus do núcleo crucial da trama golpista que não apresentou os chamados embargos de declaração”

### julgamento_nucleo_golpe — Relevância 15

**2025-11-25 — [Trama golpista: veja o que disseram as defesas dos réus após Moraes ordenar o início do cumprimento de penas | G1](https://g1.globo.com/politica/noticia/2025/11/25/trama-golpista-veja-o-que-disseram-as-defesas-dos-reus-apos-moraes-ordenar-o-inicio-do-cumprimento-de-penas.ghtml)**

**Motivo:** Contraponto das defesas ao trânsito em julgado e à inadmissibilidade recursal, sem assumir que as teses foram acolhidas.

**Evidência no corpo:** “a defesa ajuizará no curso do prazo estabelecido pelo regimento, o recurso que entende cabível.”

### julgamento_nucleo_golpe — Relevância 16

**2026-02-03 — [STM vai analisar pedidos de perda de postos e patentes de Bolsonaro e réus militares; veja perguntas e respostas | G1](https://g1.globo.com/politica/noticia/2026/02/03/stm-vai-analisar-pedidos-de-perda-de-postos-e-patentes-de-bolsonaro-e-reus-militares-veja-perguntas-e-respostas.ghtml)**

**Motivo:** Consequência institucional militar e procedimento distinto da revisão das condenações penais.

**Evidência no corpo:** “a Justiça Militar não vai reavaliar as penas aplicadas, mas verificar se a condenação penal torna a situação do grupo incompatível com a carreira militar.”

### julgamento_nucleo_golpe — Relevância 17

**2025-12-03 — [Ministério da Justiça demite Ramagem e Anderson Torres da PF, condenados por tentativa de golpe | G1](https://g1.globo.com/politica/noticia/2025/12/03/pf-demite-alexandre-ramagem-e-anderson-torres-condenados-por-tentativa-de-golpe.ghtml)**

**Motivo:** Efeito funcional concreto da condenação, separado de procedimentos disciplinares ainda em andamento.

**Evidência no corpo:** “As medidas atendem a determinações do Supremo Tribunal Federal, que condenou Ramagem e Torres por tentativa de golpe e ordenou a perda dos cargos dos dois na PF.”

### julgamento_nucleo_golpe — Relevância 18

**2026-01-08 — [Lula veta projeto de lei que prevê redução das penas dos condenados na trama golpista | G1](https://g1.globo.com/jornal-nacional/noticia/2026/01/08/lula-veta-projeto-de-lei-que-preve-a-reducao-das-penas-dos-condenados-na-trama-golpista.ghtml)**

**Motivo:** Marco histórico do veto de janeiro; sua superação em abril é documentada por referências superiores e posteriores.

**Evidência no corpo:** “vetou o texto aprovado pelo Congresso no fim de 2025, que reduz as penas e o tempo em que os condenados pelos atos golpistas ficarão presos em regime fechado.”

### julgamento_nucleo_golpe — Relevância 19

**2025-10-25 — [Ação contra Bolsonaro e sete réus entra na fase de recursos; entenda os próximos passos até a execução da pena | G1](https://g1.globo.com/politica/noticia/2025/10/25/acao-contra-bolsonaro-e-sete-reus-entra-na-fase-de-recursos-entenda-os-proximos-passos-ate-a-execucao-da-pena.ghtml)**

**Motivo:** Explica a função do acórdão e a abertura da fase de recursos, como etapa intermediária entre sentença e execução.

**Evidência no corpo:** “o processo seguiu para a fase de elaboração do acórdão, o documento que formaliza a decisão conjunta do colegiado”

### julgamento_nucleo_golpe — Relevância 20

**2026-04-30 — [Dosimetria: com derrubada de veto, saiba o que acontece com Bolsonaro | G1](https://g1.globo.com/politica/noticia/2026/04/30/com-derrubada-de-veto-saiba-o-que-acontece-com-bolsonaro-agora.ghtml)**

**Motivo:** Limites da consequência prática da dosimetria: estimativas de progressão não são redução automática ou decisão já aplicada.

**Evidência no corpo:** “Portanto, a redução de pena não será automática.”

## Antes de usar como referência definitiva

Revisar com outro anotador, confirmar o recorte informacional, congelar a versão do corpus e ampliar julgamentos com resultados não selecionados. As oito formulações de um tema compartilham a mesma história e não constituem oito temas independentes. Os conjuntos anteriores permanecem intactos; os novos arquivos não misturam os temas originais com os adicionais.
