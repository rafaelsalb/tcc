"""Materialize three editorial selections from the local corpus (read-only).

Selections below are editorial judgments after directed reading, not a search
ranking or an automated relevance classifier. No external web requests are used.
"""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

from relevance_research import database, snapshot_hash, write_json


ROOT = Path(__file__).resolve().parents[1]
STYLES = ("keyword", "short_theme", "specific_keywords", "broad_theme", "short_question",
          "specific_question", "information_request", "baseline")
THEMES = {
    "juliana_marins": {
        "name": "Juliana Marins: queda no Rinjani, resgate e perícias",
        "pattern": "(Juliana Marins|Rinjani)",
        "scope": "Acidente, tentativas de resgate, perícias e apuração de responsabilidades; exclui homenagens, vaquinhas e turismo sem evidência central.",
        "caution": "As estimativas de 10–20 minutos dizem respeito ao trauma fatal, não necessariamente à primeira queda. A estimativa posterior de 32 horas é atribuída ao perito. Alegações de negligência não equivalem a decisão judicial. O corpo da matéria sobre limitações do IML contém uma referência cronológica inconsistente a sábado (6); ela não foi adotada como data do encontro do corpo.",
        "queries": (
            "Juliana Marins Rinjani",
            "resgate e perícia de Juliana Marins",
            "Juliana Marins Rinjani queda resgate autópsia investigação",
            "morte de turista brasileira em vulcão na Indonésia",
            "O que aconteceu com Juliana Marins?",
            "O que as perícias esclareceram sobre as quedas de Juliana Marins e as dificuldades do resgate no Rinjani?",
            "Explique o acidente de Juliana Marins no Rinjani, as tentativas de resgate e os limites das conclusões periciais.",
            "O que aconteceu com Juliana Marins no Monte Rinjani, por que o resgate demorou e o que as perícias e investigações esclareceram sobre sua morte?",
        ),
        "articles": [
            ("caso-juliana-marins-perguntas-e-respostas-apos-nova-autopsia.ghtml",
             "Síntese das conclusões e perguntas remanescentes após a perícia brasileira; melhor porta de entrada.",
             "A causa imediata da morte foi hemorragia interna provocada por lesões poliviscerais e politraumatismo, compatíveis com impacto de alta energia."),
            ("juliana-marins-coletiva-detalhes-morte-e-autopsia.ghtml",
             "Atualiza a reconstrução: separa a primeira queda do impacto fatal e atribui ao perito a estimativa de sobrevida.",
             "Na coletiva, um perito afirmou que é possível estimar que ela permaneceu viva 32 horas após a primeira queda."),
            ("caso-juliana-marins-especialistas-listam-possiveis-erros-antes-e-depois-do-acidente-em-vulcao-na-indonesia.ghtml",
             "Organiza hipóteses de falhas de segurança e registra o contraponto da agência de resgate.",
             "Especialistas em montanhismo, guias experientes e turistas que já estiveram no local apontam falhas graves que podem ter contribuído para a tragédia."),
            ("por-que-levou-dias-para-brasileira-juliana-marins-ser-resgatada-de-vulcao-na-indonesia.ghtml",
             "Explica mecanismos do atraso com entrevistas sobre equipamento, clima e disponibilidade de socorristas.",
             "Primeiro, eles dizem que o equipamento de resgate de emergência era muito limitado."),
            ("brasileira-juliana-marins-e-encontrada-morta-600-metros-abaixo-da-trilha-do-vulcao-rinjani-na-indonesia.ghtml",
             "Marco da confirmação da morte e reconstrução das buscas; distingue notícia confirmada de informação depois desmentida.",
             "A família chegou a ser informada que as equipes de resgate tinham chegado até a jovem e dado comida e água. Mas a informação foi desmentida depois."),
            ("o-que-autopsia-revela-sobre-morte-de-juliana-marins-em-vulcao-na-indonesia.ghtml",
             "Documenta a conclusão da autópsia indonésia, como etapa histórica da investigação.",
             "Um trauma contundente, resultando em danos a órgãos internos e hemorragia, foi a causa da morte de Juliana Marins"),
            ("juliana-marins-policia-investigacao.ghtml",
             "Mostra abertura da apuração local e pessoas chamadas a depor, sem converter suspeitas em autoria provada.",
             "Além do guia, responsáveis pela agência de turismo, o carregador que levava as bagagens pela trilha e um policial florestal foram intimados a prestar depoimento."),
            ("monte-rinjani-quem-e-responsavel-pela-seguranca-dos-montanhistas.ghtml",
             "Explica responsabilidades institucionais e operacionais pela segurança, além do relato do acidente.",
             "A BBC News Indonesia (serviço de notícias da BBC em idioma indonésio) conversou com especialistas no país para entender de quem seriam as responsabilidades."),
            ("morte-de-juliana-marins-entenda-se-era-possivel-mandar-cobertor-e-comida-durante-resgate-em-vulcao.ghtml",
             "Contraponto técnico à certeza de negligência; o texto do podcast tem informação suficiente sem ouvir o áudio.",
             "Os especialistas ouvidos por Natuza Nery afirmam que, apesar das falhas apontadas, ainda não é possível afirmar com certeza que houve negligência no resgate de Juliana Marins."),
            ("imagens-ineditas-revelam-primeiras-tentativas-de-resgate-de-juliana-marins-ela-caiu-em-um-penhasco-diz-guia-em-gravacao.ghtml",
             "Relato textual das primeiras tentativas e horários atribuídos à família; os vídeos não foram usados como evidência autônoma.",
             "Um registro feito pelo próprio guia mostra a lanterna do capacete de Juliana ainda acesa após a queda."),
            ("guia-indonesio-juliana-marins.ghtml",
             "Versão posterior do guia sobre divisão do grupo e último contato, necessária como contraponto atribuído.",
             "O jovem disse que a niteroiense pedia ‘socorro’."),
            ("policia-do-rj-confirma-que-traumas-de-queda-mataram-juliana-marins-mas-nao-descarta-agonia-antes-da-morte.ghtml",
             "Marco da confirmação pericial brasileira e dos limites para estabelecer o horário do óbito.",
             "A estimativa exata da data da morte foi considerada prejudicada devido às condições em que o corpo chegou ao IML, já embalsamado."),
            ("caso-juliana-marins-estado-do-corpo-comprometeu-parte-das-analises-periciais-aponta-laudo-do-iml.ghtml",
             "Detalha limitações materiais da perícia; a inconsistência de data no corpo exige cautela, não correção silenciosa da fonte.",
             "Segundo o laudo, o embalsamamento realizado antes da necropsia impediu que os especialistas estimassem com precisão o horário da morte"),
            ("legistas-nao-esclareceram-em-que-dia-juliana-marins-morreu.ghtml",
             "Distingue causa da morte de data da morte na primeira divulgação pericial.",
             "Mas os legistas não esclareceram em que dia a Juliana Marins morreu."),
            ("defensora-fala-sobre-nova-autopsia-no-corpo-de-juliana-marins.ghtml",
             "Registra o pedido da DPU e possíveis vias de apuração, ainda condicionais.",
             "A DPU pediu nesta segunda-feira (30) que a Polícia Federal (PF) apure se houve crime de omissão no abandono de Juliana por parte das autoridades indonésias."),
            ("autopsia-no-corpo-de-juliana-marins-no-iml-do-rio.ghtml",
             "Execução da segunda autópsia e participação de peritos e representantes da família.",
             "A necropsia é realizada por peritos da Polícia Civil, com a presença de um perito federal e de um representante da família."),
            ("corpo-de-juliana-marins-e-icado-de-vulcao-na-indonesia.ghtml",
             "Documenta conclusão da retirada do corpo e etapas operacionais em horários locais distintos.",
             "O mau tempo impediu que helicópteros fossem usados na operação, e a solução foi instalar diversos pontos de ancoragem na pedra."),
            ("socorristas-na-indonesia-montam-acampamento-avancado-perto-de-onde-juliana-marins-esta.ghtml",
             "Comunicado do parque sobre a aproximação dos socorristas e restrição por neblina, antes da confirmação do óbito.",
             "as tentativas de auxílio aéreo por helicóptero ainda não tiveram sucesso devido à forte neblina na área"),
            ("parque-fecha-trilha-para-resgate-de-juliana-marins-brasileira-que-caiu-em-vulcao-na-indonesia.ghtml",
             "Medida concreta para restringir a trilha e permitir a operação de resgate.",
             "A medida foi tomada para acelerar o trabalho de resgate da niteroiense Juliana Marins"),
            ("familia-de-juliana-marins-decide-enterrar-corpo.ghtml",
             "Consequência ligada à preservação de possibilidade de nova perícia, não selecionada pela homenagem funerária.",
             "Então ela teria que ser enterrada caso precisasse fazer uma exumação futura"),
        ],
    },
    "cao_orelha": {
        "name": "Cão Orelha: morte, limites da perícia e revisão da investigação",
        "pattern": "(cão Orelha|cachorro Orelha|caso Orelha)",
        "scope": "Investigação do cachorro comunitário da Praia Brava, evidência veterinária/pericial, defesa, revisão pelo MP e consequências institucionais; exclui homônimos, homenagens e manifestações sem novidade central.",
        "caution": "As notícias iniciais falam em eutanásia e vários suspeitos; versões posteriores corrigem esses pontos. A exumação não determinou a causa da morte nem excluiu trauma por ausência de fraturas. Suspeita, representação e pedido de internação não são condenação. A suspensão de apuração penal do delegado não suspende automaticamente apurações cíveis; o decreto aparece como anunciado, não como publicação já confirmada naquele texto.",
        "queries": (
            "cão Orelha",
            "investigação da morte do cão Orelha",
            "cão Orelha Praia Brava exumação perícia Ministério Público investigação",
            "maus-tratos a cachorro comunitário em Florianópolis",
            "O que aconteceu com o cão Orelha?",
            "O que a perícia e o Ministério Público esclareceram sobre a morte do cão Orelha e as lacunas da investigação?",
            "Explique a morte do cão Orelha na Praia Brava, as versões da polícia e da defesa e a revisão das provas pelo Ministério Público.",
            "O que se sabe sobre a morte do cão Orelha em Florianópolis, quais foram as conclusões e limitações dos laudos e como evoluiu a investigação de adolescentes e adultos?",
        ),
        "articles": [
            ("cao-orelha-laudo-exumacao-lesoes-cabeca.ghtml",
             "Prioriza o limite probatório mais importante: exumação sem causa determinada, sem confundir ausência de fratura com exclusão de trauma.",
             "A análise dos restos mortais não permitiu afirmar qual foi a causa da morte."),
            ("pancada-piora-progressiva-adolescente-indiciado-o-que-se-sabe-cao-orelha.ghtml",
             "Síntese dos fatos, evidências e versões antes da exumação; deve ser lida junto da atualização pericial superior.",
             "Inicialmente, a polícia afirmou que Orelha passou por eutanásia após as agressões. Depois, essa hipótese foi descartada."),
            ("cao-orelha-linha-do-tempo-e-o-que-se-sabe-ate-agora.ghtml",
             "Reconstrói a sequência de eventos e separa o caso Orelha do cão Caramelo.",
             "A Polícia reiterou que não tem imagens que mostrem as agressões sofridas pelo cão."),
            ("cao-orelha-laudo-exumacao-animal-doenca-degenerativa-cronica-infeccao-ossea.ghtml",
             "Aprofunda condições prévias e alcance restrito da análise óssea, evitando inferência causal indevida.",
             "Mesmo assim, os peritos destacam que a ausência de fraturas não descarta a possibilidade de trauma na cabeça."),
            ("justica-sc-acata-35-pedidos-investigacoes-morte-cao-orelha-veja-quais.ghtml",
             "Marco judicial da ampliação das diligências e adiamento da análise de internação.",
             "O juiz André Milani postergou a análise do pedido da Polícia Civil de internação do adolescente apontado como suspeito da morte de Orelha."),
            ("caso-orelha-mpsc-vai-pedir-mais-respostas-a-policia-inqueritos.ghtml",
             "Explica por que o Ministério Público considerou a apuração insuficiente e pediu complementação.",
             "A 10ª Promotoria identificou lacunas na apuração sobre a possível participação de adolescentes"),
            ("orelha-defesa-contesta-autoria-video-cao-andando-agressoes.ghtml",
             "Contraponto da defesa e resposta policial à cronologia apresentada em vídeo.",
             "Os advogados negam que o adolescente tenha participado das agressões e afirmam que o vídeo contradiz a linha do tempo apresentada pela polícia."),
            ("policia-de-sc-conclui-que-apenas-um-adolescente-teve-envolvimento-na-morte-do-cao-orelha.ghtml",
             "Documenta a conclusão policial de fevereiro como versão atribuída, posteriormente submetida a novas diligências.",
             "No caso do cão Orelha, a polícia afirmou que só um dos adolescentes suspeitos teve envolvimento nas agressões."),
            ("veterinario-que-atendeu-cao-orelha-descarta-acidente-foi-uma-agressao.ghtml",
             "Fonte do atendimento inicial; permite comparar achados clínicos com a exumação posterior.",
             "Derli Royer, responsável pelo socorro emergencial, contou que o animal tinha lesões graves na cabeça e no olho esquerdo, além de forte desidratação."),
            ("parentes-de-adolescentes-suspeitos-de-matar-cachorro-orelha-sao-indiciados-por-coacao-de-testemunha-em-florianopolis.ghtml",
             "Marco da investigação de adultos por coação; a informação inicial de eutanásia no mesmo texto foi posteriormente revista.",
             "A polícia indiciou nesta terça-feira (27) dois empresários e um advogado."),
            ("mpsc-pede-exumacao-corpo-cao-orelha.ghtml",
             "Fundamentação do pedido de exumação e distinção entre laudo indireto e exame do corpo.",
             "Um laudo indireto, baseado em atendimento veterinário, apontou que a causa da morte foi um golpe na cabeça por objeto contundente."),
            ("corpo-de-cao-orelha-e-exumado-para-producao-de-novo-laudo-sobre-morte-em-florianopolis.ghtml",
             "Confirma execução da diligência, em vez de apenas o pedido de exumação.",
             "A exumação ocorreu na quarta-feira (11)."),
            ("orelha-mp-prazo-policia-refazer-depoimentos-esclarecer-coacao-ameaca.ghtml",
             "Delimita o procedimento de coação e ameaça de adultos, diferente da autoria dos maus-tratos.",
             "A apuração atual trata apenas do conflito entre os adultos"),
            ("cao-orelha-operacao-mandados-investigados-maus-tratos-coacao-florianopolis.ghtml",
             "Operação inicial e apreensão de dispositivos para reconstrução da prova, antes do estreitamento das suspeitas.",
             "Aparelhos celulares e outros dispositivos eletrônicos foram apreendidos e passarão por análise."),
            ("cuidadora-de-cao-orelha-nega-boatos-sobre-caso-e-alerta-inventaram-um-monte-de-coisa.ghtml",
             "Desmente detalhes virais que não devem ser incorporados à reconstrução factual sem prova.",
             "Inventaram um monte de coisa, de eutanásia, de beisebol, de prego, não tem nada disso"),
            ("caso-orelha-menina-em-video-com-adolescente-nao-viu-ataque.ghtml",
             "Esclarece que a acompanhante não testemunhou agressão e registra a correção dos horários do vídeo divulgado.",
             "a corporação esclareceu nesta sexta (6) que, na verdade, os registros mostram a saída do adolescente em outro horário, às 6h35, e o retorno às 6h37."),
            ("cao-orelha-mp-entra-acao-improbidade-contra-ex-delegado-geral-da-policia-civil-de-sc.ghtml",
             "Desdobramento institucional mais recente: ação cível sobre a condução da apuração, ainda sem julgamento informado.",
             "O processo é de improbidade administrativa com indenização por dano moral coletivo em relação a atuação dele no caso do cão Orelha"),
            ("cao-orelha-justica-suspende-investigacao-criminal-conduta-ex-delegado-geral.ghtml",
             "Contraponto judicial: suspensão por competência, sem confundir com arquivamento de toda apuração.",
             "As investigações cíveis ou administrativas seguem normalmente."),
            ("governo-publica-decreto-cao-orelha-que-endurece-penas-para-maus-tratos-a-animais.ghtml",
             "Consequência regulatória nacional; o corpo registra que o anúncio ainda aguardava publicação no DOU.",
             "Até a última atualização desta reportagem, o decreto ainda não tinha sido publicado no Diário Oficial da União (DOU)."),
            ("cao-orelha-quais-proximos-passos-investigacao.ghtml",
             "Explica procedimentos e garantias dos adolescentes, bem como a revisão das suspeitas iniciais.",
             "um dos quatro adolescentes inicialmente identificados como suspeitos do ato infracional foi ouvido nesta semana e negou que estava na praia no momento do ocorrido."),
        ],
    },
    "cop30_negociacoes": {
        "name": "COP30: negociações, financiamento e resultados de Belém",
        "pattern": "COP.?30",
        "scope": "Preparação diplomática, metas climáticas, financiamento, transição energética, adaptação e implementação após Belém; exclui turismo, publicidade, festas, obras locais e incidentes sem contribuição central para os acordos.",
        "caution": "Propostas, rascunhos e iniciativas da presidência não equivalem a decisões consensuais nem a recursos desembolsados. Diferenciar o Roteiro de Baku a Belém, o mapa do caminho para fósseis e os acordos finais. As críticas e expectativas prévias são preservadas como etapas históricas, sem substituir o resultado final.",
        "queries": (
            "COP30 Belém",
            "resultados das negociações da COP30",
            "COP30 Belém financiamento adaptação combustíveis fósseis mapa do caminho",
            "acordos climáticos e transição energética na COP30",
            "O que foi decidido na COP30?",
            "O que a COP30 decidiu sobre financiamento e adaptação climática e por que o mapa do caminho dos combustíveis fósseis ficou de fora?",
            "Explique os avanços e as pendências da COP30 em Belém sobre financiamento, adaptação e abandono dos combustíveis fósseis.",
            "Quais foram os resultados da COP30 em Belém, como evoluíram as negociações de financiamento e transição energética e quais compromissos e pendências ficaram para depois da conferência?",
        ),
        "articles": [
            ("entenda-em-12-topicos-os-avancos-e-as-pendencias-da-cop30.ghtml",
             "Síntese retrospectiva de resultados e limites, prioridade sobre expectativas anteriores à cúpula.",
             "Um dos principais resultados foi a adoção de um conjunto comum de indicadores para a chamada Meta Global de Adaptação."),
            ("cop30-aprova-acordos-sem-mapa-do-caminho.ghtml",
             "Marco da adoção dos acordos, meta financeira e controvérsia sobre o processo de aprovação.",
             "O texto do Mutirão não cita os combustíveis fósseis, mas cria estruturas que ampliam a agenda de cooperação, organizam debates e inclui a meta de triplicar o financiamento para adaptação até 2035."),
            ("por-que-rota-para-fim-de-combustiveis-fosseis-virou-impasse-na-cop30.ghtml",
             "Explicador causal do principal impasse, conectando compromisso anterior e coalizões de negociação.",
             "Os anfitriões brasileiros chegaram a cogitar mencionar um roteiro para a eliminação gradual dos combustíveis fósseis, mas o tema ficou de fora da agenda oficial e do último rascunho do texto final da cúpula"),
            ("presidencia-da-cop30-lanca-plano-de-us-13-trilhao-anuais-que-pode-ajudar-paises-na-luta-contra-crise-do-clima.ghtml",
             "Distingue financiamento proposto pelo roteiro Baku–Belém de tratado negociado e de desembolso realizado.",
             "O texto não tem força de tratado internacional nem será objeto de negociação entre países"),
            ("mapa-do-caminho-fica-fora-dos-textos-da-cop30-e-vai-ser-uma-iniciativa-da-presidencia-brasileira-diz-andre-correa-do-lago.ghtml",
             "Explica a saída institucional para o roteiro dos fósseis fora do consenso final.",
             "o chamado \"mapa do caminho\" (roadmap) para o fim do uso dos combustíveis fósseis não será incorporado aos textos finais"),
            ("em-carta-presidencia-da-cop30-defende-aceleracao-de-decisoes-climaticas-e-admite-resultado-aquem-do-esperado.ghtml",
             "Balanço posterior da presidência e continuidade do trabalho após a conferência.",
             "a Presidência da COP30 reconheceu que os resultados do evento ficaram \"aquém do esperado\""),
            ("conferencia-preparatoria-da-cop30-deixa-principais-impasses-de-belem-sem-solucao-entenda-em-5-pontos.ghtml",
             "Antecedente diplomático: problemas já identificados em Bonn, antes da reunião de Belém.",
             "a conferência alemã que deveria preparar o terreno para acordos na COP30 esbarrou em impasses sobre financiamento climático, adaptação e transição energética."),
            ("em-10-pontos-entenda-o-que-a-cupula-de-lideres-mostra-sobre-o-rumo-da-cop30-e-seus-desafios.ghtml",
             "Distingue sinalização política da cúpula de líderes de acordos negociados formalmente.",
             "São considerados passos iniciais e sinalizações importantes."),
            ("a-100-dias-da-cop30-metas-climaticas-atrasadas-aumentam-a-pressao-por-resultados-em-belem.ghtml",
             "Explica a pressão das NDCs atrasadas e o elo com o Acordo de Paris.",
             "Até o fim de julho, apenas 25 países haviam enviado suas novas metas oficiais à ONU"),
            ("fantastico-acordo-presidente-da-cop30-celebra-consenso-sobre-agenda-do-1o-dia-conferencia.ghtml",
             "Marco procedimental que permitiu iniciar negociações; não é aprovação do acordo final.",
             "o acordo costurado ainda no fim de semana foi considerado essencial para destravar o início das discussões formais."),
            ("arabia-saudita-negociacoes-plano-transicao-energetica-observadores-cop30.ghtml",
             "Mostra resistência de produtores de petróleo e interesses econômicos por trás do impasse.",
             "A Arábia Saudita, um dos líderes mundiais de petróleo, vem se posicionando contra a tentativa de um plano prático para abandonar os combustíveis fósseis na COP30."),
            ("nos-bastidores-da-cop30-brasil-arma-estrategia-para-destravar-plano-global-contra-combustiveis-fosseis.ghtml",
             "Estratégia de articulação brasileira para incluir um tema inicialmente fora da agenda.",
             "O governo brasileiro tem se mobilizado nos bastidores da COP30 para que o \"mapa do caminho\" para abandonar os combustíveis fósseis seja oficializado na agenda da conferência."),
            ("paises-apoiam-mapa-caminho-fim-combustiveis-fosseis-cop3.ghtml",
             "Formação de coalizão pró-roteiro; apoio público não é aprovação consensual.",
             "Um grupo de cerca de 80 países defendeu, nesta terça-feira (18) em Belém (PA), a importância da adoção de um \"mapa do caminho\" para o fim do uso dos combustíveis fósseis."),
            ("na-cop30-cientistas-publicam-carta-em-que-criticam-plano-dos-negociadores-contra-combustiveis-fosseis.ghtml",
             "Contraponto científico à ambição dos roteiros propostos durante as negociações.",
             "Na carta, os cientistas afirmaram ainda que não pode haver nenhum novo investimento em combustíveis fósseis."),
            ("cop30-rascunho-de-acordo-e-criticado-por-nao-citar-reducao-de-combustiveis-fosseis-nem-origem-de-financiamento-a-paises-pobres.ghtml",
             "Relaciona a ausência do roteiro ao desacordo sobre volume e origem do financiamento.",
             "O documento fala em duplicar o financiamento, enquanto o grupo de negociadores africanos vinha pedindo para triplicar"),
            ("ue-ameaca-barrar-acordo-da-cop30-e-critica-ausencia-de-metas-sobre-combustiveis-fosseis.ghtml",
             "Contradição entre pressão europeia por ambição e resistência financeira atribuída por observadores.",
             "a União Europeia dificulta as negociações em outra frente: mostra resistência em ampliar recursos para o enfrentamento da crise do clima."),
            ("resultado-da-cop30-frustra-cientistas-ambientalistas-e-representantes-de-diversos-paises.ghtml",
             "Avaliação plural do resultado, contrapondo frustração e preservação do consenso multilateral.",
             "Cientistas, ambientalistas e representantes de diversos países declararam frustração com o resultado final da COP30, mas afirmaram que foi o acordo possível."),
            ("plano-de-acao-em-saude-e-lancado-na-cop-30-em-belem-para-enfrentar-adaptacao-climatica.ghtml",
             "Resultado setorial concreto de adaptação em saúde, além da negociação energética.",
             "foi lançado o Plano de Ação em Saúde de Belém, o primeiro plano internacional dedicado exclusivamente à adaptação climática no setor de saúde."),
            ("apos-cop-sem-acordo-sobre-combustiveis-fosseis-lula-da-60-dias-para-governo-elaborar-proposta-de-transicao-energetica.ghtml",
             "Seguimento doméstico da pendência internacional: elaboração de diretrizes e mecanismos de financiamento.",
             "No despacho desta segunda-feira (8), Lula determinou que os ministérios elaborem um texto para estabelecer as diretrizes desse \"mapa do caminho\"."),
            ("cop30-na-amazonia-reforca-desafio-antigo-e-urgente-mobilizar-trilhoes-para-financiamento-climatico-global.ghtml",
             "Contexto da dívida histórica de financiamento e da demanda de países em desenvolvimento.",
             "Ainda em 2009, durante a COP15 em Copenhague, países desenvolvidos comprometeram-se a mobilizar US$ 100 bilhões anuais até 2020"),
        ],
    },
}


def build(args, themes=None, suffix=""):
    themes = THEMES if themes is None else themes
    expected_articles = 20 * len(themes)
    baseline_path = args.output_dir / f'evals_additional{suffix}_curated_2025_2026.json'
    variants_path = args.output_dir / f'evals_additional{suffix}_query_variants_2025_2026.json'
    report_path = args.output_dir / f'casos_teste_relevancia_adicionais{suffix}_2025_2026.md'
    selection_path = args.output_dir / f'relevance_additional{suffix}_selection_2025_2026.json'
    for path in (baseline_path, variants_path, report_path, selection_path):
        if path.exists():
            raise FileExistsError(f'Refusing to overwrite {path}')
    baseline, variants, selections = [], [], []
    with database(args) as conn:
        for key, theme in themes.items():
            candidates = conn.execute('''SELECT url, title, date_published::text AS date, text_content AS body
                FROM g1_articles WHERE date_published BETWEEN %s AND %s AND title ~* %s
                AND length(btrim(text_content)) > 200 ORDER BY date_published, url''',
                ('2025-06-01', '2026-05-20', theme['pattern'])).fetchall()
            articles, source_rows = [], []
            for position, (slug, rationale, evidence) in enumerate(theme['articles'], 1):
                matches = [row for row in candidates if row['url'].endswith('/' + slug)]
                if len(matches) != 1:
                    raise ValueError(f'{key}/{slug}: expected one primary URL, found {len(matches)}')
                row = matches[0]
                if evidence not in row['body']:
                    raise ValueError(f'{key}/{slug}: evidence is not literal')
                source_rows.append(row)
                articles.append({'rank': position, 'url': row['url'], 'date': row['date'],
                                 'title': row['title'], 'rationale': rationale, 'evidence': evidence,
                                 'body_sha256': hashlib.sha256(row['body'].encode()).hexdigest()})
            if len(articles) != 20 or len({row['url'] for row in articles}) != 20:
                raise ValueError(f'{key}: expected 20 unique URLs')
            if len({row['body_sha256'] for row in articles}) != 20:
                raise ValueError(f'{key}: duplicate article bodies')
            selections.append({'id': key, 'name': theme['name'], 'scope': theme['scope'],
                               'caution': theme['caution'], 'candidate_count': len(candidates),
                               'snapshot_sha256': snapshot_hash(source_rows), 'articles': articles})
            baseline.append({'id': key, 'query': theme['queries'][-1],
                             'relevant_urls': [row['url'] for row in articles]})
    for index, style in enumerate(STYLES):
        for item in baseline:
            variants.append({'id': f"{item['id']}__{style}", 'query': themes[item['id']]['queries'][index],
                             'query_formulation': style, 'relevant_urls': list(item['relevant_urls'])})
    all_urls = [article['url'] for theme in selections for article in theme['articles']]
    if len(set(all_urls)) != expected_articles:
        raise ValueError(f'Expected {expected_articles} distinct article URLs across themes')
    from services.batch_evaluation import validate_document
    for entries in (baseline, variants):
        validate_document({'schema_version': 1, 'evaluations': entries})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(baseline_path, {'schema_version': 1, 'evaluations': baseline})
    write_json(variants_path, {'schema_version': 1, 'evaluations': variants})
    write_json(selection_path, {'version': 1, 'researched_on': date.today().isoformat(),
                               'source': 'g1_articles; read-only local database',
                               'window': ['2025-06-01', '2026-05-20'], 'themes': selections})
    report = ['# Casos adicionais de relevância — 2025/2026', '',
              f'{len(themes)} temas adicionais, com **20 artigos ordenados por tema e {expected_articles} URLs distintas**. '
              'Seleção editorial assistida por IA, não ground truth exaustiva nem revisão humana independente.', '',
              '## Método e limites', '',
              f'- Pesquisa realizada em {date.today().isoformat()}.',
              '- Fonte exclusiva: `g1_articles`, consultada em transação somente de leitura. Nenhuma busca web ou ranking da aplicação foi utilizado.',
              '- Janela inclusiva: `2025-06-01` a `2026-05-20`, por `date_published`. Publicações fora do corpus não foram incluídas.',
              '- Necessidade informacional: compreender uma história continuada, suas causas, evidências, marcos, contrapontos e consequências.',
              '- Descoberta dirigida por candidatos antes não curados no relatório original. Busca de títulos por expressões regulares; contagens incluem ruído e não medem relevância.',
              '- Leitura dirigida do início e de passagens específicas do corpo, não leitura integral de todos os candidatos. Vídeos e áudios não foram assistidos; somente o texto armazenado foi julgado.',
              '- A prioridade é editorial, não cronológica: síntese, mecanismo, marcos e limites probatórios vêm antes de detalhes adicionais. Todos os 20 documentos selecionados são positivos.',
              '- Ausência na seleção significa não julgado, não necessariamente irrelevante. Há sobreposição factual entre sínteses e notícias de marcos; corpos idênticos foram excluídos.',
              '- Datas, URLs primárias, presença do corpo, unicidade e literalidade das evidências foram verificadas no banco. Hashes registram a versão do texto consultado, não prova externa de veracidade.',
              '- A seleção não foi otimizada pelos resultados de nenhum método de busca. Não houve teste de desempenho dessas consultas nesta curadoria.', '',
              '## Arquivos para avaliação', '',
              f'- `{baseline_path.name}`: {len(themes)} consultas completas, uma por tema.',
              f'- `{variants_path.name}`: {len(variants)} consultas, com as mesmas oito estruturas usadas na avaliação anterior, intercaladas por estilo.',
              f'- `{selection_path.name}`: justificativas, evidências literais, datas e hashes por artigo.',
              '- Em cada tema, todas as estruturas usam exatamente as mesmas 20 URLs na mesma ordem. Prefixos de tamanho 1/3/5/10/20 são aninhados.',
              '- Atenção: o avaliador atual compara em k com `relevant_urls[:k]`; isso não é recall contra os 20 positivos fixos em todos os cortes. A curadoria não altera essa regra.', '',
              '## Visão geral', '',
              '| Tema | Candidatos com corpo >200 caracteres | Intervalo selecionado | Datas / meses distintos |',
              '|---|---:|---|---:|']
    for theme in selections:
        dates = [row['date'] for row in theme['articles']]
        report.append(f"| {theme['name']} | {theme['candidate_count']} | {min(dates)} a {max(dates)} | {len(set(dates))} / {len({d[:7] for d in dates})} |")
    for theme in selections:
        report += ['', f"## {theme['name']}", '', f"**ID:** `{theme['id']}`", '',
                   f"**Consulta completa:** {themes[theme['id']]['queries'][-1]}", '',
                   f"**Delimitação:** {theme['scope']}", '', f"**Cautelas:** {theme['caution']}", '',
                   f"**Hash do conjunto consultado:** `{theme['snapshot_sha256']}`", '']
        for article in theme['articles']:
            report += [f"### {theme['id']} — Relevância {article['rank']:02d}", '',
                       f"**{article['date']} — [{article['title']}]({article['url']})**", '',
                       f"**Motivo:** {article['rationale']}", '', f"**Evidência no corpo:** “{article['evidence']}”", '']
    report += ['## Antes de usar como referência definitiva', '',
               'Revisar com outro anotador, confirmar o recorte informacional, congelar a versão do corpus e ampliar julgamentos com resultados não selecionados. '
               'As oito formulações de um tema compartilham a mesma história e não constituem oito temas independentes. '
               'Os conjuntos anteriores permanecem intactos; os novos arquivos não misturam os temas originais com os adicionais.', '']
    report_path.write_text('\n'.join(report), encoding='utf-8')
    for path in (baseline_path, variants_path, report_path, selection_path):
        print(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--timeout-ms', type=int, default=60000)
    build(parser.parse_args())
