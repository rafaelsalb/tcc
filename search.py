from ddgs import DDGS


def news(query, num_results=10):
    ddgs = DDGS()
    results = []
    for r in ddgs.news(
        f"{query} site:g1.globo.com",
        max_results=num_results,
        region="br-pt",
        safesearch="moderate"
    ):
        results.append(r)
    return results
