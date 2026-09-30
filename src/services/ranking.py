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

    def ppr(self, results: list[str], seed_ratio: float = 1.0) -> tuple[dict[str, float], list[dict[str, object]], dict[str, object]]:
        if not 0 < seed_ratio <= 1:
            raise ValueError(f"seed_ratio must be in the interval (0, 1], got {seed_ratio}")
        G = nx.DiGraph()
        articles = self.article_repository.get_all(in_=results)
        article_titles_by_url = {article.url: article.title for article in articles}
        entities = self.ner_service.batch_get_or_extract_entities_and_store_for_articles([article.url for article in articles], of_types=["PER", "ORG", "LOC"])
        entities_by_identity: dict[str, str] = {}
        node_names: dict[str, str] = {article.url: article.title for article in articles}
        for article in articles:
            try:
                if not entities.get(article.url):
                    print(f"No entities found for article {article.url}. Skipping.")
                    continue
                G.add_node(article.url)
                for entity in entities[article.url]:
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
        degree_two_entities = [node for node in G.nodes() if node not in results and G.degree(node) == 2]
        G.remove_nodes_from(degree_two_entities)
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

        # HITS seed selection: keep only article->entity edges (entity->article
        # ignored), so entities rank as authorities by how much the articles cite them
        article_set = set(results)
        G_hits = nx.DiGraph((source, target) for source, target in G.edges() if source in article_set)
        print("Calculating HITS...")
        if G_hits.number_of_edges() > 0:
            _, authorities = nx.hits(G_hits)
        else:
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
        # top_entities_with_text = []
        # for node, score in top_entities:
        #     entity = self.entity_repository.get_by_id(int(node))
        #     top_entities_with_text.append((entity.text_, score))
        # pprint(top_entities_with_text)
        pprint(top_entities)
        top_entity_ids = {node for node, _ in top_entities}
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
        sorted_articles = [
            {'article': article, 'score': score, 'degree': degree} for article, score, degree
            in sorted([(article, personalized_page_rank[article], article_degrees.get(article, 0)) for article in page_rank if article in results], key=lambda x: x[1], reverse=True)
        ]
        graph_data = {
            "nodes": [
                {
                    "id": node,
                    "label": node_names.get(node, node),
                    "type": "article" if node in results else "entity",
                    "score": page_rank.get(node, 0.0),
                    # bipartite graph stores both edge directions; report the half
                    # that corresponds to real opposite-node counts (citations)
                    "degree": article_degrees.get(node, degrees[node]) // 2,
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
            },
        }
        return page_rank, sorted_articles, graph_data
