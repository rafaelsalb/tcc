import math
from pprint import pprint
from pathlib import Path
from datetime import datetime
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np
import networkx as nx

from models.models import G1Articles
from repositories.article import ArticleRepository
from services.linking import is_junk_surface, normalize_surface, uri_label
from services.ner import NERService


class RankingService:
    def __init__(self, article_repository: ArticleRepository, ner_service: NERService):
        self.article_repository = article_repository
        self.entity_repository = ner_service.entity_repository
        self.ner_service = ner_service
        # Graph/score caches for interactive callers (e.g. rank_results).
        # Request paths clone via for_batch(), which resets all of these;
        # without initializing them here, getattr(..., {}) allocated a
        # throwaway dict on every call and identical pools rebuilt the whole
        # graph and re-ran PageRank each time.
        self._batch_graphs = {}
        self._batch_scores = {}
        self._batch_cross_encoder_scores = {}
        self.batch_counts = {"graph_builds": 0, "ppr_runs": 0}
        self.batch_timings = {
            "graph_seconds": 0.0, "graph_article_fetch_seconds": 0.0,
            "graph_entity_load_extract_seconds": 0.0, "graph_assembly_seconds": 0.0,
            "graph_pruning_seconds": 0.0, "ppr_seconds": 0.0, "mmr_seconds": 0.0,
        }

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

    @staticmethod
    def _ppr_top10_seeds(page_rank, article_set, opposite_count):
        """Top 10% of entities by initial PR / sqrt(degree), never by HITS."""
        entities = [node for node in page_rank if node not in article_set]
        ordered = sorted(entities, key=lambda node: (
            -page_rank[node] / math.sqrt(opposite_count[node])
            if opposite_count.get(node, 0) else 0.0,
            node,
        ))
        return set(ordered[:max(1, math.ceil(len(entities) * 0.10))])

    @staticmethod
    def _serialize_graph(graph, article_set, node_names, node_scores, *, opposite_count=None,
                         hit_scores=None, seeds=None, personalization=None, meta=None,
                         edge_weights=None):
        """Serialize a candidate graph in the format consumed by the graph UI."""
        opposite_count = opposite_count or {node: graph.degree(node) // 2 for node in graph}
        hit_scores = hit_scores or {}
        seeds = seeds or set()
        personalization = personalization or {}
        edge_weights = edge_weights or {}
        return {
            "nodes": [
                {
                    "id": node,
                    "label": node_names.get(node, node),
                    "type": "article" if node in article_set else "entity",
                    "score": float(node_scores.get(node, 0.0)),
                    "hits": float(hit_scores.get(node, 0.0)),
                    "degree": int(opposite_count.get(node, 0)),
                    "ppr_seed": node in seeds,
                    "personalization": float(personalization.get(node, 0.0)),
                }
                for node in graph.nodes()
            ],
            "links": [
                {
                    "source": source,
                    "target": target,
                    **({"weight": float(edge_weights[(source, target)])}
                       if (source, target) in edge_weights else {}),
                }
                for source, target in graph.edges()
            ],
            "meta": dict(meta or {}),
        }

    def _prepare_graph(self, results):
        article_set = set(results)
        G = nx.DiGraph()
        step_started = perf_counter()
        articles = self.article_repository.get_all(in_=results, limit=None)
        article_fetch_seconds = perf_counter() - step_started
        article_titles_by_url = {article.url: article.title for article in articles}
        step_started = perf_counter()
        entities = self.ner_service.batch_get_or_extract_entities_and_store_for_articles([article.url for article in articles], of_types=["PER", "ORG", "LOC"])
        entity_load_extract_seconds = perf_counter() - step_started
        entities_by_identity = {}
        nodes_by_surface = {}
        node_names = dict(article_titles_by_url)
        step_started = perf_counter()
        for article in articles:
            try:
                G.add_node(article.url)
                for entity in entities.get(article.url, []):
                    entity_text = entity.text_
                    if entity_text in ["g1", "G1", "Foto", "foto", "Vídeo", "vídeo", "“", "”"] or is_junk_surface(entity_text):
                        continue
                    identity = entity.canonical or entity_text
                    entity_node = entities_by_identity.get(identity)
                    if entity_node is None:
                        entity_node = f"entity:{identity}"
                        entities_by_identity[identity] = entity_node
                        G.add_node(entity_node)
                        node_names[entity_node] = uri_label(identity) if entity.canonical else entity_text
                    normalized_surface = normalize_surface(entity_text)
                    if normalized_surface:
                        nodes_by_surface.setdefault(normalized_surface, set()).add(entity_node)
                    G.add_edge(entity_node, article.url)
                    G.add_edge(article.url, entity_node)
            except Exception as exc:
                print(f"Error processing entities for article {article.url}: {exc}")
        graph_assembly_seconds = perf_counter() - step_started
        original_graph = G
        step_started = perf_counter()
        G = nx.k_core(G, k=4)
        seed_fallback = None
        if not G:
            G = nx.DiGraph()
            G.add_nodes_from(sorted(article_set))
            seed_fallback = "no_surviving_entities"
        graph_pruning_seconds = perf_counter() - step_started
        return dict(G=G, original_graph=original_graph, articles=articles,
                    article_titles_by_url=article_titles_by_url, node_names=node_names,
                    seed_fallback=seed_fallback, entity_nodes_by_identity=entities_by_identity,
                    entity_nodes_by_surface=nodes_by_surface,
                    timings={
                        "graph_article_fetch_seconds": article_fetch_seconds,
                        "graph_entity_load_extract_seconds": entity_load_extract_seconds,
                        "graph_assembly_seconds": graph_assembly_seconds,
                        "graph_pruning_seconds": graph_pruning_seconds,
                    })

    def for_batch(self):
        """Clone with request-local caches, leaving the web service untouched."""
        from copy import copy
        ranker = copy(self)
        ranker._batch_graphs = {}
        ranker._batch_scores = {}
        ranker._batch_cross_encoder_scores = {}
        ranker.batch_counts = {"graph_builds": 0, "ppr_runs": 0}
        ranker.batch_timings = {
            "graph_seconds": 0.0, "graph_article_fetch_seconds": 0.0,
            "graph_entity_load_extract_seconds": 0.0, "graph_assembly_seconds": 0.0,
            "graph_pruning_seconds": 0.0, "ppr_seconds": 0.0, "mmr_seconds": 0.0,
        }
        return ranker

    def _query_seed_nodes(self, query, prepared):
        """Match linked query entities to graph nodes, preferring canonical URIs."""
        entities = self.ner_service.extract_entities(query) if query else []
        identities = set()
        for entity in entities:
            if entity.get("label") not in ("PER", "ORG", "LOC"):
                continue
            surface = entity.get("text", "")
            if not surface or is_junk_surface(surface):
                continue
            canonical = entity.get("canonical")
            identity_node = prepared["entity_nodes_by_identity"].get(canonical) if canonical else None
            if identity_node:
                identities.add(identity_node)
                continue
            normalized = normalize_surface(surface)
            identities.update(prepared["entity_nodes_by_surface"].get(normalized, ()))
        return entities, identities

    def _ppr_inputs(self, results, prepared, seed_method, seed_ratio, topics_per_community, community_min_ratio,
                    query=None, query_seed_fallback="hits"):
        G = prepared["G"]
        article_set = set(results)
        degrees = G.degree()
        seed_fallback = prepared["seed_fallback"]
        alpha = 0.85
        if "page_rank" not in prepared:
            prepared["page_rank"] = nx.pagerank(G, alpha=alpha)
        page_rank = prepared["page_rank"]
        G_hits = nx.DiGraph((source, target) for source, target in G.edges() if source in article_set)
        opposite_count = {node: degree // 2 for node, degree in degrees}
        query_entity_count = 0
        query_entity_matched_count = 0
        query_seed_fallback_reason = None
        query_seed_type = "entity"
        effective_seed_method = seed_method
        if seed_method == "query_entities":
            query_entities, matched_nodes = self._query_seed_nodes(query, prepared)
            query_entity_count = len([e for e in query_entities if e.get("label") in ("PER", "ORG", "LOC")])
            core_entities = matched_nodes & set(G) - article_set
            if core_entities:
                top_entity_ids = core_entities
                query_entity_matched_count = len(core_entities)
                hubs, authorities = {}, {}
            else:
                # The entity may have been removed by k-core pruning. Re-anchor
                # on its directly connected candidate articles that survived.
                original_graph = prepared["original_graph"]
                article_seeds = {
                    article
                    for node in matched_nodes
                    if node in original_graph
                    for article in original_graph.neighbors(node)
                    if article in article_set and article in G
                }
                if article_seeds:
                    top_entity_ids = article_seeds
                    query_entity_matched_count = len(matched_nodes)
                    query_seed_type = "article"
                    query_seed_fallback_reason = "matched_entities_pruned_to_articles"
                    hubs, authorities = {}, {}
                else:
                    query_seed_fallback_reason = "no_query_entities" if query_entity_count == 0 else "no_graph_match"
                    effective_seed_method = query_seed_fallback
                    if effective_seed_method == "hits":
                        if "hits" not in prepared:
                            prepared["hits"] = nx.hits(G_hits) if G_hits.number_of_edges() > 0 else ({}, {})
                        hubs, authorities = prepared["hits"]
                        authorities = {node: (0.0 if node in article_set else score)
                                       for node, score in authorities.items()}
                        seed_count = math.ceil(sum(node not in article_set for node in page_rank) * seed_ratio)
                        top_entities = sorted(
                            [(node, authorities.get(node, 0.0)) for node in page_rank if node not in article_set],
                            key=lambda x: x[1], reverse=True,
                        )[:seed_count]
                        top_entity_ids = {node for node, _ in top_entities}
                    elif effective_seed_method == "louvain":
                        if "hits" not in prepared:
                            prepared["hits"] = nx.hits(G_hits) if G_hits.number_of_edges() > 0 else ({}, {})
                        hubs, authorities = prepared["hits"]
                        top_entity_ids = self._louvain_seed_selection(
                            G, article_set, opposite_count, topics_per_community, community_min_ratio)
                    else:
                        hubs, authorities = {}, {}
                        top_entity_ids = self._ppr_top10_seeds(page_rank, article_set, opposite_count)
        elif seed_method in ("hits", "louvain"):
            if "hits" not in prepared:
                prepared["hits"] = nx.hits(G_hits) if G_hits.number_of_edges() > 0 else ({}, {})
            hubs, authorities = prepared["hits"]
            if seed_method == "hits":
                authorities = {node: (0.0 if node in article_set else score) for node, score in authorities.items()}
                seed_count = math.ceil(sum(node not in article_set for node in page_rank) * seed_ratio)
                top_entities = sorted(
                    [(node, authorities.get(node, 0.0)) for node in page_rank if node not in article_set],
                    key=lambda x: x[1], reverse=True,
                )[:seed_count]
                top_entity_ids = {node for node, _ in top_entities}
            else:
                top_entity_ids = self._louvain_seed_selection(
                    G, article_set, opposite_count, topics_per_community, community_min_ratio)
        else:
            hubs, authorities = {}, {}
            top_entity_ids = self._ppr_top10_seeds(page_rank, article_set, opposite_count)
        if top_entity_ids:
            personalization = {node: 1.0 / len(top_entity_ids) if node in top_entity_ids else 0.0 for node in G}
        else:
            seed_fallback = seed_fallback or "no_entity_seeds"
            personalization = {node: 1.0 / len(article_set) if node in article_set else 0.0 for node in G}
        personalized = nx.pagerank(G, alpha=alpha, personalization=personalization)
        normalized = {
            node: personalized.get(node, 0.0) / math.sqrt(opposite_count[node])
            if opposite_count.get(node, 0) > 0 else (personalized.get(node, 0.0) if seed_fallback else 0.0)
            for node in personalized
        }
        return dict(page_rank=page_rank, normalized=normalized, opposite_count=opposite_count,
                    hubs=hubs, authorities=authorities, top_entity_ids=top_entity_ids,
                    personalization=personalization, seed_fallback=seed_fallback,
                    effective_seed_method=effective_seed_method,
                    query_entity_count=query_entity_count,
                    query_entity_matched_count=query_entity_matched_count,
                    query_seed_fallback_reason=query_seed_fallback_reason,
                    query_seed_type=query_seed_type)

    def ppr(self, results: list[str], mmr_enabled: bool = False, seed_method: str = "hits", seed_ratio: float = 1.0, topics_per_community: int = 3, community_min_ratio: float = 0.05, mmr_lambda: float = 0.5, mmr_top_n: int | None = 5, query: str | None = None, query_seed_fallback: str = "hits") -> tuple[dict[str, float], list[dict[str, object]], dict[str, object]]:
        if not 0 < seed_ratio <= 1:
            raise ValueError(f"seed_ratio must be in the interval (0, 1], got {seed_ratio}")
        if seed_method not in ("hits", "louvain", "ppr_top10", "query_entities"):
            raise ValueError(f"unsupported seed_method: {seed_method!r}")
        if query_seed_fallback not in ("hits", "louvain", "ppr_top10"):
            raise ValueError("query_seed_fallback must be hits, louvain or ppr_top10")
        if topics_per_community < 1:
            raise ValueError(f"topics_per_community must be >= 1, got {topics_per_community}")
        if not 0 <= community_min_ratio <= 1:
            raise ValueError(f"community_min_ratio must be in the interval [0, 1], got {community_min_ratio}")
        if not 0 <= mmr_lambda <= 1:
            raise ValueError(f"mmr_lambda must be in the interval [0, 1], got {mmr_lambda}")
        if mmr_top_n is not None and mmr_top_n < 1:
            raise ValueError(f"mmr_top_n must be None or >= 1, got {mmr_top_n}")
        article_set = set(results)
        graph_cache = getattr(self, "_batch_graphs", {})
        score_cache = getattr(self, "_batch_scores", {})
        pool = tuple(results)
        if pool not in graph_cache:
            tick = perf_counter()
            graph_cache[pool] = self._prepare_graph(results)
            if hasattr(self, "batch_counts"):
                self.batch_counts["graph_builds"] += 1
                self.batch_timings["graph_seconds"] += perf_counter() - tick
                for name, seconds in graph_cache[pool].get("timings", {}).items():
                    self.batch_timings[name] += seconds
        prepared = graph_cache[pool]
        query_key = query.strip() if seed_method == "query_entities" and query else None
        key = (pool, seed_method, seed_ratio, topics_per_community, community_min_ratio,
               query_key, query_seed_fallback if seed_method == "query_entities" else None)
        if key not in score_cache:
            tick = perf_counter()
            if seed_method == "query_entities":
                score_cache[key] = self._ppr_inputs(
                    results, prepared, seed_method, seed_ratio, topics_per_community,
                    community_min_ratio, query=query, query_seed_fallback=query_seed_fallback)
            else:
                score_cache[key] = self._ppr_inputs(
                    results, prepared, seed_method, seed_ratio, topics_per_community, community_min_ratio)
            if hasattr(self, "batch_counts"):
                self.batch_counts["ppr_runs"] += 1
                self.batch_timings["ppr_seconds"] += perf_counter() - tick
        scores = score_cache[key]
        G, original_graph = prepared["G"], prepared["original_graph"]
        articles, node_names = prepared["articles"], prepared["node_names"]
        page_rank, normalized = scores["page_rank"], scores["normalized"]
        opposite_count = scores["opposite_count"]
        hubs, authorities = scores["hubs"], scores["authorities"]
        top_entity_ids = scores["top_entity_ids"]
        personalization, seed_fallback = scores["personalization"], scores["seed_fallback"]
        query_seed_diagnostics = {
            "query_entity_count": scores["query_entity_count"],
            "query_entity_matched_count": scores["query_entity_matched_count"],
            "query_seed_fallback_reason": scores["query_seed_fallback_reason"],
            "query_seed_type": scores["query_seed_type"],
        } if seed_method == "query_entities" else {}

        # MMR over the articles present in the graph, relevance = normalized PPR,
        # similarity = Jaccard index of the entity sets two articles connect to;
        # disabled by default — pass mmr_enabled=True to run the diversity pass
        article_in_graph = [node for node in G.nodes() if node in article_set]
        if mmr_enabled:
            mmr_started = perf_counter()
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
            if hasattr(self, "batch_timings"):
                self.batch_timings["mmr_seconds"] += perf_counter() - mmr_started
        else:
            flagged = set()
            mmr_scores = {}

        # every retrieved article is included, ordered by normalized PPR
        ranked_urls = list(article_set)
        if mmr_enabled:
            ranked_urls.sort(key=lambda url: (mmr_scores.get(url, 0.0), url), reverse=True)
        else:
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
                    "personalization": personalization.get(node, 0.0),
                }
                for node in G.nodes()
            ],
            "links": [
                {"source": source, "target": target}
                for source, target in G.edges()
            ],
            "meta": {
                "article_count": len(results),
                "entity_count": len([node for node in G.nodes() if node not in article_set]),
                "ppr_seed_count": len(top_entity_ids),
                "seed_method": seed_method,
                "effective_seed_method": scores["effective_seed_method"],
                **query_seed_diagnostics,
                "seed_fallback": seed_fallback,
                "graph_surviving_articles": sum(node in article_set for node in G.nodes()) if seed_fallback is None else 0,
                "graph_articles_before_pruning": len(articles),
                "graph_entities_before_pruning": sum(node not in article_set for node in original_graph.nodes()),
            },
        }
        return page_rank, ranked, graph_data

    def graph_hits_cross_encoder(self, results, *, query, article_probabilities,
                                 fallback_seed_method="hits", query_seed_fallback="hits"):
        """Weighted HITS over query-entity edges, scaled by cross-encoder probability."""
        article_urls = list(dict.fromkeys(results))
        article_set = set(article_urls)
        tick = perf_counter()
        graph_cache = getattr(self, "_batch_graphs", {})
        pool = tuple(article_urls)
        if pool not in graph_cache:
            graph_cache[pool] = self._prepare_graph(article_urls)
            if hasattr(self, "batch_counts"):
                self.batch_counts["graph_builds"] += 1
                self.batch_timings["graph_seconds"] += perf_counter() - tick
                for name, seconds in graph_cache[pool].get("timings", {}).items():
                    self.batch_timings[name] += seconds
        prepared = graph_cache[pool]
        original_graph = prepared["original_graph"]
        query_entities, matched_nodes = self._query_seed_nodes(query, prepared)
        query_entity_count = sum(entity.get("label") in ("PER", "ORG", "LOC") for entity in query_entities)
        query_nodes = sorted((matched_nodes & set(original_graph)) - article_set)

        matrix = np.zeros((len(article_urls), len(query_nodes)), dtype=np.float64)
        connected_entities = set()
        for article_index, article in enumerate(article_urls):
            probability = min(1.0, max(0.0, float(article_probabilities.get(article, 0.0))))
            if probability == 0.0 or article not in original_graph:
                continue
            neighbors = set(original_graph.successors(article)) | set(original_graph.predecessors(article))
            for entity_index, entity in enumerate(query_nodes):
                if entity in neighbors:
                    matrix[article_index, entity_index] = probability
                    connected_entities.add(entity)

        if not query_entity_count:
            fallback_reason = "no_query_entities"
        elif not query_nodes:
            fallback_reason = "no_graph_match"
        elif not connected_entities or not np.any(matrix):
            fallback_reason = "no_query_entity_edges_in_cross_encoder_window"
        else:
            fallback_reason = None

        if fallback_reason:
            ranked, graph = self.graph_rank(
                article_urls, method="hits", seed_method=fallback_seed_method,
                query=query, query_seed_fallback=query_seed_fallback,
            )
            graph["meta"].update(
                graph_method="hits_cross_encoder_fallback",
                query_entity_count=query_entity_count,
                query_entity_matched_count=len(query_nodes),
                query_seed_fallback_reason=fallback_reason,
                cross_encoder_probability_count=sum(url in article_probabilities for url in article_urls),
            )
            return ranked, graph

        # Weighted bipartite HITS: article probabilities scale edges to query
        # entities; unmentioned entities are absent (equivalent to weight zero).
        hubs = np.asarray([float(article_probabilities.get(url, 0.0)) for url in article_urls], dtype=np.float64)
        norm = np.linalg.norm(hubs)
        if norm:
            hubs /= norm
        authorities = np.zeros(len(query_nodes), dtype=np.float64)
        for _ in range(500):
            authorities = matrix.T @ hubs
            norm = np.linalg.norm(authorities)
            if not norm:
                break
            authorities /= norm
            updated = matrix @ authorities
            norm = np.linalg.norm(updated)
            if not norm:
                hubs = updated
                break
            updated /= norm
            if np.linalg.norm(updated - hubs) < 1e-10:
                hubs = updated
                break
            hubs = updated
        maximum = float(hubs.max(initial=0.0))
        scores = hubs / maximum if maximum else hubs
        ranked = [{"article": url, "score": float(score)}
                  for url, score in sorted(zip(article_urls, scores), key=lambda row: (-row[1], row[0]))]
        elapsed = perf_counter() - tick
        node_scores = {url: float(score) for url, score in zip(article_urls, scores)}
        hit_scores = dict(node_scores)
        hit_scores.update({entity: float(score) for entity, score in zip(query_nodes, authorities)})
        node_scores.update({entity: float(score) for entity, score in zip(query_nodes, authorities)})
        edge_weights = {}
        for article in article_urls:
            probability = min(1.0, max(0.0, float(article_probabilities.get(article, 0.0))))
            for entity in query_nodes:
                if (article, entity) in original_graph.edges or (entity, article) in original_graph.edges:
                    edge_weights[(article, entity)] = probability
                    edge_weights[(entity, article)] = probability
        graph_data = self._serialize_graph(
            original_graph, article_set, prepared["node_names"], node_scores,
            hit_scores=hit_scores, seeds=connected_entities,
            personalization={node: 1.0 / len(connected_entities) for node in connected_entities}
            if connected_entities else {},
            edge_weights=edge_weights,
            meta={
                "article_count": len(article_urls),
                "entity_count": sum(node not in article_set for node in original_graph),
                "graph_method": "hits_cross_encoder", "graph_seconds": elapsed,
                "graph_surviving_articles": sum(url in prepared["G"] for url in article_urls),
                "graph_entity_count": len(query_nodes), "graph_seed_count": len(connected_entities),
                "seed_method": "query_entities", "effective_seed_method": "query_entities",
                "query_entity_count": query_entity_count, "query_entity_matched_count": len(query_nodes),
                "query_seed_type": "entity", "query_seed_fallback_reason": None,
                "cross_encoder_probability_count": sum(url in article_probabilities for url in article_urls),
            },
        )
        return ranked, graph_data

    def graph_rank(self, results, method="rwr", seed_method="hits", alpha=0.85, hop_decay=0.5,
                   query=None, query_seed_fallback="hits"):
        """Query-seeded graph rankings over the same article/entity candidate graph."""
        if method not in ("rwr", "hits", "salsa", "path", "walk"):
            raise ValueError(f"unsupported graph ranking: {method}")
        if not 0 < alpha < 1 or not 0 <= hop_decay <= 1:
            raise ValueError("alpha must be in (0,1) and hop_decay in [0,1]")
        tick = perf_counter()
        graph_cache = getattr(self, "_batch_graphs", {})
        pool = tuple(results)
        if pool not in graph_cache:
            graph_cache[pool] = self._prepare_graph(results)
            if hasattr(self, "batch_counts"):
                self.batch_counts["graph_builds"] += 1
                self.batch_timings["graph_seconds"] += perf_counter() - tick
                for name, seconds in graph_cache[pool].get("timings", {}).items():
                    self.batch_timings[name] += seconds
        prepared = graph_cache[pool]
        graph = prepared["G"]
        article_set = set(results)
        if seed_method == "query_entities":
            inputs = self._ppr_inputs(results, prepared, seed_method, 1.0, 3, 0.05,
                                      query=query, query_seed_fallback=query_seed_fallback)
        else:
            inputs = self._ppr_inputs(results, prepared, seed_method, 1.0, 3, 0.05)
        inputs.setdefault("query_seed_type", "entity")
        inputs.setdefault("effective_seed_method", seed_method)
        inputs.setdefault("query_entity_count", 0)
        inputs.setdefault("query_entity_matched_count", 0)
        inputs.setdefault("query_seed_fallback_reason", None)
        seeds = inputs["top_entity_ids"]
        entity_nodes = set(graph) - article_set
        article_nodes = article_set & set(graph)
        seed_articles = set(seeds) & article_set
        seed_articles.update(article for seed in (set(seeds) - article_set) if seed in graph
                             for article in graph.predecessors(seed) if article in article_set)

        node_scores = {node: inputs.get("normalized", {}).get(node, 0.0) for node in graph}
        hit_scores = {}
        if method == "rwr":
            node_scores = nx.pagerank(graph, alpha=alpha, personalization=inputs["personalization"])
            scores = {url: node_scores.get(url, 0.0) for url in results}
        elif method == "hits":
            # Query-conditioned HITS: query seed entities are hubs and connected
            # articles are authorities, matching the retrieval direction.
            if inputs["query_seed_type"] == "article":
                scores = {url: (1.0 / len(seed_articles) if url in seed_articles else 0.0) for url in results}
            else:
                directed = nx.DiGraph((e, a) for e in seeds for a in graph.predecessors(e) if a in article_set)
                try:
                    hubs, authority = nx.hits(directed, max_iter=500, normalized=True) if directed.number_of_edges() else ({}, {})
                except nx.PowerIterationFailedConvergence:
                    hubs = {node: 0.0 for node in seeds}
                    authority = {node: 0.0 for node in article_nodes}
                scores = {url: authority.get(url, 0.0) for url in results}
                hit_scores = {**hubs, **authority}
                node_scores.update(hit_scores)
        elif method in ("salsa", "walk"):
            # SALSA-style authority random walk; walk uses the same typed transitions
            # but stops at the configured two-hop horizon rather than taking a full
            # stationary walk.
            scores = {url: 0.0 for url in results}
            if inputs["query_seed_type"] == "article":
                frontier = {node: 0.0 for node in entity_nodes}
                for article in seed_articles:
                    neighbors = [node for node in graph.successors(article) if node in entity_nodes]
                    for entity in neighbors:
                        frontier[entity] += 1.0 / max(1, len(seed_articles) * len(neighbors))
            else:
                frontier = {node: (1.0 / len(seeds) if node in seeds else 0.0) for node in entity_nodes}
            node_scores.update(frontier)
            if method == "salsa":
                for _ in range(32):
                    # k-core pruning can remove retrieved articles. Keep only
                    # graph-resident articles in graph transitions; all original
                    # candidates are still returned later with absent scores = 0.
                    article_mass = {url: 0.0 for url in article_nodes}
                    for entity, mass in frontier.items():
                        neighbors = [url for url in graph.predecessors(entity) if url in article_set]
                        for url in neighbors:
                            article_mass[url] += mass / max(1, len(neighbors))
                    next_frontier = {entity: 0.0 for entity in entity_nodes}
                    for url, mass in article_mass.items():
                        neighbors = [node for node in graph.successors(url) if node in entity_nodes]
                        for entity in neighbors:
                            next_frontier[entity] += mass / max(1, len(neighbors))
                    total = sum(next_frontier.values())
                    if total:
                        next_frontier = {node: value / total for node, value in next_frontier.items()}
                    frontier = {node: alpha * next_frontier.get(node, 0.0) + (1 - alpha) * (1 / len(seeds) if node in seeds else 0.0) for node in entity_nodes} if seeds else next_frontier
                node_scores.update(frontier)
                for entity, mass in frontier.items():
                    neighbors = [url for url in graph.predecessors(entity) if url in article_set]
                    for url in neighbors:
                        scores[url] += mass / max(1, len(neighbors))
                if inputs["query_seed_type"] == "article" and seed_articles:
                    for url in seed_articles:
                        scores[url] += 1.0 / len(seed_articles)
            else:
                for url in seed_articles:
                    scores[url] += 1.0
                related = {entity for url in seed_articles for entity in graph.successors(url) if entity in entity_nodes}
                for entity in related:
                    degree = max(1, len([url for url in graph.predecessors(entity) if url in article_set]))
                    for url in graph.predecessors(entity):
                        if url in article_set and url not in seed_articles:
                            scores[url] += hop_decay / degree
        else:  # bounded short-path evidence: direct seed match plus discounted shared-entity paths
            scores = {url: (1.0 if url in seed_articles else 0.0) for url in results}
            for article in article_nodes:
                if article in seed_articles:
                    continue
                neighbors = [entity for entity in graph.successors(article) if entity in entity_nodes]
                scores[article] += hop_decay * sum(
                    1.0 / max(1, graph.degree(entity))
                    for entity in neighbors
                    if any(other in seed_articles for other in graph.predecessors(entity))
                )

        ranked = sorted(((url, scores.get(url, 0.0)) for url in results), key=lambda row: (-row[1], row[0]))
        elapsed = perf_counter() - tick
        node_scores.update(scores)
        graph_data = self._serialize_graph(
            graph, article_set, prepared.get("node_names", {}), node_scores,
            opposite_count=inputs.get("opposite_count"), hit_scores=hit_scores,
            seeds=seeds, personalization=inputs["personalization"],
            meta={
                "article_count": len(article_nodes), "entity_count": len(entity_nodes),
                "graph_surviving_articles": len(article_nodes), "graph_entity_count": len(entity_nodes),
                "graph_seed_count": len(seeds), "graph_method": method,
                "graph_seconds": elapsed, "seed_method": seed_method,
                "effective_seed_method": inputs["effective_seed_method"],
                "query_entity_count": inputs["query_entity_count"],
                "query_entity_matched_count": inputs["query_entity_matched_count"],
                "query_seed_fallback_reason": inputs["query_seed_fallback_reason"],
                "query_seed_type": inputs["query_seed_type"],
            },
        )
        return ([{"article": url, "score": score} for url, score in ranked], graph_data)
