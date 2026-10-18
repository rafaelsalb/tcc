import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('relevance_research', SCRIPTS / 'relevance_research.py')
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)
sys.modules.setdefault('relevance_research', research)
spec = importlib.util.spec_from_file_location('analyze_retrieval_coverage', SCRIPTS / 'analyze_retrieval_coverage.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_fixed_reference_metrics_use_all_positives_and_deduplicate():
    metrics = analysis.fixed_metrics(['e', 'e', 'a', 'c'], ['a', 'b', 'c', 'd', 'e'])
    assert metrics['1']['precision'] == 1
    assert metrics['1']['recall'] == 0.2
    assert metrics['3']['hits'] == 3
    assert metrics['5']['precision'] == metrics['5']['recall'] == 0.6


def pool(id='theme__keyword', top_k=100, limit=250):
    return {'id': id, 'theme': id.split('__')[0], 'query': 'query', 'query_formulation': 'keyword',
            'relevant_urls': ['a', 'b', 'c', 'd'], 'reference_total': 4,
            'lexical_references': 3, 'embedding_eligible_references': 2, 'returned_references': 1,
            'search_window': {'date_from': '2025-06-01', 'date_to': '2026-06-30'},
            'top_k': top_k, 'limit': limit, 'quorum': 0.7, 'result_unit': 'articles',
            'candidate_cap_hit': False}


def test_funnel_inventory_distinguishes_missing_chunk_and_embedding():
    row = pool()
    inventory = {u: {'url': u, 'date': '2025-07-01', 'chunks': 1, 'embedded_chunks': 1} for u in 'abcd'}
    analysis.enrich(row, inventory)
    assert row['coverage'] == {'corpus_now': 1, 'chunked_now': 1, 'capped_lexical': .75,
                               'embedding_eligible': .5, 'returned': .25}
    assert row['losses']['before_capped_lexical'] == row['losses']['embedding_filter'] == row['losses']['returned_window'] == 1
    assert row['inconsistent_funnel'] is False


def test_missing_inventory_is_not_reported_as_zero():
    row = pool()
    analysis.enrich(row, None)
    assert row['coverage']['corpus_now'] is None
    assert row['losses']['before_capped_lexical'] is None


def test_depth_comparison_uses_only_matched_cases_and_deduplicates_runs():
    first, second, unmatched = pool(), pool(top_k=400, limit=1000), pool('other__keyword')
    for row in (first, second, unmatched):
        analysis.enrich(row, None)
    second['coverage']['returned'] = .75
    report = analysis.matched_depths([{'pools': [first, unmatched]}, {'pools': [first, second]}])
    assert report['matched_cases'] == 1
    all_rows = [row for row in report['rows'] if row['theme'] == 'ALL']
    assert [r['mean_returned_reference_recall'] for r in all_rows] == [.25, .75]


def test_live_checkpoint_ignores_partial_tail_and_counts_pool_only_once(tmp_path):
    from services.batch_checkpoint import canonical_json, checksum

    path = tmp_path / 'run.jsonl'
    item = {'id': 'theme__keyword', 'query': 'query', 'relevant_urls': ['a', 'b'], 'query_formulation': 'keyword'}
    header = {'type': 'batch', 'config': {'evaluations': [item], 'metadata': {'search_window': {}}}}
    lines = [json.dumps(header)]
    for i, ranking in enumerate(['ppr', 'fused']):
        result = {'stage': 'ppr', 'ranking': ranking, 'seed_method': 'hits', 'preset': 'rapido', 'limit': 250,
                  'top_k': 100, 'quorum': .7, 'result_unit': 'articles', 'retrieval_id': 'pool',
                  'ranked_urls': ['a', 'c'], 'diagnostics': {'lexical_reference_in_pool': 2,
                  'hybrid_eligible_reference_in_pool': 2}, 'metrics': {'metrics': []}}
        record = {'type': 'result', 'index': i, 'task': {'id': item['id']}, 'result': result}
        record['checksum'] = checksum(record)
        lines.append(canonical_json(record))
    path.write_text('\n'.join(lines) + '\n{"incomplete":')
    report = analysis.read_checkpoint(path)
    assert report['saved_records'] == 2
    assert len(report['rankings']) == 2 and len(report['pools']) == 1
    assert report['pools'][0]['saved_rows'] == 2


def test_corrupt_checkpoint_is_rejected(tmp_path):
    path = tmp_path / 'run.jsonl'
    path.write_text(json.dumps({'type': 'batch', 'config': {'evaluations': [], 'metadata': {}}}) + '\n' +
                    json.dumps({'index': 0, 'checksum': 'invalid'}) + '\n')
    with pytest.raises(ValueError, match='checksum'):
        analysis.read_checkpoint(path)
