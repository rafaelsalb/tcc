# Casos adicionais de relevância — 2025/2026

Três temas adicionais, com **20 artigos ordenados por tema e 60 URLs distintas**. Seleção editorial assistida por IA, não ground truth exaustiva nem revisão humana independente.

## Método e limites

- Pesquisa realizada em 2026-10-15.
- Fonte exclusiva: `g1_articles`, consultada em transação somente de leitura. Nenhuma busca web ou ranking da aplicação foi utilizado.
- Janela inclusiva: `2025-06-01` a `2026-05-20`, por `date_published`. Publicações fora do corpus não foram incluídas.
- Necessidade informacional: compreender uma história continuada, suas causas, evidências, marcos, contrapontos e consequências.
- Descoberta dirigida pelos três candidatos antes não curados no relatório original. Busca de títulos por expressões regulares; contagens incluem ruído e não medem relevância.
- Leitura dirigida do início e de passagens específicas do corpo, não leitura integral de todos os candidatos. Vídeos e áudios não foram assistidos; somente o texto armazenado foi julgado.
- A prioridade é editorial, não cronológica: síntese, mecanismo, marcos e limites probatórios vêm antes de detalhes adicionais. Todos os 20 documentos selecionados são positivos.
- Ausência na seleção significa não julgado, não necessariamente irrelevante. Há sobreposição factual entre sínteses e notícias de marcos; corpos idênticos foram excluídos.
- Datas, URLs primárias, presença do corpo, unicidade e literalidade das evidências foram verificadas no banco. Hashes registram a versão do texto consultado, não prova externa de veracidade.
- A seleção não foi otimizada pelos resultados de nenhum método de busca. Não houve teste de desempenho dessas consultas nesta curadoria.

## Arquivos para avaliação

- `evals_additional_curated_2025_2026.json`: três consultas completas, uma por tema.
- `evals_additional_query_variants_2025_2026.json`: 24 consultas, com as mesmas oito estruturas usadas na avaliação anterior, intercaladas por estilo.
- `relevance_additional_selection_2025_2026.json`: justificativas, evidências literais, datas e hashes por artigo.
- Em cada tema, todas as estruturas usam exatamente as mesmas 20 URLs na mesma ordem. Prefixos de tamanho 1/3/5/10/20 são aninhados.
- Atenção: o avaliador atual compara em k com `relevant_urls[:k]`; isso não é recall contra os 20 positivos fixos em todos os cortes. A curadoria não altera essa regra.

## Visão geral

| Tema | Candidatos com corpo >200 caracteres | Intervalo selecionado | Datas / meses distintos |
|---|---:|---|---:|
| Juliana Marins: queda no Rinjani, resgate e perícias | 113 | 2025-06-24 a 2025-08-02 | 13 / 3 |
| Cão Orelha: morte, limites da perícia e revisão da investigação | 81 | 2026-01-26 a 2026-04-15 | 15 / 4 |
| COP30: negociações, financiamento e resultados de Belém | 668 | 2025-06-27 a 2026-01-27 | 16 / 5 |

## Juliana Marins: queda no Rinjani, resgate e perícias

**ID:** `juliana_marins`

**Consulta completa:** O que aconteceu com Juliana Marins no Monte Rinjani, por que o resgate demorou e o que as perícias e investigações esclareceram sobre sua morte?

**Delimitação:** Acidente, tentativas de resgate, perícias e apuração de responsabilidades; exclui homenagens, vaquinhas e turismo sem evidência central.

**Cautelas:** As estimativas de 10–20 minutos dizem respeito ao trauma fatal, não necessariamente à primeira queda. A estimativa posterior de 32 horas é atribuída ao perito. Alegações de negligência não equivalem a decisão judicial. O corpo da matéria sobre limitações do IML contém uma referência cronológica inconsistente a sábado (6); ela não foi adotada como data do encontro do corpo.

**Hash do conjunto consultado:** `b124fc58e1bf9a1ce0beb3953f3cf79f03e9ea69787b02e4cfef81f1ac0682f3`

### juliana_marins — Relevância 01

**2025-07-10 — [Caso Juliana Marins: Veja perguntas e respostas após nova autópsia | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/10/caso-juliana-marins-perguntas-e-respostas-apos-nova-autopsia.ghtml)**

**Motivo:** Síntese das conclusões e perguntas remanescentes após a perícia brasileira; melhor porta de entrada.

**Evidência no corpo:** “A causa imediata da morte foi hemorragia interna provocada por lesões poliviscerais e politraumatismo, compatíveis com impacto de alta energia.”

### juliana_marins — Relevância 02

**2025-07-11 — [Juliana Marins desceu 220 metros na primeira queda e morreu em uma segunda; perito estima que ela permaneceu viva 32 horas | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/11/juliana-marins-coletiva-detalhes-morte-e-autopsia.ghtml)**

**Motivo:** Atualiza a reconstrução: separa a primeira queda do impacto fatal e atribui ao perito a estimativa de sobrevida.

**Evidência no corpo:** “Na coletiva, um perito afirmou que é possível estimar que ela permaneceu viva 32 horas após a primeira queda.”

### juliana_marins — Relevância 03

**2025-06-25 — [Caso Juliana Marins: possíveis falhas antes e depois de acidente | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/25/caso-juliana-marins-especialistas-listam-possiveis-erros-antes-e-depois-do-acidente-em-vulcao-na-indonesia.ghtml)**

**Motivo:** Organiza hipóteses de falhas de segurança e registra o contraponto da agência de resgate.

**Evidência no corpo:** “Especialistas em montanhismo, guias experientes e turistas que já estiveram no local apontam falhas graves que podem ter contribuído para a tragédia.”

### juliana_marins — Relevância 04

**2025-06-26 — [Por que levou dias para brasileira Juliana Marins ser resgatada de vulcão na Indonésia | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/26/por-que-levou-dias-para-brasileira-juliana-marins-ser-resgatada-de-vulcao-na-indonesia.ghtml)**

**Motivo:** Explica mecanismos do atraso com entrevistas sobre equipamento, clima e disponibilidade de socorristas.

**Evidência no corpo:** “Primeiro, eles dizem que o equipamento de resgate de emergência era muito limitado.”

### juliana_marins — Relevância 05

**2025-06-24 — [Brasileira Juliana Marins é encontrada morta 600 metros abaixo da trilha do vulcão Rinjani, na Indonésia | G1](https://g1.globo.com/jornal-nacional/noticia/2025/06/24/brasileira-juliana-marins-e-encontrada-morta-600-metros-abaixo-da-trilha-do-vulcao-rinjani-na-indonesia.ghtml)**

**Motivo:** Marco da confirmação da morte e reconstrução das buscas; distingue notícia confirmada de informação depois desmentida.

**Evidência no corpo:** “A família chegou a ser informada que as equipes de resgate tinham chegado até a jovem e dado comida e água. Mas a informação foi desmentida depois.”

### juliana_marins — Relevância 06

**2025-06-27 — [Autópsia de Juliana Marins: saiba o que causou morte de brasileira em vulcão | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/27/o-que-autopsia-revela-sobre-morte-de-juliana-marins-em-vulcao-na-indonesia.ghtml)**

**Motivo:** Documenta a conclusão da autópsia indonésia, como etapa histórica da investigação.

**Evidência no corpo:** “Um trauma contundente, resultando em danos a órgãos internos e hemorragia, foi a causa da morte de Juliana Marins”

### juliana_marins — Relevância 07

**2025-07-01 — [Juliana Marins: Polícia investiga negligência em trilha na Indonésia | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/01/juliana-marins-policia-investigacao.ghtml)**

**Motivo:** Mostra abertura da apuração local e pessoas chamadas a depor, sem converter suspeitas em autoria provada.

**Evidência no corpo:** “Além do guia, responsáveis pela agência de turismo, o carregador que levava as bagagens pela trilha e um policial florestal foram intimados a prestar depoimento.”

### juliana_marins — Relevância 08

**2025-06-27 — [Monte Rinjani: quem é responsável pela segurança dos montanhistas? | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/27/monte-rinjani-quem-e-responsavel-pela-seguranca-dos-montanhistas.ghtml)**

**Motivo:** Explica responsabilidades institucionais e operacionais pela segurança, além do relato do acidente.

**Evidência no corpo:** “A BBC News Indonesia (serviço de notícias da BBC em idioma indonésio) conversou com especialistas no país para entender de quem seriam as responsabilidades.”

### juliana_marins — Relevância 09

**2025-06-26 — [Morte de Juliana Marins: por que é difícil usar helicóptero e cordas em resgate? Especialistas explicam | G1](https://g1.globo.com/podcast/o-assunto/noticia/2025/06/26/morte-de-juliana-marins-entenda-se-era-possivel-mandar-cobertor-e-comida-durante-resgate-em-vulcao.ghtml)**

**Motivo:** Contraponto técnico à certeza de negligência; o texto do podcast tem informação suficiente sem ouvir o áudio.

**Evidência no corpo:** “Os especialistas ouvidos por Natuza Nery afirmam que, apesar das falhas apontadas, ainda não é possível afirmar com certeza que houve negligência no resgate de Juliana Marins.”

### juliana_marins — Relevância 10

**2025-06-29 — ['Ela caiu em um penhasco', diz guia em gravação após queda de Juliana Marins | G1](https://g1.globo.com/fantastico/noticia/2025/06/29/imagens-ineditas-revelam-primeiras-tentativas-de-resgate-de-juliana-marins-ela-caiu-em-um-penhasco-diz-guia-em-gravacao.ghtml)**

**Motivo:** Relato textual das primeiras tentativas e horários atribuídos à família; os vídeos não foram usados como evidência autônoma.

**Evidência no corpo:** “Um registro feito pelo próprio guia mostra a lanterna do capacete de Juliana ainda acesa após a queda.”

### juliana_marins — Relevância 11

**2025-08-02 — [Guia indonésio relata último contato com Juliana Marins | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/08/02/guia-indonesio-juliana-marins.ghtml)**

**Motivo:** Versão posterior do guia sobre divisão do grupo e último contato, necessária como contraponto atribuído.

**Evidência no corpo:** “O jovem disse que a niteroiense pedia ‘socorro’.”

### juliana_marins — Relevância 12

**2025-07-08 — [Polícia do RJ confirma que traumas de queda mataram Juliana Marins | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/08/policia-do-rj-confirma-que-traumas-de-queda-mataram-juliana-marins-mas-nao-descarta-agonia-antes-da-morte.ghtml)**

**Motivo:** Marco da confirmação pericial brasileira e dos limites para estabelecer o horário do óbito.

**Evidência no corpo:** “A estimativa exata da data da morte foi considerada prejudicada devido às condições em que o corpo chegou ao IML, já embalsamado.”

### juliana_marins — Relevância 13

**2025-07-09 — [Caso Juliana Marins: Estado do corpo comprometeu parte das análises periciais | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/09/caso-juliana-marins-estado-do-corpo-comprometeu-parte-das-analises-periciais-aponta-laudo-do-iml.ghtml)**

**Motivo:** Detalha limitações materiais da perícia; a inconsistência de data no corpo exige cautela, não correção silenciosa da fonte.

**Evidência no corpo:** “Segundo o laudo, o embalsamamento realizado antes da necropsia impediu que os especialistas estimassem com precisão o horário da morte”

### juliana_marins — Relevância 14

**2025-06-27 — [Legistas não esclareceram em que dia Juliana Marins morreu | G1](https://g1.globo.com/jornal-nacional/noticia/2025/06/27/legistas-nao-esclareceram-em-que-dia-juliana-marins-morreu.ghtml)**

**Motivo:** Distingue causa da morte de data da morte na primeira divulgação pericial.

**Evidência no corpo:** “Mas os legistas não esclareceram em que dia a Juliana Marins morreu.”

### juliana_marins — Relevância 15

**2025-07-01 — [Nova autópsia pode levar caso Juliana Marins à Justiça internacional | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/01/defensora-fala-sobre-nova-autopsia-no-corpo-de-juliana-marins.ghtml)**

**Motivo:** Registra o pedido da DPU e possíveis vias de apuração, ainda condicionais.

**Evidência no corpo:** “A DPU pediu nesta segunda-feira (30) que a Polícia Federal (PF) apure se houve crime de omissão no abandono de Juliana por parte das autoridades indonésias.”

### juliana_marins — Relevância 16

**2025-07-02 — [Juliana Marins: autópsia no Rio busca respostas sobre a morte | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/02/autopsia-no-corpo-de-juliana-marins-no-iml-do-rio.ghtml)**

**Motivo:** Execução da segunda autópsia e participação de peritos e representantes da família.

**Evidência no corpo:** “A necropsia é realizada por peritos da Polícia Civil, com a presença de um perito federal e de um representante da família.”

### juliana_marins — Relevância 17

**2025-06-25 — [Corpo de Juliana Marins é resgatado | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/25/corpo-de-juliana-marins-e-icado-de-vulcao-na-indonesia.ghtml)**

**Motivo:** Documenta conclusão da retirada do corpo e etapas operacionais em horários locais distintos.

**Evidência no corpo:** “O mau tempo impediu que helicópteros fossem usados na operação, e a solução foi instalar diversos pontos de ancoragem na pedra.”

### juliana_marins — Relevância 18

**2025-06-24 — [Socorristas da Indonésia montam acampamento em penhasco perto de onde Juliana Marins está após cair durante trilha | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/24/socorristas-na-indonesia-montam-acampamento-avancado-perto-de-onde-juliana-marins-esta.ghtml)**

**Motivo:** Comunicado do parque sobre a aproximação dos socorristas e restrição por neblina, antes da confirmação do óbito.

**Evidência no corpo:** “as tentativas de auxílio aéreo por helicóptero ainda não tiveram sucesso devido à forte neblina na área”

### juliana_marins — Relevância 19

**2025-06-24 — [Parque fecha trilha para resgate de Juliana Marins | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/06/24/parque-fecha-trilha-para-resgate-de-juliana-marins-brasileira-que-caiu-em-vulcao-na-indonesia.ghtml)**

**Motivo:** Medida concreta para restringir a trilha e permitir a operação de resgate.

**Evidência no corpo:** “A medida foi tomada para acelerar o trabalho de resgate da niteroiense Juliana Marins”

### juliana_marins — Relevância 20

**2025-07-04 — [Família de Juliana Marins vai enterrar corpo para possível nova autópsia | G1](https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/04/familia-de-juliana-marins-decide-enterrar-corpo.ghtml)**

**Motivo:** Consequência ligada à preservação de possibilidade de nova perícia, não selecionada pela homenagem funerária.

**Evidência no corpo:** “Então ela teria que ser enterrada caso precisasse fazer uma exumação futura”


## Cão Orelha: morte, limites da perícia e revisão da investigação

**ID:** `cao_orelha`

**Consulta completa:** O que se sabe sobre a morte do cão Orelha em Florianópolis, quais foram as conclusões e limitações dos laudos e como evoluiu a investigação de adolescentes e adultos?

**Delimitação:** Investigação do cachorro comunitário da Praia Brava, evidência veterinária/pericial, defesa, revisão pelo MP e consequências institucionais; exclui homônimos, homenagens e manifestações sem novidade central.

**Cautelas:** As notícias iniciais falam em eutanásia e vários suspeitos; versões posteriores corrigem esses pontos. A exumação não determinou a causa da morte nem excluiu trauma por ausência de fraturas. Suspeita, representação e pedido de internação não são condenação. A suspensão de apuração penal do delegado não suspende automaticamente apurações cíveis; o decreto aparece como anunciado, não como publicação já confirmada naquele texto.

**Hash do conjunto consultado:** `1338379d763fa56111b2daa3528aaf0e9fec5a6d395db70a025805933f93e223`

### cao_orelha — Relevância 01

**2026-02-26 — [Cão Orelha: laudo de exumação não identifica lesões | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/26/cao-orelha-laudo-exumacao-lesoes-cabeca.ghtml)**

**Motivo:** Prioriza o limite probatório mais importante: exumação sem causa determinada, sem confundir ausência de fratura com exclusão de trauma.

**Evidência no corpo:** “A análise dos restos mortais não permitiu afirmar qual foi a causa da morte.”

### cao_orelha — Relevância 02

**2026-02-06 — [Pancada e indiciamento de adolescente: o que se sabe sobre caso Orelha | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/06/pancada-piora-progressiva-adolescente-indiciado-o-que-se-sabe-cao-orelha.ghtml)**

**Motivo:** Síntese dos fatos, evidências e versões antes da exumação; deve ser lida junto da atualização pericial superior.

**Evidência no corpo:** “Inicialmente, a polícia afirmou que Orelha passou por eutanásia após as agressões. Depois, essa hipótese foi descartada.”

### cao_orelha — Relevância 03

**2026-02-02 — [Cão Orelha: linha do tempo dos fatos e o que se sabe até agora | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/02/cao-orelha-linha-do-tempo-e-o-que-se-sabe-ate-agora.ghtml)**

**Motivo:** Reconstrói a sequência de eventos e separa o caso Orelha do cão Caramelo.

**Evidência no corpo:** “A Polícia reiterou que não tem imagens que mostrem as agressões sofridas pelo cão.”

### cao_orelha — Relevância 04

**2026-03-04 — [Cão Orelha: laudo aponta doença degenerativa e infecção óssea | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/03/04/cao-orelha-laudo-exumacao-animal-doenca-degenerativa-cronica-infeccao-ossea.ghtml)**

**Motivo:** Aprofunda condições prévias e alcance restrito da análise óssea, evitando inferência causal indevida.

**Evidência no corpo:** “Mesmo assim, os peritos destacam que a ausência de fraturas não descarta a possibilidade de trauma na cabeça.”

### cao_orelha — Relevância 05

**2026-02-12 — [Justiça acata 35 pedidos nas investigações da morte do cão Orelha | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/12/justica-sc-acata-35-pedidos-investigacoes-morte-cao-orelha-veja-quais.ghtml)**

**Motivo:** Marco judicial da ampliação das diligências e adiamento da análise de internação.

**Evidência no corpo:** “O juiz André Milani postergou a análise do pedido da Polícia Civil de internação do adolescente apontado como suspeito da morte de Orelha.”

### cao_orelha — Relevância 06

**2026-02-06 — [Caso Orelha: MPSC pede novas respostas à polícia sobre inquéritos | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/06/caso-orelha-mpsc-vai-pedir-mais-respostas-a-policia-inqueritos.ghtml)**

**Motivo:** Explica por que o Ministério Público considerou a apuração insuficiente e pediu complementação.

**Evidência no corpo:** “A 10ª Promotoria identificou lacunas na apuração sobre a possível participação de adolescentes”

### cao_orelha — Relevância 07

**2026-02-04 — [Caso Orelha: defesa contesta indiciamento com vídeo do cão andando | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/04/orelha-defesa-contesta-autoria-video-cao-andando-agressoes.ghtml)**

**Motivo:** Contraponto da defesa e resposta policial à cronologia apresentada em vídeo.

**Evidência no corpo:** “Os advogados negam que o adolescente tenha participado das agressões e afirmam que o vídeo contradiz a linha do tempo apresentada pela polícia.”

### cao_orelha — Relevância 08

**2026-02-03 — [Polícia de SC conclui que apenas um adolescente teve envolvimento na morte do cão Orelha | G1](https://g1.globo.com/jornal-nacional/noticia/2026/02/03/policia-de-sc-conclui-que-apenas-um-adolescente-teve-envolvimento-na-morte-do-cao-orelha.ghtml)**

**Motivo:** Documenta a conclusão policial de fevereiro como versão atribuída, posteriormente submetida a novas diligências.

**Evidência no corpo:** “No caso do cão Orelha, a polícia afirmou que só um dos adolescentes suspeitos teve envolvimento nas agressões.”

### cao_orelha — Relevância 09

**2026-02-02 — [Veterinário que atendeu cão Orelha descarta acidente: 'Foi uma agressão' | G1](https://g1.globo.com/fantastico/noticia/2026/02/02/veterinario-que-atendeu-cao-orelha-descarta-acidente-foi-uma-agressao.ghtml)**

**Motivo:** Fonte do atendimento inicial; permite comparar achados clínicos com a exumação posterior.

**Evidência no corpo:** “Derli Royer, responsável pelo socorro emergencial, contou que o animal tinha lesões graves na cabeça e no olho esquerdo, além de forte desidratação.”

### cao_orelha — Relevância 10

**2026-01-27 — [Parentes de adolescentes suspeitos de agredir cachorro Orelha são indiciados por coação de testemunha em Florianópolis | G1](https://g1.globo.com/jornal-nacional/noticia/2026/01/27/parentes-de-adolescentes-suspeitos-de-matar-cachorro-orelha-sao-indiciados-por-coacao-de-testemunha-em-florianopolis.ghtml)**

**Motivo:** Marco da investigação de adultos por coação; a informação inicial de eutanásia no mesmo texto foi posteriormente revista.

**Evidência no corpo:** “A polícia indiciou nesta terça-feira (27) dois empresários e um advogado.”

### cao_orelha — Relevância 11

**2026-02-10 — [Caso Orelha: Ministério Público de SC pede exumação do corpo do cão | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/10/mpsc-pede-exumacao-corpo-cao-orelha.ghtml)**

**Motivo:** Fundamentação do pedido de exumação e distinção entre laudo indireto e exame do corpo.

**Evidência no corpo:** “Um laudo indireto, baseado em atendimento veterinário, apontou que a causa da morte foi um golpe na cabeça por objeto contundente.”

### cao_orelha — Relevância 12

**2026-02-13 — [Corpo do cão Orelha é exumado após MP apontar lacunas na investigação | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/13/corpo-de-cao-orelha-e-exumado-para-producao-de-novo-laudo-sobre-morte-em-florianopolis.ghtml)**

**Motivo:** Confirma execução da diligência, em vez de apenas o pedido de exumação.

**Evidência no corpo:** “A exumação ocorreu na quarta-feira (11).”

### cao_orelha — Relevância 13

**2026-02-10 — [Caso Orelha: MP dá prazo para polícia refazer depoimentos | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/10/orelha-mp-prazo-policia-refazer-depoimentos-esclarecer-coacao-ameaca.ghtml)**

**Motivo:** Delimita o procedimento de coação e ameaça de adultos, diferente da autoria dos maus-tratos.

**Evidência no corpo:** “A apuração atual trata apenas do conflito entre os adultos”

### cao_orelha — Relevância 14

**2026-01-26 — [Cão Orelha: operação cumpre mandados contra investigados por morte de cachorro comunitário em Florianópolis | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/01/26/cao-orelha-operacao-mandados-investigados-maus-tratos-coacao-florianopolis.ghtml)**

**Motivo:** Operação inicial e apreensão de dispositivos para reconstrução da prova, antes do estreitamento das suspeitas.

**Evidência no corpo:** “Aparelhos celulares e outros dispositivos eletrônicos foram apreendidos e passarão por análise.”

### cao_orelha — Relevância 15

**2026-02-03 — [Cuidadora de cão Orelha nega boatos sobre caso e alerta: 'Inventaram um monte de coisa' | G1](https://g1.globo.com/fantastico/noticia/2026/02/03/cuidadora-de-cao-orelha-nega-boatos-sobre-caso-e-alerta-inventaram-um-monte-de-coisa.ghtml)**

**Motivo:** Desmente detalhes virais que não devem ser incorporados à reconstrução factual sem prova.

**Evidência no corpo:** “Inventaram um monte de coisa, de eutanásia, de beisebol, de prego, não tem nada disso”

### cao_orelha — Relevância 16

**2026-02-06 — [Cão Orelha: Menina em vídeo não viu agressão, diz polícia | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/02/06/caso-orelha-menina-em-video-com-adolescente-nao-viu-ataque.ghtml)**

**Motivo:** Esclarece que a acompanhante não testemunhou agressão e registra a correção dos horários do vídeo divulgado.

**Evidência no corpo:** “a corporação esclareceu nesta sexta (6) que, na verdade, os registros mostram a saída do adolescente em outro horário, às 6h35, e o retorno às 6h37.”

### cao_orelha — Relevância 17

**2026-04-15 — [Cão Orelha: MP entra com ação de improbidade contra ex-delegado-geral | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/04/15/cao-orelha-mp-entra-acao-improbidade-contra-ex-delegado-geral-da-policia-civil-de-sc.ghtml)**

**Motivo:** Desdobramento institucional mais recente: ação cível sobre a condução da apuração, ainda sem julgamento informado.

**Evidência no corpo:** “O processo é de improbidade administrativa com indenização por dano moral coletivo em relação a atuação dele no caso do cão Orelha”

### cao_orelha — Relevância 18

**2026-03-18 — [Cão Orelha: Justiça suspende investigação criminal contra ex-delegado | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/03/18/cao-orelha-justica-suspende-investigacao-criminal-conduta-ex-delegado-geral.ghtml)**

**Motivo:** Contraponto judicial: suspensão por competência, sem confundir com arquivamento de toda apuração.

**Evidência no corpo:** “As investigações cíveis ou administrativas seguem normalmente.”

### cao_orelha — Relevância 19

**2026-03-12 — [Governo anuncia decreto Cão Orelha, que endurece penas para maus-tratos a animais | G1](https://g1.globo.com/politica/noticia/2026/03/12/governo-publica-decreto-cao-orelha-que-endurece-penas-para-maus-tratos-a-animais.ghtml)**

**Motivo:** Consequência regulatória nacional; o corpo registra que o anúncio ainda aguardava publicação no DOU.

**Evidência no corpo:** “Até a última atualização desta reportagem, o decreto ainda não tinha sido publicado no Diário Oficial da União (DOU).”

### cao_orelha — Relevância 20

**2026-01-30 — [Cão Orelha: quais os próximos passos da investigação em SC | G1](https://g1.globo.com/sc/santa-catarina/noticia/2026/01/30/cao-orelha-quais-proximos-passos-investigacao.ghtml)**

**Motivo:** Explica procedimentos e garantias dos adolescentes, bem como a revisão das suspeitas iniciais.

**Evidência no corpo:** “um dos quatro adolescentes inicialmente identificados como suspeitos do ato infracional foi ouvido nesta semana e negou que estava na praia no momento do ocorrido.”


## COP30: negociações, financiamento e resultados de Belém

**ID:** `cop30_negociacoes`

**Consulta completa:** Quais foram os resultados da COP30 em Belém, como evoluíram as negociações de financiamento e transição energética e quais compromissos e pendências ficaram para depois da conferência?

**Delimitação:** Preparação diplomática, metas climáticas, financiamento, transição energética, adaptação e implementação após Belém; exclui turismo, publicidade, festas, obras locais e incidentes sem contribuição central para os acordos.

**Cautelas:** Propostas, rascunhos e iniciativas da presidência não equivalem a decisões consensuais nem a recursos desembolsados. Diferenciar o Roteiro de Baku a Belém, o mapa do caminho para fósseis e os acordos finais. As críticas e expectativas prévias são preservadas como etapas históricas, sem substituir o resultado final.

**Hash do conjunto consultado:** `467a4c914bdebeca0c7e4bd3379c0df55637d75dafcb4c38e74e92a02d263652`

### cop30_negociacoes — Relevância 01

**2025-11-23 — [Entenda em 12 tópicos os avanços e as pendências da COP30 | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/23/entenda-em-12-topicos-os-avancos-e-as-pendencias-da-cop30.ghtml)**

**Motivo:** Síntese retrospectiva de resultados e limites, prioridade sobre expectativas anteriores à cúpula.

**Evidência no corpo:** “Um dos principais resultados foi a adoção de um conjunto comum de indicadores para a chamada Meta Global de Adaptação.”

### cop30_negociacoes — Relevância 02

**2025-11-22 — [COP30 aprova acordos com meta de triplicar financiamento e sem definição para o 'mapa do caminho' | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/22/cop30-aprova-acordos-sem-mapa-do-caminho.ghtml)**

**Motivo:** Marco da adoção dos acordos, meta financeira e controvérsia sobre o processo de aprovação.

**Evidência no corpo:** “O texto do Mutirão não cita os combustíveis fósseis, mas cria estruturas que ampliam a agenda de cooperação, organizam debates e inclui a meta de triplicar o financiamento para adaptação até 2035.”

### cop30_negociacoes — Relevância 03

**2025-11-21 — [Por que rota para fim de combustíveis fósseis virou impasse na COP30? | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/21/por-que-rota-para-fim-de-combustiveis-fosseis-virou-impasse-na-cop30.ghtml)**

**Motivo:** Explicador causal do principal impasse, conectando compromisso anterior e coalizões de negociação.

**Evidência no corpo:** “Os anfitriões brasileiros chegaram a cogitar mencionar um roteiro para a eliminação gradual dos combustíveis fósseis, mas o tema ficou de fora da agenda oficial e do último rascunho do texto final da cúpula”

### cop30_negociacoes — Relevância 04

**2025-11-05 — [COP30 apresenta plano de US$ 1,3 trilhão por ano para países pobres | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/05/presidencia-da-cop30-lanca-plano-de-us-13-trilhao-anuais-que-pode-ajudar-paises-na-luta-contra-crise-do-clima.ghtml)**

**Motivo:** Distingue financiamento proposto pelo roteiro Baku–Belém de tratado negociado e de desembolso realizado.

**Evidência no corpo:** “O texto não tem força de tratado internacional nem será objeto de negociação entre países”

### cop30_negociacoes — Relevância 05

**2025-11-22 — [Mapa do caminho fica fora dos textos da COP30 e vai ser uma iniciativa da presidência brasileira, diz André Corrêa do Lago | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/22/mapa-do-caminho-fica-fora-dos-textos-da-cop30-e-vai-ser-uma-iniciativa-da-presidencia-brasileira-diz-andre-correa-do-lago.ghtml)**

**Motivo:** Explica a saída institucional para o roteiro dos fósseis fora do consenso final.

**Evidência no corpo:** “o chamado "mapa do caminho" (roadmap) para o fim do uso dos combustíveis fósseis não será incorporado aos textos finais”

### cop30_negociacoes — Relevância 06

**2026-01-27 — [Em carta, Presidência da COP30 defende aceleração de decisões climáticas e admite resultado 'aquém do esperado' | G1](https://g1.globo.com/politica/noticia/2026/01/27/em-carta-presidencia-da-cop30-defende-aceleracao-de-decisoes-climaticas-e-admite-resultado-aquem-do-esperado.ghtml)**

**Motivo:** Balanço posterior da presidência e continuidade do trabalho após a conferência.

**Evidência no corpo:** “a Presidência da COP30 reconheceu que os resultados do evento ficaram "aquém do esperado"”

### cop30_negociacoes — Relevância 07

**2025-06-27 — [Conferência preparatória da COP30 deixa principais impasses de Belém sem solução; entenda em 5 pontos | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/06/27/conferencia-preparatoria-da-cop30-deixa-principais-impasses-de-belem-sem-solucao-entenda-em-5-pontos.ghtml)**

**Motivo:** Antecedente diplomático: problemas já identificados em Bonn, antes da reunião de Belém.

**Evidência no corpo:** “a conferência alemã que deveria preparar o terreno para acordos na COP30 esbarrou em impasses sobre financiamento climático, adaptação e transição energética.”

### cop30_negociacoes — Relevância 08

**2025-11-08 — [Em 10 pontos, entenda o que a Cúpula de Líderes mostra sobre a COP30 | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/08/em-10-pontos-entenda-o-que-a-cupula-de-lideres-mostra-sobre-o-rumo-da-cop30-e-seus-desafios.ghtml)**

**Motivo:** Distingue sinalização política da cúpula de líderes de acordos negociados formalmente.

**Evidência no corpo:** “São considerados passos iniciais e sinalizações importantes.”

### cop30_negociacoes — Relevância 09

**2025-08-02 — [A 100 dias da COP30, metas climáticas atrasadas aumentam a pressão por resultados em Belém | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/08/02/a-100-dias-da-cop30-metas-climaticas-atrasadas-aumentam-a-pressao-por-resultados-em-belem.ghtml)**

**Motivo:** Explica a pressão das NDCs atrasadas e o elo com o Acordo de Paris.

**Evidência no corpo:** “Até o fim de julho, apenas 25 países haviam enviado suas novas metas oficiais à ONU”

### cop30_negociacoes — Relevância 10

**2025-11-10 — [‘Fantástico acordo’: presidente da COP30 celebra consenso sobre agenda | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/10/fantastico-acordo-presidente-da-cop30-celebra-consenso-sobre-agenda-do-1o-dia-conferencia.ghtml)**

**Motivo:** Marco procedimental que permitiu iniciar negociações; não é aprovação do acordo final.

**Evidência no corpo:** “o acordo costurado ainda no fim de semana foi considerado essencial para destravar o início das discussões formais.”

### cop30_negociacoes — Relevância 11

**2025-11-11 — [Arábia Saudita trava negociações sobre plano para transição energética, dizem observadores da COP30 | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/11/arabia-saudita-negociacoes-plano-transicao-energetica-observadores-cop30.ghtml)**

**Motivo:** Mostra resistência de produtores de petróleo e interesses econômicos por trás do impasse.

**Evidência no corpo:** “A Arábia Saudita, um dos líderes mundiais de petróleo, vem se posicionando contra a tentativa de um plano prático para abandonar os combustíveis fósseis na COP30.”

### cop30_negociacoes — Relevância 12

**2025-11-15 — [COP30: Brasil tenta destravar plano global contra combustíveis fósseis | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/15/nos-bastidores-da-cop30-brasil-arma-estrategia-para-destravar-plano-global-contra-combustiveis-fosseis.ghtml)**

**Motivo:** Estratégia de articulação brasileira para incluir um tema inicialmente fora da agenda.

**Evidência no corpo:** “O governo brasileiro tem se mobilizado nos bastidores da COP30 para que o "mapa do caminho" para abandonar os combustíveis fósseis seja oficializado na agenda da conferência.”

### cop30_negociacoes — Relevância 13

**2025-11-18 — [Na COP30, grupo de países apoia a adoção de 'mapa do caminho' pelo fim do uso de combustíveis fósseis | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/18/paises-apoiam-mapa-caminho-fim-combustiveis-fosseis-cop3.ghtml)**

**Motivo:** Formação de coalizão pró-roteiro; apoio público não é aprovação consensual.

**Evidência no corpo:** “Um grupo de cerca de 80 países defendeu, nesta terça-feira (18) em Belém (PA), a importância da adoção de um "mapa do caminho" para o fim do uso dos combustíveis fósseis.”

### cop30_negociacoes — Relevância 14

**2025-11-19 — [Na COP30, cientistas publicam carta em que criticam plano dos negociadores contra combustíveis fósseis | G1](https://g1.globo.com/jornal-nacional/jn-na-cop30/noticia/2025/11/19/na-cop30-cientistas-publicam-carta-em-que-criticam-plano-dos-negociadores-contra-combustiveis-fosseis.ghtml)**

**Motivo:** Contraponto científico à ambição dos roteiros propostos durante as negociações.

**Evidência no corpo:** “Na carta, os cientistas afirmaram ainda que não pode haver nenhum novo investimento em combustíveis fósseis.”

### cop30_negociacoes — Relevância 15

**2025-11-21 — [COP30: rascunho de acordo é criticado por não citar redução de combustíveis fósseis nem origem de financiamento a países pobres | G1](https://g1.globo.com/jornal-nacional/jn-na-cop30/noticia/2025/11/21/cop30-rascunho-de-acordo-e-criticado-por-nao-citar-reducao-de-combustiveis-fosseis-nem-origem-de-financiamento-a-paises-pobres.ghtml)**

**Motivo:** Relaciona a ausência do roteiro ao desacordo sobre volume e origem do financiamento.

**Evidência no corpo:** “O documento fala em duplicar o financiamento, enquanto o grupo de negociadores africanos vinha pedindo para triplicar”

### cop30_negociacoes — Relevância 16

**2025-11-21 — [UE ameaça barrar acordo da COP30 e critica ausência de metas sobre com | G1](https://g1.globo.com/meio-ambiente/cop-30/noticia/2025/11/21/ue-ameaca-barrar-acordo-da-cop30-e-critica-ausencia-de-metas-sobre-combustiveis-fosseis.ghtml)**

**Motivo:** Contradição entre pressão europeia por ambição e resistência financeira atribuída por observadores.

**Evidência no corpo:** “a União Europeia dificulta as negociações em outra frente: mostra resistência em ampliar recursos para o enfrentamento da crise do clima.”

### cop30_negociacoes — Relevância 17

**2025-11-22 — [Resultado da COP30 frustra cientistas, ambientalistas e representantes de diversos países | G1](https://g1.globo.com/jornal-nacional/jn-na-cop30/noticia/2025/11/22/resultado-da-cop30-frustra-cientistas-ambientalistas-e-representantes-de-diversos-paises.ghtml)**

**Motivo:** Avaliação plural do resultado, contrapondo frustração e preservação do consenso multilateral.

**Evidência no corpo:** “Cientistas, ambientalistas e representantes de diversos países declararam frustração com o resultado final da COP30, mas afirmaram que foi o acordo possível.”

### cop30_negociacoes — Relevância 18

**2025-11-13 — [Plano de ação em saúde é lançado na COP 30 em Belém para enfrentar adaptação climática | G1](https://g1.globo.com/pa/para/noticia/2025/11/13/plano-de-acao-em-saude-e-lancado-na-cop-30-em-belem-para-enfrentar-adaptacao-climatica.ghtml)**

**Motivo:** Resultado setorial concreto de adaptação em saúde, além da negociação energética.

**Evidência no corpo:** “foi lançado o Plano de Ação em Saúde de Belém, o primeiro plano internacional dedicado exclusivamente à adaptação climática no setor de saúde.”

### cop30_negociacoes — Relevância 19

**2025-12-08 — [Transição Energética: Lula dá prazo para proposta após COP30 | G1](https://g1.globo.com/politica/noticia/2025/12/08/apos-cop-sem-acordo-sobre-combustiveis-fosseis-lula-da-60-dias-para-governo-elaborar-proposta-de-transicao-energetica.ghtml)**

**Motivo:** Seguimento doméstico da pendência internacional: elaboração de diretrizes e mecanismos de financiamento.

**Evidência no corpo:** “No despacho desta segunda-feira (8), Lula determinou que os ministérios elaborem um texto para estabelecer as diretrizes desse "mapa do caminho".”

### cop30_negociacoes — Relevância 20

**2025-08-13 — [COP30 reforça desafio antigo: mobilizar recursos para financiamento climático | G1](https://g1.globo.com/pa/para/noticia/2025/08/13/cop30-na-amazonia-reforca-desafio-antigo-e-urgente-mobilizar-trilhoes-para-financiamento-climatico-global.ghtml)**

**Motivo:** Contexto da dívida histórica de financiamento e da demanda de países em desenvolvimento.

**Evidência no corpo:** “Ainda em 2009, durante a COP15 em Copenhague, países desenvolvidos comprometeram-se a mobilizar US$ 100 bilhões anuais até 2020”

## Antes de usar como referência definitiva

Revisar com outro anotador, confirmar o recorte informacional, congelar a versão do corpus e ampliar julgamentos com resultados não selecionados. As oito formulações de um tema compartilham a mesma história e não constituem oito temas independentes. Os conjuntos anteriores permanecem intactos; os novos arquivos não misturam os temas originais com os adicionais.
