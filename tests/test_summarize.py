from app import App
from trafilatura import fetch_url, extract


g1_app = App()

def test_summarize():
    summary = g1_app.summarize("\n".join([
        "O governo anunciou hoje um novo pacote de medidas econômicas focado em infraestrutura...",
        "Especialistas reagem de forma mista às novas medidas de infraestrutura, citando preocupações fiscais...",
        "Mercado fecha em alta após anúncio das medidas governamentais, com destaque para o setor de construção civil..."
    ]))
    print(summary)

def test_summarize_with_real_articles():
    urls = [
        "https://g1.globo.com/rj/rio-de-janeiro/noticia/2025/07/07/declaracao-marco-dos-lideres-do-brics-sobre-financas-climaticas.ghtml",
        "https://g1.globo.com/pa/para/noticia/2025/08/01/cop30-em-belem-forum-raizes-do-amanha-tera-palestras-feira-e-apresentacoes-culturais.ghtml",
        "https://g1.globo.com/pa/para/noticia/2025/10/15/mostra-amazonia-nas-telas-abre-amazoniafidoc-2025-com-pre-estreia-de-xingu-nosso-rio-sagrado-em-belem.ghtml"
    ]
    articles_texts = []
    for url in urls:
        downloaded = fetch_url(url)
        if downloaded:
            text = extract(downloaded)
            if text:
                articles_texts.append(text)
    summary = g1_app.summarize("\n".join(articles_texts))
    print(summary)
