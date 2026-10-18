# Casos de teste: notícias centrais para compreender histórias continuadas

## 1. Resultado e escopo

**Cinco casos completos, com 20 artigos relevantes ordenados por caso: 100 URLs distintas.** Foram localizados dez temas candidatos; cinco receberam curadoria documental nesta rodada. Os outros cinco são possibilidades de ampliação, não conjuntos de referência já validados.

- **Fonte exclusiva:** tabela local `g1_articles`. Não foram utilizados os arquivos de avaliações ou pesquisas anteriores do repositório, nem buscas na web.
- **Janela inclusiva de publicação:** `2025-06-01` a `2026-05-20`, pelo campo `date_published`.
- **Necessidade informacional:** uma pessoa ocupada, sem conhecimento prévio, quer compreender o acontecimento, suas causas, personagens, consequências e principais desdobramentos.
- **Idioma e unidade de avaliação:** português; artigo identificado pela **URL primária da tabela**, não por trecho, título, personagem ou número de ordem nesta pesquisa.
- **Pesquisa realizada em:** 2026-10-15. A consulta ao banco foi somente de leitura.
- **Natureza do resultado:** referência editorial curada, produzida por um único avaliador assistido por IA; não é um julgamento humano independente nem um levantamento exaustivo de todos os documentos relevantes.

### Visão geral dos conjuntos completos

| ID | História delimitada | Publicações selecionadas | Dias / meses distintos nas seleções | Artigos |
| --- | --- | --- | --- | ---: |
| M | Crise do Banco Master: liquidação, suspeitas de fraude, BRB e investidores | 2025-09-03 a 2026-04-22 | 17 / 8 | 20 |
| I | Descontos associativos indevidos no INSS: funcionamento, reparação e investigação | 2025-06-08 a 2026-04-23 | 18 / 10 | 20 |
| T | Tarifaço dos EUA sobre o Brasil: imposição, negociação e mudança de base jurídica | 2025-07-09 a 2026-03-12 | 17 / 7 | 20 |
| A | Intoxicações por metanol em bebidas adulteradas: surto e cadeia de falsificação | 2025-09-28 a 2026-02-27 | 19 / 5 | 20 |
| B | Morte de Benício Xavier em Manaus: prescrição de adrenalina e investigação | 2025-11-27 a 2026-05-05 | 16 / 5 | 20 |

Esses intervalos são os das **matérias selecionadas**, não as datas de início e fim dos acontecimentos. Não é necessário que um tema ocupe toda a janela: a continuidade é demonstrada por diferentes etapas e publicações ao longo do tempo.

## 2. Descoberta dos temas e critérios de julgamento

### 2.1. O que foi encontrado no banco

O recorte contém **211.773 registros**, todos com título e corpo não vazios. Existem registros em todos os meses da janela; isso não demonstra completude da coleta de toda a cobertura do G1.

A descoberta combinou uma amostra de títulos distribuída pelo período (`ORDER BY md5(url) LIMIT 850`) com buscas exploratórias por nomes e acontecimentos encontrados nos títulos. Depois, foram examinadas listas de candidatos por data e priorizados explicadores, marcos factuais e consequências. Não foi utilizado o ranking do sistema de busca da aplicação para escolher os positivos.

| Tema candidato | Correspondências exploratórias no título | Intervalo dessas correspondências | Decisão nesta rodada |
| --- | ---: | --- | --- |
| Banco Master / Vorcaro | 838 | 2025-06-17 a 2026-05-03 | Curadoria completa: caso M |
| Fraudes, descontos e CPMI do INSS | 318 | 2025-06-02 a 2026-04-30 | Curadoria completa, restrita aos descontos associativos: caso I |
| Tarifaço / tarifas relacionadas ao Brasil | 809 | 2025-06-04 a 2026-05-05 | Curadoria completa, restrita ao conflito tarifário EUA–Brasil: caso T |
| Metanol | 563 | 2025-08-18 a 2026-04-15 | Curadoria completa, restrita às bebidas adulteradas: caso A |
| Benício | 74 | 2025-06-15 a 2026-05-05 | Curadoria completa, eliminando homônimos: caso B |
| Operação Contenção / operações na Penha e no Alemão | 119 | 2025-06-12 a 2026-04-02 | Candidato para ampliação: operação de outubro e apuração das mortes; filtro ainda contém muito ruído |
| Juliana Marins / Rinjani | 113 | 2025-06-23 a 2026-01-04 | Candidato para ampliação: queda, resgate e perícias; separar fatos centrais de homenagens e perfis turísticos |
| Cão Orelha | 81 | 2026-01-26 a 2026-04-15 | Candidato para ampliação: agressão e investigação; separar evidências de manifestações e boatos |
| COP30 | 675 | 2025-06-01 a 2026-04-04 | Candidato para ampliação: delimitar negociações e resultados, excluindo publicidade e agenda local |
| Trama golpista / julgamento de Bolsonaro | 515 | 2025-06-02 a 2026-04-30 | Candidato para ampliação: delimitar núcleo principal, julgamento e execução das penas |

**As contagens acima NÃO são contagens de artigos relevantes.** Incluem falsos positivos: “contenção” de encostas, outras fraudes previdenciárias, homônimos de Benício, tarifas de ônibus, metanol em pesquisas químicas etc. Tampouco a presença no G1 mede, por si só, a cobertura de toda a imprensa brasileira. Os cinco conjuntos completos demonstram cobertura continuada dentro do corpus disponível.

### 2.2. O que conta como relevante

Uma matéria foi incluída quando os trechos examinados do corpo traziam informação central sobre pelo menos uma destas funções:

1. **Síntese:** explica o que aconteceu e por que importa, sem pressupor familiaridade.
2. **Causalidade e evidência:** esclarece o mecanismo, documentos, perícias ou limites de uma hipótese.
3. **Marco:** documenta uma mudança importante — liquidação, prisão, decisão, reembolso, confirmação ou conclusão de inquérito.
4. **Consequência:** mostra impacto coletivo, reparação, risco sanitário ou responsabilidade institucional.
5. **Contraponto central:** registra a versão dos envolvidos ou uma decisão que impede confundir suspeita com resultado definitivo.

Menção incidental, reação de celebridade, luxo de investigados, homenagem, agenda, reprodução muito pobre, chamada de programa e balanço local sem novidade central não bastaram. Uma matéria regional pode ser relevante quando é a fonte do acontecimento central: o caso Benício é o exemplo mais claro.

**Leitura do corpo:** foi dirigida, com exame do início e de passagens factuais posteriores; algumas matérias foram lidas integralmente. Não afirmo leitura integral de todos os corpos nem revisão de todos os resultados exploratórios. As evidências curtas abaixo foram retiradas de `text_content`, e não inferidas apenas dos títulos. Imagens, áudio e vídeo não foram assistidos: matérias desses formatos só entraram quando havia texto suficiente.

### 2.3. O que significa a ordem 1–20

É uma **prioridade editorial de relevância para a consulta definida**, não ordem cronológica e não uma pontuação calculada pelo sistema. A prioridade considera, nesta sequência: capacidade de explicar a história; centralidade do fato; evidência e abrangência; utilidade para o leitor; contribuição adicional em relação às posições superiores. A numeração desempata julgamentos qualitativos próximos, sem pretensão de precisão matemática.

As posições 1–5 privilegiam visão geral, mecanismo e marcos estruturantes. As posições seguintes acrescentam etapas, consequências e evidências mais específicas. **A posição 20 continua sendo relevante**; “menos relevante” significa menos prioritária dentre as vinte selecionadas, não irrelevante. Há sobreposição factual, sobretudo entre um explicador e a notícia do marco que ele explica; não foram selecionadas duas URLs apenas para repetir o mesmo texto.

Notícias antigas continuam úteis para reconstruir a evolução do caso, mas **hipótese inicial não deve ser convertida em fato atual**. Quando houve superação ou divergência, ela foi marcada. Alegações de polícia, relator ou defesa são atribuídas às respectivas fontes; prisão e indiciamento não são condenação.

## 3. Conjuntos de 1, 3, 5, 10 e 20 e uso nas métricas

Para cada tema, os conjuntos pedidos são **prefixos aninhados** da lista ordenada:

| Tema | Conjunto de 1 | Conjunto de 3 | Conjunto de 5 | Conjunto de 10 | Conjunto de 20 |
| --- | --- | --- | --- | --- | --- |
| M | M01 | M01–M03 | M01–M05 | M01–M10 | M01–M20 |
| I | I01 | I01–I03 | I01–I05 | I01–I10 | I01–I20 |
| T | T01 | T01–T03 | T01–T05 | T01–T10 | T01–T20 |
| A | A01 | A01–A03 | A01–A05 | A01–A10 | A01–A20 |
| B | B01 | B01–B03 | B01–B05 | B01–B10 | B01–B20 |

`M01–M05`, por exemplo, significa exatamente `{M01, M02, M03, M04, M05}`. A mesma regra vale para todos os intervalos da tabela.

### Atenção: tamanho da referência não é k

Para comparar **precision@k, recall@k e F1@k**, recomendo manter uma referência fixa por tema — inicialmente as 20 URLs — e variar apenas `k ∈ {1,3,5,10,20}`. Se `Lk` é o conjunto das primeiras k URLs distintas recuperadas e `R` a referência fixa:

```text
acertos = |Lk ∩ R|
precision@k = acertos / k
recall@k = acertos / |R|
F1@k = 2 × precision@k × recall@k / (precision@k + recall@k)
```

F1 é zero quando ambas as parcelas forem zero. Se o sistema retornar menos de k artigos, declarar previamente a convenção: nesta definição, as posições não preenchidas não geram acertos. Deduplicar artigos antes do corte; se a recuperação for por chunks, agregar por URL antes de avaliar.

Com 20 positivos fixos, o recall máximo em k=1 é 1/20, ou 5%; isso é esperado. **Não trocar automaticamente R por seu prefixo de tamanho k:** isso muda o alvo entre os experimentos e pode penalizar um artigo relevante simplesmente por estar fora daquele prefixo. Os prefixos são úteis como diferentes orçamentos de leitura ou tarefas editoriais explicitamente distintas.

**Limitação decisiva:** há outros artigos relevantes não selecionados. Uma URL ausente deste arquivo é **não julgada**, não automaticamente negativa. As fórmulas acima, usando somente estas vinte URLs, medem recuperação da referência curada, não recall de toda a cobertura. Para métricas de relevância no corpus, ampliar os julgamentos com um pool de resultados de diferentes métodos e rotular os não julgados antes de contabilizá-los como erros. Reportar os resultados iniciais como avaliação contra referência curada; não como ground truth exaustiva. Os dez temas foram descobertos no corpus disponível, portanto também existe viés de seleção por cobertura.

## 4. Caso M — Crise do Banco Master

**Consulta sugerida:** “O que aconteceu com o Banco Master, como funcionavam as suspeitas de fraude e quais foram as consequências para o BRB e os investidores?”

**Delimitação:** tentativa de compra pelo BRB, liquidação, investigação Compliance Zero e consequências financeiras diretamente ligadas ao colapso. Não inclui toda notícia sobre Daniel Vorcaro, vida privada ou disputas políticas que apenas mencionam o banco.

**Por que é uma história continuada:** há veto à compra em setembro, investigação em outubro, liquidação em novembro, novas diligências e ressarcimento em janeiro, mudança de relatoria em fevereiro e desdobramentos financeiros e policiais em março/abril. A continuidade está documentada por 17 datas selecionadas em oito meses, não por muitas notas sobre um único anúncio.

**Lógica do topo:** M01 explica o modelo e o colapso; M02 documenta a liquidação; M03 e M04 mostram a ampliação da investigação; M05 esclarece a situação dos investidores. As posições seguintes aprofundam antecedentes, dinheiro público, provas e reparação.

### M01 — Relevância 1
- **2026-03-04 — [CDBs irreais e carteiras de crédito falsas: entenda a crise que derrubou o Banco Master e levou Vorcaro à prisão](https://g1.globo.com/economia/noticia/2026/03/04/cdbs-irreais-e-carteiras-de-credito-falsas-entenda-a-crise-que-derrubou-o-banco-master-e-levou-vorcaro-a-prisao.ghtml)**
- **Motivo:** melhor ponto de entrada: integra captação cara, risco de insolvência, tentativas de venda, liquidação e nova prisão. Explica a crise, em vez de apresentar apenas uma atualização.
- **Evidência no corpo:** “O banco operava sob risco elevado de insolvência”. **Limite:** a síntese termina em março; M04 e M10 acrescentam fatos de abril.

### M02 — Relevância 2
- **2025-11-18 — [Banco Central determina a liquidação extrajudicial do Banco Master](https://g1.globo.com/economia/noticia/2025/11/18/banco-central-determina-a-liquidacao-extrajudicial-do-banco-master.ghtml)**
- **Motivo:** registra o fato que transforma dificuldades bancárias em colapso institucional e explica o significado da liquidação. É mais central que reações de mercado ou declarações políticas.
- **Evidência no corpo:** “decretar a liquidação extrajudicial do conglomerado”. **Cuidado:** o texto também menciona administração especial; não tratar todos os componentes do grupo como submetidos a um único regime idêntico.

### M03 — Relevância 3
- **2026-03-04 — [Daniel Vorcaro é preso pela PF em nova fase da operação sobre Banco Master](https://g1.globo.com/sp/sao-paulo/noticia/2026/03/04/vorcaro-e-preso-em-nova-operacao-da-pf.ghtml)**
- **Motivo:** documenta a nova prisão e o escopo criminal da terceira fase, incluindo a versão da defesa. Complementa a explicação financeira de M01 com um marco factual.
- **Evidência no corpo:** “possível prática dos crimes de ameaça, corrupção, lavagem de dinheiro e invasão de dispositivos informáticos”. Trata-se de investigação, não sentença.

### M04 — Relevância 4
- **2026-04-16 — [PF prende ex-presidente do BRB; ele teria recebido 6 imóveis de luxo avaliados em R$ 146 milhões como propina de Daniel Vorcaro](https://g1.globo.com/jornal-nacional/noticia/2026/04/16/pf-prende-ex-presidente-do-brb-ele-teria-recebido-6-imoveis-de-luxo-avaliados-em-r-146-milhoes-como-propina-de-daniel-vorcaro.ghtml)**
- **Motivo:** conecta suspeitas de corrupção à compra de carteiras fraudulentas pelo banco público. Os imóveis importam como alegada contrapartida, não como curiosidade sobre luxo.
- **Evidência no corpo:** “teria atuado para o BRB comprar carteiras de crédito fraudulentas do Banco Master”. Atribuição: investigadores da PF.

### M05 — Relevância 5
- **2025-11-18 — [Banco Master: como ficam investidores após a liquidação pelo BC](https://g1.globo.com/economia/noticia/2025/11/18/liquidacao-do-banco-master-como-ficam-correntistas-e-investidores.ghtml)**
- **Motivo:** responde à consequência prática mais imediata: proteção, limites do FGC, créditos sem cobertura e funcionamento do ressarcimento. Tem utilidade geral, não apenas para um município afetado.
- **Evidência no corpo:** “Quem não é protegido pelo FGC?” e “Quando o saldo ultrapassa R$ 250 mil”. **Limite:** condições e estimativas são as daquele momento.

### M06 — Relevância 6
- **2025-09-03 — [Banco Central reprova compra do Master pelo estatal BRB](https://g1.globo.com/economia/noticia/2025/09/03/bc-banco-master-brb.ghtml)**
- **Motivo:** antecedente decisivo: a solução de venda ao BRB foi barrada antes da liquidação. O corpo detalha a operação e registra as posições dos bancos.
- **Evidência no corpo:** “A reprovação pelo BC foi anunciada após mais de cinco meses de análise”. **Qualidade:** o texto armazenado começa com referência a documento anterior, mas preserva informação substancial sobre o veto.

### M07 — Relevância 7
- **2025-11-19 — [18 fundos previdenciários de estados e municípios têm R$ 1,86 bilhão aplicados no banco Master](https://g1.globo.com/economia/noticia/2025/11/19/18-fundos-de-pensao-de-estados-e-municipios-tem-r-186-bilhao-aplicados-no-banco-master.ghtml)**
- **Motivo:** dimensiona a exposição de recursos previdenciários e explica por que parte dos prejudicados não recebe a mesma garantia do pequeno investidor. Preferível à soma de notas municipais isoladas.
- **Evidência no corpo:** “os valores aplicados por fundos previdenciários e por fundos de investimento não são cobertos pelo Fundo Garantidor de Crédito”. Valores referem-se ao levantamento daquela data.

### M08 — Relevância 8
- **2026-01-19 — [FGC começa a ressarcir 377 mil credores do banco Master a partir desta segunda](https://g1.globo.com/economia/noticia/2026/01/19/fgc-comeca-a-ressarcir-150-mil-credores-do-banco-master-a-partir-desta-segunda.ghtml)**
- **Motivo:** muda a narrativa de expectativa de proteção para pagamento efetivo. Distingue solicitações registradas de processos concluídos e informa a revisão das estimativas.
- **Evidência no corpo:** “aproximadamente 377 mil finalizaram o processo de solicitação de garantia”. **Metadado:** a URL conserva “150-mil”, mas título e corpo armazenados usam 377 mil; a URL continua sendo a identidade.

### M09 — Relevância 9
- **2026-02-12 — [STF anuncia afastamento de Toffoli da relatoria do caso Master; ministro foi citado em mensagens de Daniel Vorcaro](https://g1.globo.com/jornal-nacional/noticia/2026/02/12/stf-anuncia-afastamento-de-toffoli-da-relatoria-do-caso-master-ministro-foi-citado-em-mensagens-de-daniel-vorcaro.ghtml)**
- **Motivo:** explica uma mudança importante na condução judicial e a origem da crise de relatoria. Mais útil que especulações anteriores sobre o que o tribunal faria.
- **Evidência no corpo:** “reconhecem a plena validade dos atos praticados pelo ministro Dias Toffoli”. **Cuidado:** a nota também afirma inexistência de suspeição ou impedimento; a saída não prova crime do ministro.

### M10 — Relevância 10
- **2026-04-16 — [Master: PF aponta que planilhas, extratos e contratos 'artificiais' sustentavam ativos sem lastro](https://g1.globo.com/politica/blog/andreia-sadi/post/2026/04/16/master-vorcaro-pf-documentos-artificiais-operacao-compliance.ghtml)**
- **Motivo:** esclarece o mecanismo documental atribuído à fraude. Acrescenta substância à expressão genérica “carteiras falsas”, embora seja mais específico que M01.
- **Evidência no corpo:** “contratos, extratos, planilhas e procurações produzidos em série”. A matéria relata indícios policiais, não conclusão judicial definitiva.

### M11 — Relevância 11
- **2025-10-01 — [PF abre inquérito para apurar suposto envolvimento do Banco Master em crimes contra o sistema financeiro](https://g1.globo.com/df/distrito-federal/noticia/2025/10/01/pf-abre-inquerito-para-apurar-envolvimento-do-banco-master-brb-crimes-financeiro.ghtml)**
- **Motivo:** documenta que a investigação antecede a prisão e a liquidação. É curta, porém contém um marco verificável, não uma mera chamada de vídeo.
- **Evidência no corpo:** “ganhou novos elementos depois que Banco Central compartilhou documentos com o Ministério Público Federal”. Menor prioridade pela pouca explicação adicional.

### M12 — Relevância 12
- **2025-12-03 — [Decisão de Dias Toffoli provoca transferência das investigações sobre Banco Master para o STF](https://g1.globo.com/jornal-nacional/noticia/2025/12/03/decisao-de-dias-toffoli-provoca-transferencia-das-investigacoes-sobre-banco-master-para-o-supremo.ghtml)**
- **Motivo:** permite entender por que o caso saiu da Justiça Federal e chegou ao Supremo, antecedente necessário da mudança narrada em M09.
- **Evidência no corpo:** “a PF encontrou material relacionado a um deputado federal na casa de Daniel Vorcaro”. O texto também registra a soltura anterior dos executivos.

### M13 — Relevância 13
- **2026-03-23 — [Master: técnicos do TCU dizem que BC agiu corretamente em liquidação](https://g1.globo.com/economia/noticia/2026/03/23/tecnicos-do-tcu-concluem-que-nao-houve-impropriedades-omissoes-ou-negligencias-do-bc-na-liquidacao-do-master.ghtml)**
- **Motivo:** oferece o resultado técnico de uma controvérsia relevante, em vez de apenas sua abertura. Ajuda a separar questionamento político/institucional de achado de auditoria.
- **Evidência no corpo:** “medida imperativa, legal e tecnicamente fundamentada”. **Limite:** parecer da área técnica; o plenário ainda não julgara.

### M14 — Relevância 14
- **2026-01-14 — [Banco Master: PF faz buscas em endereços de Daniel Vorcaro e parentes](https://g1.globo.com/sp/sao-paulo/noticia/2026/01/14/pf-faz-buscas-em-enderecos-de-daniel-vorcaro-e-parentes-dele.ghtml)**
- **Motivo:** documenta a segunda fase e o avanço sobre patrimônio, fundos e familiares; faz a ponte entre a investigação inicial e a nova prisão de março.
- **Evidência no corpo:** “havia captação de dinheiro, aplicação em fundos e desvio para o patrimônio pessoal de Vorcaro e parentes”. Atribuição à investigação; inclui manifestação da defesa.

### M15 — Relevância 15
- **2026-01-21 — [BC liquida Will Bank, banco digital do Master; FGC vai ter que desembolsar mais R$ 6 bilhões para ressarcir vítimas](https://g1.globo.com/jornal-nacional/noticia/2026/01/21/bc-liquida-will-bank-banco-digital-do-master-fgc-vai-ter-que-desembolsar-mais-r-6-bilhoes-para-ressarcir-vitimas.ghtml)**
- **Motivo:** mostra o alcance do colapso dentro do grupo e o impacto sobre clientes de baixa renda. Não é uma história bancária independente apenas por envolver outro nome.
- **Evidência no corpo:** “O Will Bank foi criado em 2017 e comprado pelo Master em 2024”. A cifra de ressarcimento é estimativa da época.

### M16 — Relevância 16
- **2026-03-02 — [Caso Master: BRB estima prejuízo de R$ 8 bilhões, diz presidente](https://g1.globo.com/df/distrito-federal/noticia/2026/03/02/caso-master-dano-causado-ao-brb-e-estimado-em-r-8-bilhoes-diz-presidente-do-banco-publico.ghtml)**
- **Motivo:** dimensiona o prejuízo no banco público e a discussão sobre recomposição patrimonial. É consequência central, embora menos introdutória que a explicação do colapso.
- **Evidência no corpo:** “o rombo deixado nas contas do banco pelas transações malsucedidas com o Banco Master é estimado em R$ 8 bilhões”. Não confundir estimativa de provisão com perda final apurada.

### M17 — Relevância 17
- **2026-03-31 — [BRB sabia que parte da carteira de consignados do Master não tinha empréstimos associados, diz documento interno do banco](https://g1.globo.com/politica/noticia/2026/03/31/brb-sabia-que-parte-da-carteira-de-consignados-do-master-nao-tinha-emprestimos-associados-diz-documento-interno-do-banco.ghtml)**
- **Motivo:** acrescenta evidência documental sobre conhecimento prévio dos riscos. Importa para responsabilidade institucional, não apenas para o valor do prejuízo.
- **Evidência no corpo:** “a equipe técnica já sabia que parte das carteiras de crédito consignado oferecidas por Daniel Vorcaro não tinha lastro”. O BRB fora procurado e ainda não se manifestara naquele texto.

### M18 — Relevância 18
- **2026-04-22 — [BRB aprova aumento de capital de até R$ 8,8 bilhões para reduzir rombo deixado pelo Master](https://g1.globo.com/jornal-nacional/noticia/2026/04/22/brb-aprova-aumento-de-capital-de-ate-r-88-bilhoes-para-reduzir-rombo-deixado-pelo-master.ghtml)**
- **Motivo:** documenta uma resposta concreta ao prejuízo e sua possível incidência sobre as contas do Distrito Federal. Complementa M16 com medida efetiva, não só estimativa.
- **Evidência no corpo:** “o governo do DF deverá aportar pelo menos R$ 6 bilhões para seguir como acionista majoritário”. **Cuidado:** aprovação de aumento não significa que todo aporte já ocorreu.

### M19 — Relevância 19
- **2026-03-19 — [Vorcaro firma termo de confidencialidade; Mendonça barra domiciliar e transfere banqueiro para a PF](https://g1.globo.com/politica/blog/andreia-sadi/post/2026/03/19/bastidores-vorcaro-assinou-termo-de-confidencialidade-para-colaborar-mendonca-rejeitou-domiciliar-e-transferiu-banqueiro-para-a-pf.ghtml)**
- **Motivo:** esclarece a situação real da possível colaboração, evitando tratar negociação como delação concluída. Fica abaixo dos fatos financeiros e policiais já documentados.
- **Evidência no corpo:** “sem antecipar qualquer benefício antes da comprovação efetiva de colaboração”. **Limite:** apuração de bastidores; termo de confidencialidade não equivale a acordo homologado.

### M20 — Relevância 20
- **2026-03-05 — [Após ‘rombo’ do caso Master, bancos fecham acordo para antecipar R$ 32,5 bilhões ao FGC](https://g1.globo.com/economia/noticia/2026/03/05/bancos-pagamentos-fgc.ghtml)**
- **Motivo:** explica quem recompõe o fundo após os ressarcimentos e dimensiona o custo coletivo no setor bancário. É central como consequência, mas demanda mais contexto que os primeiros artigos.
- **Evidência no corpo:** “cinco anos de contribuições ao fundo, em um total de R$ 32,5 bilhões”. A recomposição é por instituições associadas; não presumir transferência direta do Tesouro.

**Exclusões e substituições importantes:** notícias sobre festas, jatos ou mansão de Vorcaro não explicavam o mecanismo; notas de cada fundo municipal foram preteridas por M07; a negociação intermediária TCU–BC de 12/01 foi substituída pelo resultado técnico de M13. O explicador municipal de investimentos de Santo Antônio de Posse, embora informativo, perdeu lugar para M20, de alcance mais geral. Essas exclusões do conjunto não são rótulos universais de irrelevância.

## 5. Caso I — Descontos associativos indevidos no INSS

**Consulta sugerida:** “Como funcionavam os descontos não autorizados nas aposentadorias do INSS, como as vítimas foram ressarcidas e o que as investigações descobriram?”

**Delimitação:** mensalidades associativas sem autorização, Operação Sem Desconto, reparação e investigação parlamentar correspondente. Exclui fraudes distintas na concessão de benefícios, atestados falsos ou toda notícia sobre crédito consignado sem ligação demonstrada com essa história.

**Por que é uma história continuada:** a revelação original ocorreu antes do recorte, mas o período contém documentação do mecanismo, acordo e pagamentos, prisões, alteração legislativa, encerramento da CPMI e balanço de um ano. São dez meses distintos nas seleções.

**Lógica do topo:** I01 dá dimensão e situação da reparação; I02 explica um braço do esquema; I03 contextualiza a investigação; I04 mostra como as vítimas eram enganadas; I05 documenta o início do reembolso. Não se deve generalizar o mecanismo específico da Conafer a todas as entidades sem evidência.

### I01 — Relevância 1
- **2026-04-23 — [Fraude no INSS: um ano após operação revelar desvios, ressarcimento a segurados chega a quase R$ 3 bilhões](https://g1.globo.com/politica/noticia/2026/04/23/fraude-no-inss-um-ano-apos-operacao-revelar-desvios-ressarcimento-a-segurados-chega-a-quase-r-3-bilhoes.ghtml)**
- **Motivo:** síntese retrospectiva com mecanismo, escala, reparação e pendências. É a melhor entrada para quem não acompanhou os meses anteriores.
- **Evidência no corpo:** “o órgão devolveu R$ 2,95 bilhões a 4,34 milhões de pessoas”. O balanço citado tem data de referência em março; não é medição feita no próprio dia da publicação.

### I02 — Relevância 2
- **2025-11-14 — [Fraude no INSS: esquema de desvios da Conafer tinha núcleos político, de comando e financeiro, segundo PF](https://g1.globo.com/politica/noticia/2025/11/14/fraude-no-inss-esquema-de-desvios-da-conafer-tinha-nucleos-politico-de-comando-e-financeiro-segundo-pf.ghtml)**
- **Motivo:** apresenta estrutura e divisão de tarefas, substituindo uma lista de suspeitos por explicação causal. Distingue valores atribuídos à Conafer da estimativa para todas as entidades.
- **Evidência no corpo:** “três núcleos de pessoas, com divisão de tarefas e hierarquia”. O esquema descrito é o atribuído à Conafer pela PF.

### I03 — Relevância 3
- **2025-08-26 — [CPMI do INSS: veja perguntas e respostas sobre a investigação](https://g1.globo.com/economia/noticia/2025/08/26/cpmi-do-inss-veja-perguntas-e-respostas.ghtml)**
- **Motivo:** explica o acontecimento e a função da comissão para o leitor iniciante. Mais abrangente que notas de convocação, troca de comando ou bate-boca.
- **Evidência no corpo:** “os suspeitos cobravam mensalidades irregulares, descontadas diretamente dos benefícios”. **Limite:** expectativas sobre a CPMI são daquele momento; I09 mostra como ela terminou.

### I04 — Relevância 4
- **2025-06-08 — [Áudios mostram como call centers enganam idosos para autorizar descontos indevidos no INSS](https://g1.globo.com/fantastico/noticia/2025/06/08/audios-mostram-como-call-centers-enganam-idosos-para-autorizar-descontos-indevidos-no-inss.ghtml)**
- **Motivo:** demonstra o mecanismo de engano por gravações e relatos, ligando a estrutura abstrata ao que ocorria com os segurados. O depoimento individual tem função explicativa, não apenas emocional.
- **Evidência no corpo:** “Ex-funcionários de call centers confirmam que gravações são forjadas”. As práticas relatadas não significam que todos os descontos associativos fossem ilegais.

### I05 — Relevância 5
- **2025-07-24 — [Fraude no INSS: governo inicia reembolso a vítimas nesta quinta](https://g1.globo.com/economia/noticia/2025/07/24/fraude-no-inss-governo-inicia-reembolso-a-vitimas-nesta-quinta-feira-saiba-como-solicitar.ghtml)**
- **Motivo:** marco de reparação com elegibilidade, forma de pagamento e regras do acordo. Mais útil que anúncios repetidos de intenção de pagar.
- **Evidência no corpo:** “Todo o processo será feito por via administrativa, sem ação judicial”. **Limite:** o prazo antigo mencionado no texto foi posteriormente prorrogado; consultar I15.

### I06 — Relevância 6
- **2025-11-13 — [PF prende Alessandro Stefanutto, ex-presidente do INSS, em operação que investiga esquema de desvio bilionário contra aposentados e pensionistas](https://g1.globo.com/jornal-nacional/noticia/2025/11/13/pf-prende-alessandro-stefanutto-ex-presidente-do-inss-em-operacao-que-investiga-esquema-de-desvio-bilionario-contra-aposentados-e-pensionistas.ghtml)**
- **Motivo:** documenta avanço sobre a antiga cúpula do órgão e relata a conduta atribuída ao ex-presidente. É desenvolvimento de responsabilidade institucional, não só nova apreensão.
- **Evidência no corpo:** “Investigadores afirmam que ele recebeu propina de R$ 250 mil por mês”. Atribuição policial; não condenação.

### I07 — Relevância 7
- **2025-12-18 — [Fraude do INSS: PF prende secretário-executivo do Ministério da Previdência e faz buscas em endereços do senador Weverton Rocha, do PDT](https://g1.globo.com/jornal-nacional/noticia/2025/12/18/fraude-do-inss-pf-prende-secretario-executivo-do-ministerio-da-previdencia-e-faz-buscas-em-enderecos-do-senador-weverton-rocha-do-pdt.ghtml)**
- **Motivo:** mostra a ampliação da apuração à cúpula ministerial e à alegada sustentação política, sem omitir a diferença entre busca, pedido de prisão e decisão judicial.
- **Evidência no corpo:** “ainda não há prova direta de que Weverton recebeu dinheiro ou comandou o esquema”. Esse é o fundamento relatado para a negativa do pedido de prisão do senador.

### I08 — Relevância 8
- **2026-01-07 — [Lula sanciona lei que proíbe descontos nos benefícios pagos pelo INSS, mas veta 'busca ativa' de aposentados lesados](https://g1.globo.com/politica/noticia/2026/01/07/lula-sanciona-lei-que-proibe-descontos-nos-beneficios-pagos-pelo-inss-e-determina-busca-ativa-de-aposentados-lesados.ghtml)**
- **Motivo:** documenta a resposta legislativa e uma restrição importante à reparação. Evita resumir o caso apenas como investigação criminal.
- **Evidência no corpo:** “esse trecho foi vetado pelo presidente”. **Correção editorial:** título e corpo corrigem a informação inicial; a URL ainda diz que a lei “determina busca ativa”. Não inferir conteúdo pelo slug.

### I09 — Relevância 9
- **2026-03-28 — [CPMI do INSS rejeita relatório que pedia indiciamento de 'Lulinha' e ex-ministros de Lula e Bolsonaro](https://g1.globo.com/politica/noticia/2026/03/28/cpmi-do-inss-relatorio.ghtml)**
- **Motivo:** registra o desfecho parlamentar e impede confundir a proposta do relator com conclusão aprovada pela comissão. É mais importante que a votação nominal isolada.
- **Evidência no corpo:** “a comissão encerra os trabalhos sem um relatório aprovado”. Rejeição parlamentar também não equivale a absolvição judicial dos citados.

### I10 — Relevância 10
- **2025-07-03 — [Fraude no INSS: Toffoli dá aval a acordo da União para devolução de dinheiro a aposentados do INSS](https://g1.globo.com/politica/noticia/2025/07/03/fraude-no-inss-toffoli-da-aval-a-acordo-para-devolucao-de-dinheiro-a-aposentados-do-inss.ghtml)**
- **Motivo:** explica a base jurídica da solução administrativa que se materializa em I05. Entra abaixo do início efetivo dos pagamentos por ser uma etapa preparatória.
- **Evidência no corpo:** “evitar a judicialização de casos em massa”. A homologação ainda dependia de referendo do plenário no momento relatado.

### I11 — Relevância 11
- **2025-09-14 — [Controles do INSS contra descontos irregulares são "frágeis", aponta CGU](https://g1.globo.com/politica/noticia/2025/09/14/cgu-auditoria-descontos-indevidos-inss.ghtml)**
- **Motivo:** identifica falhas de controle que ajudam a explicar como a fraude foi possível. É evidência institucional, não opinião genérica sobre corrupção.
- **Evidência no corpo:** “em 92% dos processos analisados”. **Limite:** a auditoria examinou amostra de 12 acordos; não apresentar o percentual como censo de todos os convênios do INSS.

### I12 — Relevância 12
- **2025-09-12 — [PF prende o 'Careca do INSS' em operação contra fraudes no INSS](https://g1.globo.com/sp/sao-paulo/noticia/2025/09/12/pf-faz-operacao-para-prender-suspeitos-de-envolvimento-nas-fraudes-do-inss.ghtml)**
- **Motivo:** apresenta o papel atribuído a um operador central e a prisão de Camisotti. Mais útil que matérias dedicadas somente aos carros ou objetos apreendidos.
- **Evidência no corpo:** “ele transferiu R$ 9,3 milhões para pessoas relacionadas a servidores do INSS entre 2023 e 2024”. As atribuições permanecem investigativas.

### I13 — Relevância 13
- **2025-06-13 — [Fraude do INSS: 3,1 milhões já acusaram descontos irregulares; associações abriram 512 mil contestações](https://g1.globo.com/economia/noticia/2025/06/13/fraude-do-inss-31-milhoes-ja-acusaram-descontos-irregulares-associacoes-abriram-512-mil-contestacoes.ghtml)**
- **Motivo:** dimensiona a contestação inicial e explica a disputa sobre autorizações. Tem valor para reconstruir a escala, mas os números posteriores de I01 são mais úteis como balanço.
- **Evidência no corpo:** “Das 43 entidades envolvidas, 15 ainda não apresentaram qualquer resposta”. Contestações não são, individualmente, fraudes já comprovadas.

### I14 — Relevância 14
- **2025-10-09 — [Fraude no INSS: governo ressarciu 43% do que foi descontado de aposentadorias até agora](https://g1.globo.com/politica/noticia/2025/10/09/fraude-no-inss-governo-ressarciu-43percent-do-que-foi-descontado-de-aposentadorias-ate-agora.ghtml)**
- **Motivo:** avalia andamento e insuficiência da reparação, distinguindo bases de cálculo. Não é apenas atualização de quantos moradores de uma cidade receberam.
- **Evidência no corpo:** “a Dataprev estima que R$ 3,7 bilhões foram descontados indevidamente”. O denominador difere dos R$ 6,3 bilhões estimados originalmente por PF/CGU; não misturar as séries.

### I15 — Relevância 15
- **2026-03-27 — [Governo prorroga até junho prazo de contestação de descontos indevidos de aposentados do INSS](https://g1.globo.com/economia/noticia/2026/03/27/governo-prorroga-ate-junho-prazo-de-contestacao-de-descontos-indevidos-de-aposentados-do-inss.ghtml)**
- **Motivo:** corrige a utilidade prática de guias antigos ao documentar extensão do prazo e consequências da adesão. Central para uma pessoa afetada, mais específica para o leitor geral.
- **Evidência no corpo:** “renuncia ao direito de processar o INSS futuramente pela fraude”. O texto preserva a possibilidade de ação contra as associações.

### I16 — Relevância 16
- **2026-03-17 — [PF diz que deputada do Ceará era 'articuladora política' de esquema de fraudes no INSS](https://g1.globo.com/politica/noticia/2026/03/17/pf-aponta-que-deputada-do-ce-era-articuladora-politica-de-esquema-de-fraudes-no-inss.ghtml)**
- **Motivo:** documenta nova frente da mesma operação e o papel atribuído a agente política, com medidas cautelares e defesa. Não entra apenas por citar uma pessoa conhecida.
- **Evidência no corpo:** “alvo de medidas cautelares e passou a ser monitorada por tornozeleira eletrônica”. A defesa nega ato ilícito; a suspeita não é culpa estabelecida.

### I17 — Relevância 17
- **2026-03-26 — [Por 8 votos a 2, Supremo decide que cabe ao Congresso prorrogar ou não a CPMI do INSS](https://g1.globo.com/jornal-nacional/noticia/2026/03/26/por-8-votos-a-2-supremo-decide-que-cabe-ao-congresso-prorrogar-ou-nao-a-cpmi-do-inss.ghtml)**
- **Motivo:** explica o limite institucional que antecede o encerramento da comissão. É contexto jurídico complementar; I09 entrega o resultado final mais diretamente.
- **Evidência no corpo:** “A comissão apura fraudes nos descontos de aposentados e pensionistas”. O objeto é a prorrogação da CPMI, não o encerramento de todas as investigações policiais.

### I18 — Relevância 18
- **2026-03-27 — [CPMI do INSS: relator pede indiciamento de mais de 200 pessoas, incluindo 'Lulinha' e ex-ministros de Lula e Bolsonaro](https://g1.globo.com/politica/noticia/2026/03/27/cpmi-do-inss-relatorio.ghtml)**
- **Motivo:** documenta o conteúdo da proposta cuja rejeição aparece em I09. A posição é inferior justamente porque a proposta não se tornou relatório aprovado.
- **Evidência no corpo:** “Este texto não é o final da CPMI”. Não tratar pedidos de indiciamento do relator como conclusão da comissão, indiciamento policial consumado ou condenação.

### I19 — Relevância 19
- **2025-09-29 — [CPMI do INSS ouve presidente da Conafer, entidade que, entre 2019 e 2023, aumentou volume de descontos de R$ 400 mil para R$ 202 milhões](https://g1.globo.com/jornal-nacional/noticia/2025/09/29/cpmi-do-inss-ouve-presidente-da-conafer-entidade-que-entre-2019-e-2023-aumentou-volume-de-descontos-de-r-400-mil-para-r-202-milhoes.ghtml)**
- **Motivo:** traz questionamentos concretos sobre escala dos descontos e a negativa do dirigente. Complementa o desenho policial de I02, mas exige mais contexto.
- **Evidência no corpo:** “mais de 70 mil beneficiários da Conafer reclamaram de descontos ilegais”. Questionamentos em depoimento não demonstram, sozinhos, cada acusação.

### I20 — Relevância 20
- **2025-07-24 — [Fraude do INSS: o que fazer se a instituição apresentou provas falsas para comprovar o desconto? Veja dicas](https://g1.globo.com/economia/noticia/2025/07/24/fraude-do-inss-veja-dicas.ghtml)**
- **Motivo:** explica uma dificuldade central da reparação: entidades supostamente usam nova documentação fraudada para sustentar o desconto original. Tem foco mais estreito que o guia geral e o balanço.
- **Evidência no corpo:** “mais de seis entidades que compraram um software para falsificação de assinaturas”. Atribuição ao presidente do INSS; orientações procedimentais são históricas.

**Exclusões e substituições importantes:** fraudes em atestados e concessão de benefícios não foram misturadas aos descontos associativos; notas estaduais de ressarcimento perderam lugar para balanços nacionais; um guia de Santa Catarina, apesar do título genérico, tinha entrada fortemente local e foi substituído por I20. Notícias centradas em convocar familiares de Vorcaro sem explicar os descontos não entraram automaticamente neste tema.

## 6. Caso T — Tarifaço dos EUA sobre produtos brasileiros

**Consulta sugerida:** “Por que os EUA impuseram tarifas ao Brasil, quais produtos foram afetados e como as negociações e decisões judiciais mudaram a cobrança?”

**Delimitação:** sobretaxa dirigida ao Brasil em 2025, exceções, resposta brasileira, negociações e reconfiguração jurídica em 2026. Decisões globais entram quando são indispensáveis para explicar a cobrança sobre produtos brasileiros. Não é um conjunto sobre todas as políticas externas de Trump.

**Por que é uma história continuada:** anúncio, decreto, vigência, auxílio a exportadores, negociação, retiradas parciais, decisão judicial e investigação subsequente. Os artigos selecionados cobrem sete meses distintos.

**Lógica do topo:** T01 oferece cronologia; T02 e T03 separam anúncio de ato formal; T04 registra a virada judicial; T05 esclarece a cobrança e as exceções posteriores. **Não há uma única alíquota válida para todos os produtos e todas as datas.**

### T01 — Relevância 1
- **2026-02-21 — [Tarifaço de Trump: veja cronologia e como ficam as tarifas ao Brasil](https://g1.globo.com/economia/noticia/2026/02/21/tarifaco-de-trump-veja-a-cronologia-e-como-ficam-as-tarifas-para-o-brasil.ghtml)**
- **Motivo:** resumo cronológico com ligação direta entre origem, decisão judicial e tratamento do Brasil. Melhor entrada que uma notícia isolada sobre uma fala presidencial.
- **Evidência no corpo:** “a decisão da Suprema Corte anulou todas as tarifas aplicadas com base na IEEPA”. **Limite:** retrata a etapa inicial da nova taxa de 10%; T05 esclarece a situação de 24/02.

### T02 — Relevância 2
- **2025-07-09 — [Trump manda carta a Lula e anuncia tarifa de 50% sobre produtos brasileiros](https://g1.globo.com/economia/noticia/2025/07/09/trump-manda-carta-a-lula-e-anuncia-tarifa-de-50percent-sobre-produtos-brasileiros.ghtml)**
- **Motivo:** fato deflagrador da crise específica, com justificativa política declarada e resposta brasileira. Permite distinguir a decisão contra o Brasil da política global anterior.
- **Evidência no corpo:** “Trump citou Jair Bolsonaro”. **Limite:** a entrada em vigor anunciada para 1º de agosto foi alterada no decreto posterior; não tomar a previsão inicial como data efetiva.

### T03 — Relevância 3
- **2025-07-30 — [Trump assina decreto que impõe tarifa de 50% ao Brasil](https://g1.globo.com/economia/noticia/2025/07/30/trump-assina-decreto-que-impoe-tarifa-de-50percent-ao-brasil.ghtml)**
- **Motivo:** transforma anúncio em ordem formal, detalhando composição da taxa e exceções. É necessário para não repetir que toda exportação brasileira pagaria 50%.
- **Evidência no corpo:** “uma tarifa adicional de 40% sobre produtos brasileiros, elevando o total para 50%”. O corpo informa vigência em 6 de agosto.

### T04 — Relevância 4
- **2026-02-20 — [Suprema Corte dos EUA derruba tarifaço imposto por Trump](https://g1.globo.com/economia/noticia/2026/02/20/suprema-corte-dos-eua-trump-tarifas-globais.ghtml)**
- **Motivo:** explica a mudança de base jurídica que atinge a sobretaxa brasileira. A dimensão global é pertinente porque altera diretamente esta história.
- **Evidência no corpo:** “As tarifas específicas sobre importações de aço e alumínio, incluindo produtos brasileiros, não são afetadas pela decisão”. Não interpretar a manchete como eliminação de todas as tarifas americanas.

### T05 — Relevância 5
- **2026-02-24 — [Tarifaço de Trump: veja quais produtos brasileiros ficam isentos](https://g1.globo.com/economia/noticia/2026/02/24/tarifaco-de-trump-veja-quais-produtos-ficam-isentos.ghtml)**
- **Motivo:** fecha uma ambiguidade importante: distingue o anúncio de 15% da cobrança formal de 10% e detalha isenções. Tem alto valor prático e interpretativo.
- **Evidência no corpo:** “até esta terça-feira não havia publicado uma diretriz formal para oficializar o aumento”. É situação daquela data, não garantia sobre regras futuras.

### T06 — Relevância 6
- **2025-08-06 — [Tarifaço de Trump: taxas de 50% contra o Brasil entram em vigor nesta quarta](https://g1.globo.com/economia/noticia/2025/08/06/tarifaco-de-trump-taxas-de-50percent-contra-o-brasil-entram-em-vigor-nesta-quarta-feira.ghtml)**
- **Motivo:** documenta o início efetivo da cobrança e a manutenção das exceções. Complementa T03, distinguindo ato publicado de aplicação concreta.
- **Evidência no corpo:** “Entram em vigor nesta quarta-feira (6) as tarifas de importação de 50%”. Menor prioridade pela sobreposição parcial com o decreto.

### T07 — Relevância 7
- **2025-11-20 — [EUA anunciam fim das tarifas de 40% sobre dezenas de produtos brasileiros; carne, café e frutas estão na lista](https://g1.globo.com/jornal-nacional/noticia/2025/11/20/eua-anunciam-fim-das-tarifas-de-40percent-sobre-dezenas-de-produtos-brasileiros-carne-cafe-e-frutas-estao-na-lista.ghtml)**
- **Motivo:** marco de reversão parcial após negociações, com produtos abrangidos e efeito retroativo. Mais informativo que comemorações ou memes sobre o anúncio.
- **Evidência no corpo:** “A isenção tem efeito retroativo”. **Limite:** não foi revogação integral das tarifas sobre todos os produtos; T10 identifica o que permaneceu.

### T08 — Relevância 8
- **2025-08-13 — [Lula anuncia R$ 30 bilhões em crédito para empresas afetadas pelo tarifaço](https://g1.globo.com/economia/noticia/2025/08/13/tarifaco-de-trump-governo-apresenta-plano-de-socorro-as-empresas-com-linha-de-credito-de-r-30-bi.ghtml)**
- **Motivo:** explica a principal resposta econômica doméstica, condições de acesso, tributos e compras públicas. Foi preferido à página de transmissão do evento, cujo corpo era raso.
- **Evidência no corpo:** “O acesso às linhas estará condicionado à manutenção do número de empregos”. Crédito anunciado não equivale a valor já desembolsado.

### T09 — Relevância 9
- **2025-10-27 — [Tarifaço foi suspenso? Do que Lula e Trump falaram? Veja perguntas e respostas sobre o encontro entre os dois presidentes](https://g1.globo.com/mundo/noticia/2025/10/27/encontro-lula-trump-perguntas-e-respostas.ghtml)**
- **Motivo:** explica o primeiro encontro e separa abertura de negociação de suspensão efetiva. Evita conclusão errada a partir da cordialidade entre os presidentes.
- **Evidência no corpo:** “isso não aconteceu imediatamente”. Refere-se à suspensão das tarifas durante as negociações solicitada pelo Brasil.

### T10 — Relevância 10
- **2025-11-21 — [Tarifaço de Trump: o que continua com 40% e o que deixou de ser taxado](https://g1.globo.com/economia/noticia/2025/11/21/tarifaco-dos-eua-o-que-continua-com-40percent-e-o-que-deixou-de-ser-taxado.ghtml)**
- **Motivo:** traduz o acordo parcial em efeitos setoriais, mostrando por que a história não terminara em novembro. Complementa diretamente T07.
- **Evidência no corpo:** “os produtos manufaturados seguem com taxa de 40%”. A lista é a daquela fase; não reaplicá-la sem atualização após fevereiro.

### T11 — Relevância 11
- **2025-10-06 — [Em conversa com Trump, Lula pede o fim das tarifas e das sanções contra autoridades brasileiras](https://g1.globo.com/jornal-nacional/noticia/2025/10/06/em-conversa-com-trump-lula-pede-o-fim-das-tarifas-e-das-sancoes-contra-autoridades-brasileiras.ghtml)**
- **Motivo:** registra abertura de canal direto que antecede a reunião presencial e a retirada parcial. É um marco diplomático, não mera troca de elogios.
- **Evidência no corpo:** “solicitou a retirada da sobretaxa de 40% imposta a produtos nacionais”. O telefonema não retirou, por si só, a cobrança.

### T12 — Relevância 12
- **2025-07-30 — [Tarifa de 50% contra o Brasil tem longa lista de exceções; veja quais](https://g1.globo.com/economia/noticia/2025/07/30/taxa-dos-eua-tem-excecoes.ghtml)**
- **Motivo:** esclarece o alcance real do decreto inicial com detalhamento de produtos. Sua utilidade é grande, mas parte da informação já aparece em T03.
- **Evidência no corpo:** “deixar quase 700 itens sem a cobrança extra”. Isenção da cobrança adicional não significa necessariamente ausência de qualquer tarifa prévia.

### T13 — Relevância 13
- **2025-08-06 — [Governo Lula aciona OMC contra tarifaço de Trump](https://g1.globo.com/economia/noticia/2025/08/06/governo-lula-aciona-omc-contra-tarifaco-de-trump.ghtml)**
- **Motivo:** documenta a resposta multilateral e seus limites processuais. Mais central que manifestações genéricas de apoio de outros governos.
- **Evidência no corpo:** “A consulta é uma etapa anterior à eventual abertura de um painel”. Não apresentar a consulta como vitória judicial ou suspensão imediata das tarifas.

### T14 — Relevância 14
- **2025-07-10 — [Lei da Reciprocidade: entenda o texto citado por Lula para responder tarifaço de Trump](https://g1.globo.com/politica/noticia/2025/07/10/lei-da-reciprocidade-entenda-o-texto-citado-por-lula-para-responder-tarifaco-de-trump.ghtml)**
- **Motivo:** explica instrumento frequentemente citado na crise e a possibilidade de contramedidas. É contexto relevante, mas possibilidade legal não é resposta econômica já executada.
- **Evidência no corpo:** “prevê contramedidas em casos de retaliações comerciais externas”. Ler em conjunto com T08, que registra medidas efetivamente anunciadas.

### T15 — Relevância 15
- **2025-11-06 — [Balança Comercial: Exportações para os EUA caem 38% com tarifaço](https://g1.globo.com/economia/noticia/2025/11/06/em-meio-ao-tarifaco-exportacoes-aos-eua-despencam-38percent-em-outubro-brasil-tem-superavit-em-toda-balanca-comercial.ghtml)**
- **Motivo:** oferece consequência mensurada no comércio bilateral, evitando depender só de projeções empresariais. Menor prioridade por ser balanço mensal.
- **Evidência no corpo:** “as exportações aos EUA somaram US$ 2,21 bilhões em outubro”. A comparação é com outubro do ano anterior; não atribuir causalidade exclusiva às tarifas sem análise adicional.

### T16 — Relevância 16
- **2026-01-06 — [Balança comercial tem saldo de US$ 68 bi em 2025; resultado é afetado por tarifaço de Trump](https://g1.globo.com/jornal-nacional/noticia/2026/01/06/balanca-comercial-tem-saldo-de-us-68-bi-em-2025-resultado-e-afetado-por-tarifaco-de-trump.ghtml)**
- **Motivo:** contrapõe perda no mercado americano e diversificação de destinos, oferecendo balanço anual mais equilibrado que relatos isolados de prejuízo.
- **Evidência no corpo:** “o Brasil ampliou as exportações para outros mercados”. O saldo global positivo não anula perdas específicas na relação com os EUA.

### T17 — Relevância 17
- **2026-02-20 — [EUA encerram parte do tarifaço e Trump assina taxação global de 10%](https://g1.globo.com/economia/noticia/2026/02/20/casa-branca-tarifaco.ghtml)**
- **Motivo:** documenta a reação formal do Executivo à decisão judicial. Acrescenta a substituição de instrumento legal, mas se sobrepõe parcialmente a T04 e T05.
- **Evidência no corpo:** “formalizou a medida que cria uma nova tarifa global de 10%”. O anúncio posterior de 15% precisa ser distinguido do ato então publicado.

### T18 — Relevância 18
- **2026-03-12 — [EUA incluem Brasil em investigação que pode criar novas tarifas](https://g1.globo.com/economia/noticia/2026/03/12/eua-abrem-investigacao-sobre-praticas-comerciais-desleais-de-60-paises-devido-a-trabalho-forcado.ghtml)**
- **Motivo:** demonstra continuidade após a derrota judicial das tarifas anteriores, com possível uso de outra base legal. Não pressupõe que a nova taxação já exista.
- **Evidência no corpo:** “A nova investigação se baseia na Seção 301”. **Distinção:** investigação sobre trabalho forçado não é comprovação de prática irregular pelo Brasil.

### T19 — Relevância 19
- **2025-11-14 — [Trump reduz tarifas sobre café, carne e frutas, produtos exportados pelo Brasil](https://g1.globo.com/economia/agronegocios/noticia/2025/11/14/eua-suspendem-tarifa-de-50percent-para-cafe-carne-banana-e-acai-brasileiros.ghtml)**
- **Motivo:** registra a etapa intermediária que impede confundir duas reduções diferentes de novembro. Fica abaixo de T07, que mostra a mudança posterior mais ampla para esses produtos.
- **Evidência no corpo:** “Para o Brasil, as taxas caíram de 50% para 40%”. O slug sugere suspensão de 50%, mas o corpo esclarece redução de dez pontos percentuais.

### T20 — Relevância 20
- **2025-10-16 — [Tarifa de Trump trava exportações e força Brasil a buscar novos mercados; governo tenta reverter impasse nesta quinta](https://g1.globo.com/economia/noticia/2025/10/16/tarifa-de-trump-trava-exportacoes-e-forca-brasil-a-buscar-novos-mercados.ghtml)**
- **Motivo:** explica por que redirecionar vendas não resolve imediatamente o impacto do tarifaço: acordos, logística e adaptações exigem tempo. É contexto econômico complementar, não previsão necessária para entender os marcos.
- **Evidência no corpo:** “redirecionar exportações dos EUA para outros mercados não é uma tarefa simples”. Projeções de especialistas sobre negociações futuras não são tratadas como fatos consumados.

**Exclusões e substituições importantes:** excluídas tarifas de transporte e conflitos comerciais sem relação central com o Brasil. A página ao vivo de 13/08 foi substituída por T08. A retrospectiva de Lula–Trump de 05/05 era ampla, com muitos episódios não tarifários, e foi preterida. O explicador de 24/02 “relembre os fatos e entenda efeitos da nova taxa” foi preterido porque o corpo examinado alternava a cobrança formal de 10% com trechos tratando 15% como resultado; T05 é mais claro nessa distinção. A exclusão foi de utilidade/consistência para este conjunto, não mera ausência de palavras-chave.

## 7. Caso A — Metanol em bebidas adulteradas

**Consulta sugerida:** “Como surgiu a crise de intoxicações por metanol em bebidas no Brasil, o que a investigação descobriu e como as autoridades responderam?”

**Delimitação:** surto de 2025, falsificação e rastreamento da substância, resposta sanitária e persistência de casos em 2026. O tema reúne a crise sanitária nacional; **não presume que todos os focos tenham o mesmo fornecedor ou organização criminosa**.

**Por que é uma história continuada:** alerta inicial, investigação laboratorial, descoberta de fábricas e fornecedores, distribuição de antídotos, encerramento da estrutura emergencial e novos casos. São cinco meses distintos nas seleções.

**Lógica do topo:** A01 explica a cadeia identificada em SP; A02 dimensiona o surto e o fim da resposta emergencial; A03 traz evidência posterior sobre o esquema; A04 contextualiza a descoberta inicial; A05 explica o risco químico. **A hipótese inicial citada em A04 foi superada por achados de A08 e A01.**

### A01 — Relevância 1
- **2025-10-18 — [Entenda como funcionava esquema que levou metanol até bebidas alcoólicas em SP](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/18/do-posto-aos-bares-entenda-como-funcionava-esquema-que-levou-metanol-ate-bebidas-alcoolicas-em-sp.ghtml)**
- **Motivo:** melhor explicação causal da cadeia identificada: combustível, fábrica clandestina, envase e bares. Vai além de anunciar mortes ou apreensões.
- **Evidência no corpo:** “O metanol percorreu um caminho que começa em dois postos de combustível no ABC Paulista”. **Limite:** cadeia investigada em SP; não prova origem comum para todos os casos do país.

### A02 — Relevância 2
- **2025-12-08 — [Governo encerra Sala de Situação sobre intoxicação por metanol após queda de casos; 22 mortes foram confirmadas](https://g1.globo.com/saude/noticia/2025/12/08/governo-encerra-sala-de-situacao-sobre-intoxicacao-por-metanol-apos-queda-de-casos-22-mortes-foram-confirmadas.ghtml)**
- **Motivo:** dá dimensão nacional e um marco de encerramento da resposta extraordinária, sem anunciar desaparecimento do risco. Contrabalança a concentração paulista de A01.
- **Evidência no corpo:** “73 pessoas foram diagnosticadas com intoxicação por metanol e 22 morreram”. **Limites:** balanço daquele período, não total final de 2026; o corpo diz “segunda-feira (9)”, divergindo da data armazenada 08/12.

### A03 — Relevância 3
- **2026-01-25 — [Áudios revelam esquema de bebidas com metanol ligado a mortes em SP](https://g1.globo.com/fantastico/noticia/2026/01/25/audios-revelam-esquema-de-bebidas-com-metanol-ligado-a-mortes-em-sp.ghtml)**
- **Motivo:** atualiza a explicação causal com mensagens e reconstrução da distribuição. É avanço substantivo, não repetição do número de casos.
- **Evidência no corpo:** “foi possível montar um mapa e identificar os estabelecimentos que compraram bebidas da fábrica clandestina”. O texto distingue condenação por falsificação de investigação por homicídio.

### A04 — Relevância 4
- **2025-10-04 — [Metanol em bebidas alcoólicas: veja o que se sabe até agora sobre casos de intoxicação](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/04/metanol-em-bebidas-alcoolicas-veja-o-que-se-sabe-ate-agora-sobre-casos-de-intoxicacao.ghtml)**
- **Motivo:** explicador abrangente da descoberta do surto, riscos, proteção e resposta inicial. Ajuda a reconstruir como casos dispersos viraram uma crise reconhecida.
- **Evidência no corpo:** “não se tratava de episódios isolados”. **Superação importante:** a hipótese de higienização de garrafas com metanol, então destacada no texto, não deve ser apresentada como explicação final; ver A08/A01.

### A05 — Relevância 5
- **2025-09-30 — [Etanol x metanol: qual é a diferença e por que há risco de envenenamento](https://g1.globo.com/educacao/noticia/2025/09/30/metanol-x-etanol-qual-e-a-diferenca-e-por-que-ha-risco-de-envenenamento.ghtml)**
- **Motivo:** elimina uma confusão essencial sobre substâncias parecidas e explica por que o consumidor não consegue verificar a segurança pelo aspecto da bebida.
- **Evidência no corpo:** “É IMPOSSÍVEL NOTAR A DIFERENÇA entre metanol e etanol sem testes de laboratório”. Não é uma reportagem química genérica: parte diretamente das mortes da crise.

### A06 — Relevância 6
- **2025-10-02 — [Ministério instala sala de situação para monitorar intoxicação por metanol](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/02/ministerio-da-saude-instala-sala-de-situacao-para-monitorar-casos-de-intoxicacao-por-metanol-no-pais.ghtml)**
- **Motivo:** mostra reconhecimento do caráter anormal e coordenação nacional da resposta. É o marco institucional que antecede o encerramento narrado em A02.
- **Evidência no corpo:** “unificar as informações sobre os casos de intoxicação pelo país”. A publicação é de 02/10, mas relata instalação em 01/10; não confundir os dois campos temporais.

### A07 — Relevância 7
- **2025-09-28 — [Ministério faz alerta sobre bebidas alcoólicas adulteradas com metanol após intoxicações em SP; Duas mortes já foram registradas](https://g1.globo.com/sp/sao-paulo/noticia/2025/09/28/ministerio-faz-alerta-sobre-bebidas-alcoolicas-adulteradas-com-metanol-apos-intoxicacoes-em-sp-ao-menos-duas-mortes-ja-foram-registradas.ghtml)**
- **Motivo:** documenta o alerta inicial e as orientações a estabelecimentos sobre lotes e preservação de provas. Informa o início da resposta, não apenas medo dos consumidores.
- **Evidência no corpo:** “interromper imediatamente a venda do lote”. Os números e a classificação de óbitos são preliminares e não devem substituir balanços posteriores.

### A08 — Relevância 8
- **2025-10-08 — [Perícia de bebidas destiladas adulteradas descarta contaminação acidental e afirma que metanol foi adicionado de forma criminosa](https://g1.globo.com/jornal-nacional/noticia/2025/10/08/pericia-de-bebidas-destiladas-adulteradas-descarta-contaminacao-acidental-e-afirma-que-metanol-foi-adicionado-de-forma-criminosa.ghtml)**
- **Motivo:** muda o estado da evidência ao afastar hipóteses iniciais para as amostras analisadas. É central para não perpetuar uma explicação preliminar como fato.
- **Evidência no corpo:** “exclua essa hipótese de uma destilação mal feita”. **Limite:** conclusão sobre amostras periciadas; não identifica automaticamente todos os autores ou fornecedores.

### A09 — Relevância 9
- **2025-09-29 — [Metanol: quais são os sintomas da intoxicação causada por bebidas adulteradas](https://g1.globo.com/ciencia/noticia/2025/09/29/metanol-quais-sao-os-sintomas-da-intoxicacao-causada-por-substancia-em-bebidas-alcoolicas-adulteradas-em-sp.ghtml)**
- **Motivo:** contextualiza por que os quadros eram confundidos com ressaca e por que o atraso de atendimento importa. É serviço diretamente ligado à compreensão do risco da história.
- **Evidência no corpo:** “os primeiros sintomas podem ser confundidos com os de uma embriaguez ou ressaca comum”. Não usar o artigo como orientação para tratamento doméstico.

### A10 — Relevância 10
- **2025-10-09 — [Fomepizol: Ministério da Saúde distribui antídoto contra metanol aos estados](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/09/mais-de-2-mil-doses-de-fomepizol-chegam-ao-centro-de-distribuicao-do-ministerio-da-saude-em-guarulhos.ghtml)**
- **Motivo:** documenta a chegada e distribuição do tratamento, superando anúncios de compra. Mostra resposta concreta à escassez e à expansão das notificações.
- **Evidência no corpo:** “O fomepizol será usado apenas sob acompanhamento médico”. A distribuição relatada não significa disponibilidade irrestrita em farmácias.

### A11 — Relevância 11
- **2025-10-10 — [Polícia localiza em SP fábrica clandestina de bebida ligada a mortes por metanol](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/10/policia-civil-localiza-fabrica-clandestina-de-bebidas-ligadas-a-morte-de-duas-pessoas-por-intoxicacao-com-metanol-em-sp.ghtml)**
- **Motivo:** marco de identificação de uma origem produtiva vinculada às mortes. Mais central que fiscalizações preventivas sem conexão demonstrada com vítimas.
- **Evidência no corpo:** “as garrafas de bebida alcoólica que causaram a morte de duas pessoas”. A matéria atribui a ligação à investigação policial.

### A12 — Relevância 12
- **2025-10-16 — [PF e ANP fazem operação contra fábricas clandestinas de bebidas com metanol](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/16/pf-anp-e-ministerio-da-agricultura-fazem-operacao-contra-fabricas-clandestinas-de-bebidas-com-metanol-em-cinco-estados.ghtml)**
- **Motivo:** amplia a apuração para a cadeia de importação e distribuição e explica o objetivo do rastreamento. Não se limita a quantificar garrafas recolhidas.
- **Evidência no corpo:** “identificar a origem do metanol e confirmar se há relação entre os materiais apreendidos”. A relação ainda estava sendo investigada, não demonstrada para todo alvo.

### A13 — Relevância 13
- **2025-12-31 — [Confirmada presença de metanol em bebidas e sangue de pacientes na BA](https://g1.globo.com/ba/bahia/noticia/2025/12/31/laudo-metanol-em-bebidas-apreendidas-na-ba.ghtml)**
- **Motivo:** novo foco confirmado após o encerramento da sala nacional. Mostra por que redução de casos não significou fim do risco, com comprovação laboratorial e não só suspeitas.
- **Evidência no corpo:** “também nas amostras de sangue de sete pacientes”. Não há base neste artigo para unificar o fornecedor baiano à cadeia paulista.

### A14 — Relevância 14
- **2025-10-05 — [Intoxicação por metanol: Brasil tem 16 casos confirmados e 209 suspeitos, diz novo boletim do Ministério da Saúde; veja dados por cidade](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/05/intoxicacao-por-metanol-brasil-tem-16-casos-confirmados-e-209-suspeitos-diz-novo-boletim-do-ministerio-da-saude-veja-dados-por-cidade.ghtml)**
- **Motivo:** dimensiona a expansão inicial e, sobretudo, diferencia confirmação e investigação. É um marco de escala, não a escolha de cada boletim diário.
- **Evidência no corpo:** “São 16 casos confirmados e 209 em investigação”. Não somar suspeitas a confirmações como se todas fossem casos comprovados.

### A15 — Relevância 15
- **2025-10-24 — [Intoxicação por metanol: Brasil tem 58 casos confirmados, diz ministério](https://g1.globo.com/saude/noticia/2025/10/24/intoxicacao-por-metanol-brasil-tem-58-casos-confirmados-diz-ministerio.ghtml)**
- **Motivo:** oferece estágio posterior do surto, distribuição nacional e descarte de notificações. Complementa A14 com evolução da confirmação, não apenas aumento de suspeitas.
- **Evidência no corpo:** “Outras 635 ocorrências foram descartadas”. Números pertencem a um boletim, não a uma contagem definitiva para toda a janela.

### A16 — Relevância 16
- **2025-10-17 — [Encontrados postos suspeitos de vender etanol com metanol para batizar bebidas](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/17/policia-encontra-posto-de-combustivel-suspeito-de-fornecer-etanol-com-metanol-usado-para-batizar-bebidas.ghtml)**
- **Motivo:** documenta a etapa de abastecimento que permite entender a ponte entre adulteração de combustível e de bebidas. Fica abaixo de A01, que integra a cadeia inteira.
- **Evidência no corpo:** “dois postos de combustível suspeitos de vender etanol”. Citação de uma bandeira em outra operação não comprova autoria de facção em todas as intoxicações.

### A17 — Relevância 17
- **2025-10-04 — [Ministério da Saúde anuncia compra de 2,5 mil tratamentos contra metanol](https://g1.globo.com/sp/sao-paulo/noticia/2025/10/04/ministro-saude-padilha-antidoto-metanol.ghtml)**
- **Motivo:** explica a estratégia de obter antídotos e a cooperação internacional. Tem menor prioridade que A10 porque compra anunciada ainda não é entrega.
- **Evidência no corpo:** “junto à Organização Panamericana de Saúde”. **Metadado:** o início do corpo diz “sábado (5)”, enquanto a publicação armazenada e a URL são de 04/10; não corrigir silenciosamente.

### A18 — Relevância 18
- **2026-01-05 — [Homem é preso suspeito de vender bebidas com metanol na Bahia](https://g1.globo.com/ba/bahia/noticia/2026/01/05/homem-e-preso-suspeito-de-vender-bebidas-alcoolicas-adulteradas-com-metanol-na-bahia.ghtml)**
- **Motivo:** acompanha a resposta investigativa ao novo período de contaminações na Bahia e preserva uma incerteza essencial, em vez de presumir elo causal.
- **Evidência no corpo:** “Não há informações sobre se o homem preso nesta segunda vendeu as bebidas consumidas por essas pessoas”. Central para a crise, mas a ligação com o foco de Ribeira do Pombal não estava estabelecida.

### A19 — Relevância 19
- **2026-02-04 — [Jovem de 26 anos é 12ª morte por intoxicação com metanol em SP](https://g1.globo.com/sp/sao-paulo/noticia/2026/02/04/jovem-de-26-anos-e-12a-morte-por-intoxicacao-com-metanol-em-sp-vitima-consumiu-vodca-em-janeiro.ghtml)**
- **Motivo:** demonstra episódio de consumo em janeiro, não apenas atualização tardia de internações do auge do surto. Sustenta continuidade do risco em 2026.
- **Evidência no corpo:** “A investigação epidemiológica do município apontou o consumo de vodca”. Escopo paulista; não converter a 12ª morte estadual em total nacional.

### A20 — Relevância 20
- **2026-02-27 — [Estado de SP chega a 53 casos por intoxicação com metanol](https://g1.globo.com/sp/sao-paulo/noticia/2026/02/27/estado-de-sp-chega-a-53-casos-por-intoxicacao-com-metanol-jovem-de-22-anos-e-nova-vitima.ghtml)**
- **Motivo:** confirma persistência de novos episódios em fevereiro e oferece balanço paulista posterior. É complementar e menos explicativo que os artigos iniciais.
- **Evidência no corpo:** “O novo caso é de uma mulher de 22 anos, de São Bernardo do Campo, do dia 2 de fevereiro”. Não representa encerramento de todos os casos da janela.

**Exclusões e substituições importantes:** pesquisa sobre produção química de metanol, intoxicações estrangeiras antigas e notícias de combustíveis sem conexão com bebidas foram excluídas do escopo. Perfis de vítimas só entrariam se trouxessem novidade central, não apenas luto. Entre muitos boletins, foram escolhidos poucos marcos de confirmação, descarte e persistência. A evolução A04 → A08 → A01 deve ser preservada: a hipótese inicial de lavagem de garrafas não é a conclusão posterior.

## 8. Caso B — Morte de Benício Xavier após atendimento em Manaus

**Consulta sugerida:** “O que aconteceu com Benício Xavier no Hospital Santa Júlia, qual foi o erro com adrenalina e o que a investigação concluiu?”

**Delimitação:** atendimento, prescrição e aplicação de adrenalina, evidências, versões dos envolvidos, responsabilidade hospitalar e evolução policial/judicial até o corte. Exclui outros Benícios, homenagens isoladas e repercussão sem novidade sobre o caso.

**Por que é uma história continuada:** denúncia em novembro, depoimentos e cautelares em dezembro, perícia em janeiro, novas diligências em março e conclusão policial em maio. Há cinco meses distintos nas seleções.

**Lógica do topo:** B01 é a síntese posterior que resolve questões levantadas nas matérias iniciais; B02 reconstrói a sequência; B03 testa a alegação de falha do sistema; B04 esclarece a suspeita de prova forjada; B05 explica a diferença médica central. **A apuração posterior afasta erro da equipe de UTI como causa, hipótese presente em matérias antigas.**

### B01 — Relevância 1
- **2026-05-03 — [Caso Benício: polícia aponta erro médico e overdose de adrenalina](https://g1.globo.com/fantastico/noticia/2026/05/03/caso-benicio-policia-conclui-que-menino-de-6-anos-foi-vitima-de-erro-medico-overdose-de-adrenalina.ghtml)**
- **Motivo:** melhor síntese disponível da conclusão policial: mecanismo da morte, prescrição, aplicação, perícias e responsabilização. Atualiza e qualifica as hipóteses dos primeiros meses.
- **Evidência no corpo:** “não houve erros de intubação ou de qualquer conduta da equipe de UTI”. **Limite:** conclusão de inquérito/peritos relatada pela reportagem, não condenação judicial definitiva.

### B02 — Relevância 2
- **2025-12-01 — [Caso Benício: veja a cronologia da morte após aplicação de medicamento](https://g1.globo.com/am/amazonas/noticia/2025/12/01/caso-benicio-veja-a-cronologia-do-atendimento-que-levou-a-morte-de-crianca-apos-aplicacao-de-adrenalina.ghtml)**
- **Motivo:** organiza entrada no hospital, prescrição, piora, morte e denúncia. É mais útil ao leitor iniciante que vários depoimentos fragmentados.
- **Evidência no corpo:** “entre sábado (22) e a madrugada de domingo (23)”. **Temporalidade:** esta sequência diverge das datas 23–24 citadas em alguns textos iniciais; a divergência não foi apagada.

### B03 — Relevância 3
- **2026-01-23 — [Caso Benício: Perícia em sistema hospitalar contradiz versão da médica](https://g1.globo.com/am/amazonas/noticia/2026/01/23/caso-benicio-delegado-diz-que-pericia-nao-encontrou-falhas-em-sistema-do-hospital-e-contraria-versao-da-medica.ghtml)**
- **Motivo:** testa uma explicação central da defesa com perícia do sistema de prescrição. Tem mais peso explicativo que especulações sobre falha de software.
- **Evidência no corpo:** “a via de administração é selecionada pelo médico, não há troca automática de via de administração”. A declaração é do delegado sobre o laudo.

### B04 — Relevância 4
- **2026-05-05 — [‘Ofereci dinheiro para ela filmar’: mensagem indica tentativa de médica de forjar prova na morte de Benício, diz polícia](https://g1.globo.com/fantastico/noticia/2026/05/05/ofereci-dinheiro-para-ela-filmar-mensagem-indica-tentativa-de-medica-de-forjar-prova-na-morte-de-benicio-diz-policia.ghtml)**
- **Motivo:** detalha a apuração sobre o vídeo usado para sustentar a versão de erro do sistema e informa o indiciamento. O conteúdo da mensagem importa como evidência atribuída, não por sensacionalismo.
- **Evidência no corpo:** “Juliana Brasil foi indiciada por homicídio doloso com dolo eventual, fraude processual e falsidade ideológica”. A defesa nega; indiciamento não é condenação.

### B05 — Relevância 5
- **2025-12-09 — [Caso Benício: entenda a diferença entre inalação e injeção de adrenalina](https://g1.globo.com/fantastico/noticia/2025/12/09/caso-benicio-entenda-a-diferenca-entre-inalacao-e-injecao-de-adrenalina.ghtml)**
- **Motivo:** explica por que via, dose e contexto clínico são o centro da história. É informação essencial para quem não entende a diferença entre “adrenalina” em usos distintos.
- **Evidência no corpo:** “uma dose muito pequena, proporcional ao peso do paciente”. **Superação:** o trecho sobre investigação de intubação é histórico; B01 relata conclusão posterior que afasta falha da UTI.

### B06 — Relevância 6
- **2025-12-07 — [Caso Benício: erros em atendimento causam morte de menino no AM](https://g1.globo.com/fantastico/noticia/2025/12/07/caso-benicio-pais-denunciam-sucessao-de-erros-em-atendimento-que-terminou-com-morte-do-filho-de-6-anos.ghtml)**
- **Motivo:** reconstrói o atendimento com relato dos pais, imagens descritas em texto e explicação médica. Complementa a cronologia com experiência e documentos do episódio.
- **Evidência no corpo:** “O menino morreu após receber uma dose incorreta de adrenalina na veia”. A expressão “sucessão de erros” inclui alegações iniciais; não substitui as conclusões posteriores de B01.

### B07 — Relevância 7
- **2025-12-01 — [Polícia confirma conversa em que médica admite erro com Benício](https://g1.globo.com/am/amazonas/noticia/2025/12/01/policia-confirma-autenticidade-de-conversa-em-que-medica-admite-erro-ao-prescrever-adrenalina-em-benicio-xavier.ghtml)**
- **Motivo:** verifica a autenticidade de mensagens que circulavam nas redes, transformando material viral em evidência contextualizada pela apuração.
- **Evidência no corpo:** “a veracidade das mensagens foi confirmada pelo médico Enryko Queiroz”. **Qualidade:** o corpo também reproduz a sequência de datas 23–24, divergente de B02.

### B08 — Relevância 8
- **2025-11-29 — [Caso Benício: técnica de enfermagem diz que seguiu prescrição](https://g1.globo.com/am/amazonas/noticia/2025/11/29/caso-benicio-tecnica-de-enfermagem-diz-que-apenas-seguiu-prescricao-medica-durante-atendimento.ghtml)**
- **Motivo:** registra a versão de quem aplicou a medicação e o questionamento da mãe, elementos centrais da cadeia de decisões. Não é apenas uma manifestação de advogado sem conteúdo factual.
- **Evidência no corpo:** “a medicação de forma intravenosa e sem diluição, como constava na prescrição”. É a versão da técnica; o texto contém a mesma divergência inicial de datas.

### B09 — Relevância 9
- **2025-12-16 — [Caso Benício: justiça suspende atuação de médica e técnica](https://g1.globo.com/am/amazonas/noticia/2025/12/16/caso-benicio-justica-nega-prisao-de-medica-investigada-mas-suspende-exercicio-profissional.ghtml)**
- **Motivo:** distingue pedido policial de prisão de decisão judicial por cautelares e afastamento. Evita descrever as investigadas como presas quando não estavam.
- **Evidência no corpo:** “A Justiça do Amazonas negou o pedido de prisão preventiva”. **Precisão:** o início do corpo detalha sobretudo o afastamento da médica; B17 explicita cautelares de ambas.

### B10 — Relevância 10
- **2025-12-17 — [Caso Benício: hospital diz que havia suporte e nega falta de protocolo](https://g1.globo.com/am/amazonas/noticia/2025/12/17/caso-benicio-donos-do-hospital-prestam-depoimento-sobre-a-morte-da-crianca-apos-dose-de-adrenalina.ghtml)**
- **Motivo:** oferece o contraponto da instituição sobre dupla checagem, equipe e responsabilidade. É indispensável para não reduzir a narrativa apenas às versões acusatórias.
- **Evidência no corpo:** “tinha uma enfermeira que faz o protocolo de segurança. Ela não foi acionada”. Atribuição ao fundador; não valida automaticamente a suficiência do protocolo.

### B11 — Relevância 11
- **2025-12-07 — [Caso Benício: Médica tentou adulterar prontuário, diz delegado](https://g1.globo.com/am/amazonas/noticia/2025/12/07/caso-benicio-testemunhas-afirmam-que-medica-tentou-adulterar-prontuario-para-omitir-erro-apos-morte-diz-delegado.ghtml)**
- **Motivo:** introduz a suspeita de interferência em prova diretamente ligada à prescrição. Complementa B04, que trata de outro suporte: o vídeo do sistema.
- **Evidência no corpo:** “Ao menos três testemunhas afirmaram”. Trata-se de relatos informados pelo delegado, não adulteração demonstrada por sentença.

### B12 — Relevância 12
- **2025-12-11 — [Caso Benício: prescrição foi escondida por medo de alteração da médica](https://g1.globo.com/am/amazonas/noticia/2025/12/11/caso-benicio-prescricao-foi-escondida-em-jalecos-por-medo-de-alteracao-da-medica-apos-erro-na-adrenalina-dizem-depoimentos.ghtml)**
- **Motivo:** explica preservação do documento original e a origem de depoimentos sobre eventual alteração. É evidência complementar, não um novo resumo completo.
- **Evidência no corpo:** “mantiveram a prescrição original, assinada por Juliana, para impedir que fosse substituída”. A matéria atribui o fato aos depoimentos das profissionais.

### B13 — Relevância 13
- **2025-12-15 — [Caso Benício: Médica foi cadastrada como pediatra sem especialização](https://g1.globo.com/am/amazonas/noticia/2025/12/15/caso-benicio-hospital-cadastrou-medica-no-ministerio-da-saude-como-pediatra-mesmo-sem-especializacao-diz-delegado.ghtml)**
- **Motivo:** amplia a questão da apresentação profissional para responsabilidade do hospital pelo cadastro. Mais abrangente que a notícia isolada sobre o carimbo.
- **Evidência no corpo:** “não é ela que faz essa declaração, é o próprio hospital”. É declaração do delegado sobre a consulta ao cadastro; não causa médica da morte por si só.

### B14 — Relevância 14
- **2025-12-11 — [Caso Benício: Overdose e Falta de Equipamentos na UTI, Aponta Médica](https://g1.globo.com/am/amazonas/noticia/2025/12/11/caso-benicio-medicas-apontam-overdose-por-dose-15-vezes-maior-de-adrenalina-e-falta-de-equipamentos-na-uti.ghtml)**
- **Motivo:** traz depoimento médico sobre a dimensão da dose e questões de estrutura. É relevante para a evolução da apuração, mas deve ser lido com a conclusão posterior.
- **Evidência no corpo:** “recebeu 3 ml diretamente na veia”. **Superação:** alegações de falta de equipamento não provam contribuição causal da UTI; B01 afasta erro de intubação como causa.

### B15 — Relevância 15
- **2025-12-04 — [Caso Benício: Polícia investiga erro em intubação na UTI](https://g1.globo.com/am/amazonas/noticia/2025/12/04/caso-benicio-policia-investiga-se-erro-durante-intubacao-contribuiu-para-a-morte.ghtml)**
- **Motivo:** documenta uma linha de investigação relevante no percurso do caso, permitindo avaliar se uma síntese distingue hipótese de conclusão. Prioridade inferior porque a hipótese foi afastada depois.
- **Evidência no corpo:** “investiga a possibilidade de erros durante o procedimento de intubação”. **Uso correto:** referência histórica; não usar como afirmação atual de erro da UTI.

### B16 — Relevância 16
- **2025-12-15 — [Caso Benício: Polícia pede prisão de médica e técnica de enfermagem](https://g1.globo.com/am/amazonas/noticia/2025/12/15/caso-benicio-policia-pede-prisao-de-medica-e-tecnica-investigadas-pela-morte-do-menino.ghtml)**
- **Motivo:** mostra a escalada da pretensão policial e o contexto de revogação do habeas corpus. Complementa, sem substituir, a decisão de B09.
- **Evidência no corpo:** “A Justiça não decidiu se aceita ou nega o pedido”. Não converter pedido de prisão em prisão realizada.

### B17 — Relevância 17
- **2025-12-23 — [Caso Benício: Justiça nega novo pedido de prisão de médica e técnica](https://g1.globo.com/am/amazonas/noticia/2025/12/23/caso-benicio-justica-nega-novo-pedido-de-prisao-de-medica-e-tecnica-investigadas-pela-morte-do-menino.ghtml)**
- **Motivo:** registra manutenção das cautelares após nova tentativa de prisão e explicita a situação das duas investigadas. Menor prioridade pela sobreposição com B09.
- **Evidência no corpo:** “as medidas cautelares já impostas são suficientes para garantir a ordem pública”. Negativa de prisão preventiva não é absolvição.

### B18 — Relevância 18
- **2026-03-24 — [Caso Benício: polícia pede mais 45 dias para apurar morte em Manaus](https://g1.globo.com/am/amazonas/noticia/2026/03/24/caso-benicio-policia-pede-mais-45-dias-para-concluir-investigacao-sobre-morte-de-crianca-em-hospital-de-manaus.ghtml)**
- **Motivo:** explica por que a investigação ainda não estava concluída e quais etapas faltavam, além de contextualizar o vídeo suspeito. Faz a ponte entre a perícia de janeiro e a conclusão de maio.
- **Evidência no corpo:** “depoimento de testemunhas, laudos de exame necroscópico e a elaboração do relatório final”. Pedido de prazo não é conclusão do inquérito.

### B19 — Relevância 19
- **2025-11-27 — [Caso Benício: o que se sabe sobre a morte da criança em Manaus](https://g1.globo.com/am/amazonas/noticia/2025/11/27/caso-benicio-o-que-se-sabe-sobre-a-morte-da-crianca-e-a-denuncia-de-erro-na-aplicacao-de-adrenalina.ghtml)**
- **Motivo:** explicador inicial útil para o que era conhecido e ainda indeterminado. Cai no ranking porque B01/B02 são mais completos e o corpo contém divergência de datas.
- **Evidência no corpo:** “a causa da morte consta como indeterminada no relatório de necrópsia”. **Limites:** estado inicial do conhecimento, não conclusão atual; o texto usa 23–24, enquanto B02 usa 22–23.

### B20 — Relevância 20
- **2025-12-14 — [Caso Benício: médica usou carimbo de pediatria sem especialidade](https://g1.globo.com/am/amazonas/noticia/2025/12/14/caso-benicio-medica-usava-carimbo-de-pediatria-sem-ter-especialidade-e-pode-responder-por-falsidade-ideologica-diz-delegado.ghtml)**
- **Motivo:** documenta a origem da frente sobre qualificação e identificação profissional, mas acrescenta menos ao leitor geral que o vínculo hospitalar de B13.
- **Evidência no corpo:** “utilizava carimbo e assinaturas com referência à especialidade de pediatria”. Atribuição ao delegado; não confundir possível crime documental com demonstração autônoma da causa da morte.

**Exclusões e substituições importantes:** homenagens escolares, aniversário que a criança faria e carta do papa não forneciam o núcleo factual buscado. Homônimos como Murilo Benício, Benício Huck e Mônica Benício foram descartados pelo escopo. A chamada do Fantástico de 01/05, apesar de anunciar responsabilizações, tinha corpo curto e promocional; foi substituída pela reportagem substantiva B01. B15/B19 foram mantidos com baixa prioridade e avisos por documentarem o percurso da investigação; para uma tarefa estritamente de informação atual, e não reconstrução da história, seus julgamentos devem ser revistos.

## 9. Rastreabilidade e verificação

### 9.1. Metadados e limitações temporais

- Todos os títulos, datas e URLs dos 100 artigos foram obtidos da tabela. Foi removido apenas o sufixo repetitivo ` | G1` na apresentação dos títulos.
- As URLs são as chaves `url`, mesmo quando o slug conserva números, chamadas ou afirmações anteriores a uma atualização.
- Os 100 registros selecionados foram capturados entre **2026-04-21 21:04:38.860722+00** e **2026-05-06 13:54:19.815742+00**, pelo campo `fetched_at`. Portanto os snapshots selecionados foram obtidos antes do limite de 20/05/2026. Nenhum `sitemap_article_lastmod` desses registros indicava atualização posterior ao corte.
- Não foi reconstruída a versão original de cada publicação. Um artigo de novembro capturado em abril pode conter revisões posteriores à publicação, ainda que anteriores ao corte geral. Não usar este conjunto para simular automaticamente uma busca “como era conhecida no dia da publicação”.
- “Corpo não vazio” não significa extração perfeita. Foram observados inícios truncados, legendas e pequenas inconsistências internas; quando interferem na interpretação dos selecionados, há aviso no item.
- A importância atribuída às posições e fronteiras do tema deve ser revisada por orientador ou segundo anotador. Não há medida de concordância interavaliadores nesta rodada.

### 9.2. Consultas de partida, sem modificar o banco

```sql
BEGIN READ ONLY;

SELECT count(*) AS total,
       min(date_published) AS primeira_publicacao,
       max(date_published) AS ultima_publicacao,
       count(*) FILTER (WHERE nullif(btrim(title), '') IS NOT NULL) AS com_titulo,
       count(*) FILTER (WHERE nullif(btrim(text_content), '') IS NOT NULL) AS com_corpo
FROM g1_articles
WHERE date_published BETWEEN DATE '2025-06-01' AND DATE '2026-05-20';

SELECT date_published, title, url
FROM g1_articles
WHERE date_published BETWEEN DATE '2025-06-01' AND DATE '2026-05-20'
ORDER BY md5(url)
LIMIT 850;

-- :padrao é parâmetro do cliente SQL, não SQL literal executável sem substituição.
SELECT url, final_url, title, date_published, text_content
FROM g1_articles
WHERE date_published BETWEEN DATE '2025-06-01' AND DATE '2026-05-20'
  AND title ~* :padrao
ORDER BY date_published, url;

ROLLBACK;
```

Padrões exploratórios usados com a última consulta; correspondência sem distinguir maiúsculas/minúsculas, sintaxe PostgreSQL:

```text
master:    \m(master|vorcaro)\M
inss:      (INSS.*(fraud|descont|ressarc|devol|operaç|CPMI)|((fraud|descont|ressarc|devol|CPMI).*(INSS|aposentad)))
tarifaco:  (tarifaço|tarifas?.*(Brasil|brasileir)|Brasil.*tarifas?)
metanol:   metanol
benicio:   Benício
contencao: (contenção|operaç.*(Penha|Alemão)|megaoperaç.*Rio)
rinjani:   (Juliana Marins|Rinjani)
orelha:    (cão Orelha|cachorro Orelha|caso Orelha)
cop30:     COP.?30
golpe:     (trama golpista|tentativa de golpe|julgamento.*Bolsonaro|Bolsonaro.*(condena|réu))
```

Esses padrões documentam a descoberta, não um classificador de relevância. As listas completas de candidatos não receberam rótulos negativos. Os julgamentos positivos são as 100 entradas identificadas neste arquivo; as exclusões comentadas são decisões editoriais de escopo/prioridade, com o nível de inspeção indicado, não uma coleção exaustiva de negativos difíceis.

### 9.3. Impressões dos snapshots selecionados

Para detectar mudança posterior no banco, foi calculado um SHA-256 por conjunto, a partir das vinte linhas selecionadas. Estes hashes não substituem um backup do corpus, mas permitem verificar se os mesmos títulos, datas e corpos continuam presentes.

| Caso | SHA-256 |
| --- | --- |
| M | `2ecc9dba6bc7fedb2aed30ea4d9cc7ea29d3a0056f0ae56d618e4567e38a05ce` |
| I | `4251775d3c81ee05766ac9b18fb454fd88e972a69f05dbb7a296d019abf81c43` |
| T | `1d8db98732ba4d59ab3497b355dbda37bb6d2c9cfe4ea8115b31a65394aa2a45` |
| A | `c5b4f96a863f918280733985cb42f9801c3700bd650652e8ad70ba4f02d5046f` |
| B | `924b635872e003286a1cb56c8987a3eef75e5a8b22c54be286e892e930fc303f` |

Algoritmo exato de serialização em Python, após buscar as vinte URLs do tema; `date` é a data ISO e `body` é `text_content` sem normalização:

```python
payload = '\n'.join(
    json.dumps(
        {key: row[key] for key in ['url', 'title', 'date', 'body']},
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )
    for row in sorted(rows, key=lambda row: row['url'])
)
digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
```

**Antes de congelar a avaliação da tese:** revisar os casos com um segundo anotador; decidir se a tarefa é compreensão histórica ou apenas informação atual; julgar os documentos adicionais recuperados pelos métodos comparados; manter o mesmo recorte e a mesma referência ao variar k; registrar a versão do corpus. Esses passos não foram simulados nem apresentados aqui como concluídos.
