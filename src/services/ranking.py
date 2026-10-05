import math
from pprint import pprint
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import networkx as nx

from models.models import G1Articles
from repositories.article import ArticleRepository
from services.linking import is_junk_surface, uri_label
from services.ner import NERService


class RankingService:
    def __init__(self, article_repository: ArticleRepository, ner_service: NERService):
        self.article_repository = article_repository
        self.entity_repository = ner_service.entity_repository
        self.ner_service = ner_service

    def _save_graph_image(
        self,
        graph: nx.DiGraph,
        article_nodes: set[str],
        page_rank: dict[str, float],
        node_names: dict[str, str],
    ) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path.cwd() / f"graph_{timestamp}.png"

        node_count = max(1, graph.number_of_nodes())
        k = 3.0 / np.sqrt(node_count)

        plt.figure(figsize=(60, 60), dpi=100)
        pos = nx.spring_layout(graph, seed=42, k=k, iterations=200, scale=3.0)

        node_colors = ["#1f77b4" if node in article_nodes else "#ff7f0e" for node in graph.nodes()]
        node_sizes = [900 if node in article_nodes else 250 for node in graph.nodes()]

        nx.draw_networkx(
            graph,
            pos=pos,
            with_labels=False,
            node_color=node_colors,
            node_size=node_sizes,
            edge_color="#b0b0b0",
            alpha=0.9,
            width=0.6,
        )

        labels = {
            node: f"{node_names.get(node, node)}\n{page_rank.get(node, 0.0):.4f}"
            for node in graph.nodes()
        }
        nx.draw_networkx_labels(
            graph,
            pos=pos,
            labels=labels,
            font_size=6,
            font_color="#222222",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.7),
        )

        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches="tight")
        plt.close()

        return output_path

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)

    @classmethod
    def _mmr_scores(
        cls,
        scores: dict[str, float],
        entity_sets: dict[str, set],
        article_urls: list[str],
        lam: float,
    ) -> dict[str, float]:
        """Carbonell–Goldstein greedy MMR over article URLs.

        Relevance is the (normalized) score in `scores`; similarity between two
        articles is the Jaccard index of their entity-neighbor sets.
        """
        remaining = [url for url in article_urls if url in scores]
        mmr: dict[str, float] = {}
        selected: list[str] = []
        while remaining:
            best_url = None
            best_value = -math.inf
            for url in remaining:
                penalty = max(
                    (cls._jaccard(entity_sets.get(url, set()), entity_sets.get(s, set())) for s in selected),
                    default=0.0,
                )
                value = scores[url] - lam * penalty
                if value > best_value or (value == best_value and (best_url is None or (scores[url], url) > (scores[best_url], best_url))):
                    best_value = value
                    best_url = url
            # the anchor pick has nothing selected yet, so no penalty applies
            mmr[best_url] = scores[best_url] if not selected else best_value
            selected.append(best_url)
            remaining.remove(best_url)
        return mmr

    @staticmethod
    def _louvain_seed_selection(
        G: nx.DiGraph,
        article_set: set[str],
        opposite_count: dict[str, int],
        topics_per_community: int,
        community_min_ratio: float,
    ) -> set[str]:
        """Louvain Community-Stratified Seeding.

        Projects the pruned bipartite graph onto the topic nodes (edge weight =
        number of shared articles), finds communities with Louvain, discards
        communities below `community_min_ratio` of the topic total (skipping
        the filter when nothing survives), and pools the top
        `topics_per_community` topics of each surviving community by bipartite
        opposite-node count.
        """
        B = G.to_undirected()
        topic_nodes = [node for node in B.nodes if node not in article_set]
        if not topic_nodes:
            return set()
        projected = nx.algorithms.bipartite.weighted_projected_graph(B, topic_nodes)
        communities = nx.community.louvain_communities(projected, weight="weight", seed=42)
        communities = sorted(
            (sorted(community) for community in communities),
            key=lambda community: (-len(community), community[0] if community else ""),
        )
        print(f"Louvain found {len(communities)} communities (sizes {[len(c) for c in communities]}):")

        threshold = community_min_ratio * len(topic_nodes)
        surviving = [community for community in communities if len(community) >= threshold]
        if not surviving:
            # the filter targets tangent removal; on a graph where every
            # community is small it is counterproductive, so skip it
            print(f"No community >= {threshold:.1f} topics; skipping the macro-community filter.")
            surviving = communities
        else:
            discarded = len(communities) - len(surviving)
            print(f"Macro-community filter (>= {threshold:.1f} topics): {len(surviving)} survive, {discarded} discarded.")

        seeds: set[str] = set()
        for community in surviving:
            top = sorted(community, key=lambda node: (-opposite_count.get(node, 0), node))[:topics_per_community]
            print(f"  community ({len(community)} topics) seeds: {[node.replace('entity:', '') for node in top]}")
            seeds.update(top)
        print(f"Pooled {len(seeds)} seed topics (top-{topics_per_community} per community):")
        pprint(sorted(seeds))
        return seeds

    def ppr(self, results: list[str], mmr_enabled: bool = False, seed_method: str = "hits", seed_ratio: float = 1.0, topics_per_community: int = 3, community_min_ratio: float = 0.05, mmr_lambda: float = 0.5, mmr_top_n: int | None = 5) -> tuple[dict[str, float], list[dict[str, object]], dict[str, object]]:
        if not 0 < seed_ratio <= 1:
            raise ValueError(f"seed_ratio must be in the interval (0, 1], got {seed_ratio}")
        if seed_method not in ("hits", "louvain"):
            raise ValueError(f"seed_method must be 'hits' or 'louvain', got {seed_method!r}")
        if topics_per_community < 1:
            raise ValueError(f"topics_per_community must be >= 1, got {topics_per_community}")
        if not 0 <= community_min_ratio <= 1:
            raise ValueError(f"community_min_ratio must be in the interval [0, 1], got {community_min_ratio}")
        if not 0 <= mmr_lambda <= 1:
            raise ValueError(f"mmr_lambda must be in the interval [0, 1], got {mmr_lambda}")
        if mmr_top_n is not None and mmr_top_n < 1:
            raise ValueError(f"mmr_top_n must be None or >= 1, got {mmr_top_n}")
        article_set = set(results)
        G = nx.DiGraph()
        articles = self.article_repository.get_all(in_=results)
        article_titles_by_url = {article.url: article.title for article in articles}
        entities = self.ner_service.batch_get_or_extract_entities_and_store_for_articles([article.url for article in articles], of_types=["PER", "ORG", "LOC"])
        entities_by_identity: dict[str, str] = {}
        node_names: dict[str, str] = {article.url: article.title for article in articles}
        for article in articles:
            try:
                if not entities.get(article.url):
                    print(f"No entities found for article {article.url}: kept with score 0, but no entity edges.")
                G.add_node(article.url)
                for entity in entities.get(article.url, []):
                    entity_text = entity.text_
                    if entity_text in ["g1", "G1", "Foto", "foto", "Vídeo", "vídeo", "“", "”"]:
                        continue
                    if is_junk_surface(entity_text):
                        continue
                    # canonical identity: DBpedia URI when linked, surface text otherwise
                    entity_identity = entity.canonical or entity_text
                    entity_node = entities_by_identity.get(entity_identity)
                    if entity_node is None:
                        entity_node = f"entity:{entity_identity}"
                        entities_by_identity[entity_identity] = entity_node
                        G.add_node(entity_node)
                        node_names[entity_node] = uri_label(entity_identity) if entity.canonical else entity_text
                    G.add_edge(entity_node, article.url)
                    G.add_edge(article.url, entity_node)
            except Exception as e:
                print(f"Error processing entities for article {article.url}: {e}")
                continue
        # k-core pruning: nx counts in+out degree and every edge is stored in
        # both directions, so k=4 means "at least 2 opposite nodes" (entities
        # cited by >=2 articles, articles with >=2 topics) — peeled iteratively
        G = nx.k_core(G, k=4)
        degrees = G.degree()
        # print("Graph degrees:")
        # pprint(degrees)


        alpha = 0.85
        # P = nx.google_matrix(G, alpha=alpha)
        # PPR_s =
        print("Calculating PageRank...")
        page_rank = nx.pagerank(G, alpha=alpha)
        # graph_image_path = self._save_graph_image(G, set(results), page_rank, node_names)
        # print(f"Graph image saved to: {graph_image_path}")

        # --- seed selection (switchable for A/B testing) -------------------
        # HITS: keep only article->entity edges (entity->article ignored), so
        # entities rank as authorities by how much the articles cite them
        # Louvain: community-stratified seeding over the projected topic graph
        G_hits = nx.DiGraph((source, target) for source, target in G.edges() if source in article_set)
        # opposite-node counts (degree // 2) used by both the Louvain seeding
        # and the sqrt normalization downstream
        opposite_count = {node: degree // 2 for node, degree in degrees}
        if seed_method == "hits":
            print("Calculating HITS...")
            if G_hits.number_of_edges() > 0:
                hubs, authorities = nx.hits(G_hits)
            else:
                hubs = {}
                authorities = {}
            authorities = {node: (0.0 if node in article_set else score) for node, score in authorities.items()}

            entity_node_count = len([node for node in page_rank if node not in results])
            seed_count = math.ceil(entity_node_count * seed_ratio)
            top_entities = sorted(
                [(node, authorities.get(node, 0.0)) for node in page_rank if node not in results],
                key=lambda x: x[1],
                reverse=True,
            )[:seed_count]
            print(f"Top {seed_count} of {entity_node_count} entities by HITS authority score:")
            pprint(top_entities)
            top_entity_ids = {node for node, _ in top_entities}
        else:
            print("Calculating HITS (for the Peso field)...")
            if G_hits.number_of_edges() > 0:
                hubs, authorities = nx.hits(G_hits)
            else:
                hubs = {}
            top_entity_ids = self._louvain_seed_selection(
                G, article_set, opposite_count, topics_per_community, community_min_ratio
            )
        if top_entity_ids:
            # PPR personalized by the most influential entities (HITS authorities)
            personalization = {
                node: (1.0 / len(top_entity_ids)) if node in top_entity_ids else 0.0
                for node in G.nodes()
            }
        else:
            # No entities in the graph: fall back to the retrieved articles as seeds
            personalization = {
                node: (1.0 / len(results)) if node in results else 0.0
                for node in G.nodes()
            }
        personalized_page_rank = nx.pagerank(
            G,
            alpha=alpha,
            personalization=personalization,
        )
        pprint(page_rank)
        article_degrees = {node: degree for node, degree in degrees if node in results}
        print("Degrees for articles:")
        pprint(article_degrees)

        # square-root degree normalization: PPR divided by sqrt(out-degree),
        # a gentler hub-bias correction than dividing by the raw degree
        normalized = {
            node: personalized_page_rank.get(node, 0.0) / math.sqrt(opposite_count[node])
            if opposite_count.get(node, 0) > 0 else 0.0
            for node in personalized_page_rank
        }
        print("Normalized PPR (per-sqrt-out-degree):")
        pprint(normalized)

        # MMR over the articles present in the graph, relevance = normalized PPR,
        # similarity = Jaccard index of the entity sets two articles connect to;
        # disabled by default — pass mmr_enabled=True to run the diversity pass
        article_in_graph = [node for node in G.nodes() if node in article_set]
        if mmr_enabled:
            entity_sets = {}
            for article_url in article_in_graph:
                entity_sets[article_url] = {nbr for nbr in G[article_url] if nbr not in article_set}
            mmr_scores = self._mmr_scores(
                {url: normalized[url] for url in article_in_graph},
                entity_sets,
                article_in_graph,
                mmr_lambda,
            )
            ranked_values = sorted(
                ((article, mmr_scores[article]) for article in mmr_scores),
                key=lambda x: x[1],
                reverse=True,
            )
            flagged = {article for article, _ in ranked_values[:mmr_top_n]} if mmr_top_n is not None else set(mmr_scores)
            # every retrieved article is included; articles without entity edges are
            # kept with score 0 and are never flagged
            for url in article_set:
                mmr_scores.setdefault(url, 0.0)
            print(f"MMR (lambda={mmr_lambda}): flagged {len(flagged)} of {len(mmr_scores)} articles:")
            pprint([(url, mmr_scores.get(url)) for url in mmr_scores if url in flagged])
        else:
            flagged = set()
            mmr_scores = {}

        # every retrieved article is included, ordered by normalized PPR
        ranked_urls = list(article_set)
        ranked_urls.sort(key=lambda url: (normalized.get(url, 0.0), url), reverse=True)
        ranked = [
            {'article': url, 'score': normalized.get(url, 0.0), 'degree': opposite_count.get(url, 0), 'mmr_score': mmr_scores.get(url, 0.0), 'mmr': url in flagged}
            for url in ranked_urls
        ]

        graph_data = {
            "nodes": [
                {
                    "id": node,
                    "label": node_names.get(node, node),
                    "type": "article" if node in results else "entity",
                    "score": normalized[node],
                    # HITS role score: articles are hubs (they cite), entities
                    # are authorities (they are cited)
                    "hits": hubs.get(node, 0.0) if node in article_set else authorities.get(node, 0.0),
                    # bipartite graph stores both edge directions; report the half
                    # that corresponds to real opposite-node counts (citations)
                    "degree": opposite_count[node],
                    "ppr_seed": node in top_entity_ids,
                }
                for node in G.nodes()
            ],
            "links": [
                {"source": source, "target": target}
                for source, target in G.edges()
            ],
            "meta": {
                "article_count": len(results),
                "entity_count": len([node for node in G.nodes() if node not in results]),
                "ppr_seed_count": len(top_entity_ids),
                "seed_method": seed_method,
            },
        }
        return page_rank, ranked, graph_data
