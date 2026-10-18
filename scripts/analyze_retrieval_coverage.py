"""Read-only coverage funnel and fixed-reference analysis of batch checkpoints."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean

from services.batch_checkpoint import checksum
from relevance_research import database


KS = (1, 3, 5, 10, 20)


def fixed_metrics(ranked, relevant):
    ranked = list(dict.fromkeys(ranked))
    relevant = set(relevant)
    metrics = {}
    for k in KS:
        hits = len(set(ranked[:k]) & relevant)
        p = hits / k
        r = hits / len(relevant) if relevant else 0.0
        metrics[str(k)] = {"hits": hits, "precision": p, "recall": r,
                           "f1": 2 * p * r / (p + r) if p + r else 0.0}
    return metrics


def read_checkpoint(path):
    pools = {}
    rankings = []
    with path.open('rb') as stream:
        size = path.stat().st_size  # A bounded snapshot, even if the run is live.
        header = json.loads(stream.readline())
        if header.get('type') != 'batch':
            raise ValueError(f'{path}: not a batch checkpoint')
        config = header['config']
        items = {item['id']: item for item in config['evaluations']}
        metadata = config['metadata']
        count = 0
        while stream.tell() < size:
            line = stream.readline()
            if stream.tell() > size or not line.endswith(b'\n'):
                break  # Ignore an append that was unfinished at the snapshot boundary.
            record = json.loads(line)
            digest = record.pop('checksum')
            if checksum(record) != digest or record['index'] != count:
                raise ValueError(f'{path}: checksum or sequence mismatch at record {count}')
            count += 1
            item = items[record['task']['id']]
            result = record['result']
            for comparison in result.get('comparisons', [result]):
                row = {**result, **comparison}
                if row.get('stage') == 'lexical':
                    continue  # This audit compares hybrid retrieval across rankings.
                key = (item['id'], row['preset'], row['quorum'], row['limit'], row['top_k'], row['result_unit'], row.get('retrieval_id'))
                urls = list(dict.fromkeys(row['ranked_urls']))
                reference = set(item['relevant_urls'])
                diagnostics = row.get('diagnostics', {})
                pool = pools.setdefault(key, {
                    'id': item['id'], 'query': item['query'], 'theme': item['id'].split('__', 1)[0],
                    'query_formulation': item.get('query_formulation', 'unspecified'),
                    'preset': row['preset'], 'quorum': row['quorum'], 'limit': row['limit'], 'top_k': row['top_k'],
                    'result_unit': row['result_unit'], 'search_window': metadata['search_window'],
                    'relevant_urls': item['relevant_urls'], 'reference_total': len(reference),
                    'lexical_references': diagnostics.get('lexical_reference_in_pool'),
                    'embedding_eligible_references': diagnostics.get('hybrid_eligible_reference_in_pool'),
                    'returned_references': len(reference & set(urls)), 'returned_articles': len(urls),
                    'candidate_cap_hit': diagnostics.get('candidate_cap_hit'),
                    'effective_quorum': diagnostics.get('effective_quorum'),
                    'query_lexeme_count': len(diagnostics.get('query_lexemes', [])),
                    'returned_urls': urls, 'saved_rows': 0,
                })
                if set(urls) != set(pool['returned_urls']):
                    raise ValueError(f'{path}: rankings do not preserve the pool for {item["id"]}')
                # Some seed-independent rows have richer diagnostics than graph rows.
                for target, source in (('lexical_references', 'lexical_reference_in_pool'),
                                       ('embedding_eligible_references', 'hybrid_eligible_reference_in_pool')):
                    if pool[target] is None:
                        pool[target] = diagnostics.get(source)
                pool['saved_rows'] += 1
                rankings.append({
                    'id': item['id'], 'theme': pool['theme'], 'query_formulation': pool['query_formulation'],
                    'preset': row['preset'], 'quorum': row['quorum'],
                    'ranking': row.get('ranking', row['stage']), 'seed_method': row['seed_method'],
                    'prefix_metrics': row['metrics']['metrics'],
                    'fixed_reference_metrics': fixed_metrics(urls, reference),
                    'oracle_fixed_recall_at20': min(20, pool['returned_references']) / len(reference),
                })
    return {'source': str(path), 'saved_records': count, 'expected_evaluations': len(items),
            'evaluations': list(items.values()),
            'metadata': metadata, 'pools': list(pools.values()), 'rankings': rankings}


def audit_database(urls, args):
    with database(args) as conn:
        rows = conn.execute('''SELECT a.url, a.date_published::text AS date,
            count(c.id) AS chunks, count(c.id) FILTER (WHERE c.embedding IS NOT NULL) AS embedded_chunks
            FROM g1_articles a LEFT JOIN g1_chunks c ON c.article = a.url
            WHERE a.url = ANY(%s) GROUP BY a.url, a.date_published''', (list(urls),)).fetchall()
    return {row['url']: row for row in rows}


def enrich(pool, inventory):
    n = pool['reference_total']
    corpus = chunked = None
    if inventory is not None:
        start, end = (pool['search_window'].get(key) for key in ('date_from', 'date_to'))
        eligible = [inventory[url] for url in pool['relevant_urls'] if url in inventory
                    and inventory[url]['date'] is not None
                    and (not start or inventory[url]['date'] >= start)
                    and (not end or inventory[url]['date'] <= end)]
        corpus = len(eligible)
        chunked = sum(row['chunks'] > 0 for row in eligible)
        pool['unavailable_references_now'] = [url for url in pool['relevant_urls'] if url not in {row['url'] for row in eligible}]
        pool['unchunked_references_now'] = [row['url'] for row in eligible if not row['chunks']]
        pool['unembedded_references_now'] = [row['url'] for row in eligible if row['chunks'] and not row['embedded_chunks']]
    lexical, embedded, returned = (pool[key] for key in (
        'lexical_references', 'embedding_eligible_references', 'returned_references'))
    pool['coverage'] = {name: value / n if value is not None else None for name, value in (
        ('corpus_now', corpus), ('chunked_now', chunked), ('capped_lexical', lexical),
        ('embedding_eligible', embedded), ('returned', returned))}
    pool['losses'] = {
        'corpus_or_date_now': n - corpus if corpus is not None else None,
        'no_chunks_now': corpus - chunked if corpus is not None else None,
        'before_capped_lexical': chunked - lexical if chunked is not None and lexical is not None else None,
        'embedding_filter': lexical - embedded if lexical is not None and embedded is not None else None,
        'returned_window': embedded - returned if embedded is not None else None,
    }
    pool['inconsistent_funnel'] = any(value is not None and value < 0 for value in pool['losses'].values())


def aggregate_pools(pools, field):
    groups = defaultdict(list)
    for pool in pools:
        groups[pool[field]].append(pool)
    result = []
    for label, entries in groups.items():
        coverage, losses = {}, {}
        for target, name in ((coverage, 'coverage'), (losses, 'losses')):
            for key in entries[0][name]:
                values = [entry[name][key] for entry in entries if entry[name][key] is not None]
                target[key] = mean(values) if values else None
        result.append({'group': label, 'retrieval_pools': len(entries), 'coverage': coverage, 'mean_reference_losses': losses,
                       'candidate_cap_hits': sum(entry['candidate_cap_hit'] is True for entry in entries),
                       'inconsistent_funnels': sum(entry['inconsistent_funnel'] for entry in entries)})
    return sorted(result, key=lambda row: row['coverage']['returned'])


def matched_depths(runs):
    # Use only queries observed at every depth, with the same reference order,
    # date window, quorum, and result unit. Do not overweight repeated runs.
    cases = defaultdict(lambda: defaultdict(set))
    themes = {}
    depths = set()
    for run in runs:
        for pool in run['pools']:
            key = (pool['id'], pool['query'], tuple(pool['relevant_urls']), pool['quorum'],
                   json.dumps(pool['search_window'], sort_keys=True), pool['result_unit'])
            depth = (pool['top_k'], pool['limit'])
            cases[key][depth].add(pool['coverage']['returned'])
            themes[key] = pool['theme']
            depths.add(depth)
    if len(depths) < 2:
        return {'matched_cases': 0, 'rows': []}
    matched = [key for key, values in cases.items() if all(depth in values and len(values[depth]) == 1 for depth in depths)]
    rows = []
    for label in ['ALL'] + sorted({themes[key] for key in matched}):
        keys = [key for key in matched if label == 'ALL' or themes[key] == label]
        for top_k, limit in sorted(depths):
            values = [next(iter(cases[key][(top_k, limit)])) for key in keys]
            if values:
                rows.append({'theme': label, 'top_k': top_k, 'limit': limit, 'matched_cases': len(keys),
                             'mean_returned_reference_recall': mean(values)})
    distinct_limits = {pool['limit'] for run in runs for pool in run['pools']}
    isolates_top_k = len(distinct_limits) <= 1
    return {'matched_cases': len(matched), 'rows': rows,
            'note': ('HNSW limit is fixed across top_k values.' if isolates_top_k else
                     'top_k and HNSW limit vary together in at least one run; their effects are confounded.') +
                    ' Conflicting repeated observations are excluded.'}


def markdown(report):
    lines = ['# Diagnóstico de cobertura da recuperação', '',
             f"Gerado em {report['generated_at']}. Somente leitura; nenhuma busca ou alteração de referência foi feita.", '',
             'Contagens de recuperação usam pools únicos, não as linhas repetidas de rankings/seeds. '
             'O oráculo não é uma medida de relevância humana: é a cobertura da referência no pool retornado.', '',
             '**Limites:** lexical significa o conjunto já limitado pelo candidate cap. Uma perda nessa etapa pode vir de quorum, '
             'matching ou cap — este relatório não os separa. Inventário do banco é atual e pode diferir do momento da avaliação. '
             'Os percentuais de cobertura usam todos os positivos fixos; não os prefixos editoriais. Resultados parciais têm cobertura desigual.', '']
    def pct(value):
        return '—' if value is None else f'{value:.1%}'
    for run in report['runs']:
        lines += [f"## {run['source']}", '',
                  f"Registros salvos: {run['saved_records']}; pools: {len(run['pools'])}; consultas observadas: {len({p['id'] for p in run['pools']})}/{run['expected_evaluations']}.", '']
        for title, field in [('Por tema', 'theme'), ('Por estrutura de consulta', 'query_formulation')]:
            lines += [f'### {title}', '',
                      '| Grupo | Pools | Corpus atual | Com chunks | Lexical limitado | Com embedding | Retornado | Cap atingido |',
                      '|---|---:|---:|---:|---:|---:|---:|---:|']
            for row in run['aggregates'][field]:
                coverage = row['coverage']
                lines.append(f"| {row['group']} | {row['retrieval_pools']} | " + ' | '.join(pct(coverage[key]) for key in (
                    'corpus_now', 'chunked_now', 'capped_lexical', 'embedding_eligible', 'returned')) + f" | {row['candidate_cap_hits']} |")
            lines.append('')
        lines += ['### Ranking com referência fixa', '',
                  'Média por linha salva; seeds repetidas permanecem na grade. Não altera os resultados originais.', '',
                  '| Ranking | Linhas | P@5 fixo | R@5 fixo | F1@5 fixo | F1@20 fixo | R@20 oráculo fixo |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for row in run['ranking_aggregates']:
            lines.append(f"| {row['ranking']} | {row['rows']} | " + ' | '.join(pct(row[key]) for key in (
                'fixed_precision_at5', 'fixed_recall_at5', 'fixed_f1_at5', 'fixed_f1_at20', 'oracle_fixed_recall_at20')) + ' |')
        lines.append('')
    lines += ['## Comparação pareada dos presets existentes', '',
              f"Consultas comparáveis em todos os presets: {report['matched_depth_comparison']['matched_cases']}.", '',
              f"{report['matched_depth_comparison']['note']} "
              'Temas presentes só no lote definitivo não entram na comparação se não tiverem os outros presets.', '',
              '| Tema | top_k | limit | Consultas pareadas | Cobertura retornada |',
              '|---|---:|---:|---:|---:|']
    for row in report['matched_depth_comparison']['rows']:
        lines.append(f"| {row['theme']} | {row['top_k']} | {row['limit']} | {row['matched_cases']} | {pct(row['mean_returned_reference_recall'])} |")
    lines += ['', '## Implementação RRF e alcance deste diagnóstico', '',
              '- A auditoria encontrou que o serviço descartava os ranks vetoriais de cada linha; por isso, RRF substituía o canal vetorial pelo próprio híbrido. Também ordenava ranks lexicais em direção descendente, embora rank 1 seja o melhor.',
              '- Corrigido em `stages_v3`/cache `v13`: preserva o melhor rank de chunk por artigo, ordena os dois canais com menor rank primeiro e não substitui um canal ausente pelo híbrido. O oráculo de cobertura não é afetado por essa correção.',
              '- Os resultados RRF anteriores (por exemplo, `eval_stages_v5`) vieram da implementação anterior e não devem ser usados para concluir que RRF funciona melhor ou pior. O piloto deste relatório testa `hybrid_max`, não é uma reavaliação RRF; a API atual passou por smoke test e os testes focados passaram.',
              '- O quorum é aplicado a lexemas de cada chunk, não à união dos termos no artigo inteiro. Consultas longas podem exigir uma combinação de termos que nenhum chunk relevante contém.', '']
    if report.get('pilot'):
        lines += ['## Piloto proposto', '',
                  f"Arquivo: `{report['pilot']['file']}`; {report['pilot']['evaluations']} consultas.", '',
                  'Amostra diagnóstica dos quatro temas de baixa cobertura: Banco Master, metanol, tarifaço e núcleo crucial. '
                  'Inclui keyword, broad_theme, specific_question e information_request. '
                  'Não é um conjunto de teste cego nem evidência independente para a avaliação final.', '',
                  'Execute com `--rankings hybrid_max --seed-methods hits --presets rapido balanceado profundo --quorums 0.3 0.7 --result-unit articles`. '
                  'São 96 grupos de recuperação, sem grafo ou reranker. O seed é só um placeholder e não afeta hybrid_max. '
                  'Compare principalmente as coberturas lexical e retornada; não escolha referências novas com base nos resultados.', '']
    return '\n'.join(lines) + '\n'


def pilot_document(runs):
    themes = {'banco_master', 'metanol_bebidas', 'tarifaco_eua_brasil', 'julgamento_nucleo_golpe'}
    styles = {'keyword', 'broad_theme', 'specific_question', 'information_request'}
    selected = {}
    for run in runs:
        for item in run['evaluations']:
            if item['id'].split('__', 1)[0] in themes and item.get('query_formulation') in styles:
                selected[item['id']] = item
    if len(selected) != 16:
        raise ValueError('The pilot requires all four selected themes and query structures in the checkpoint inputs')
    document = {'schema_version': 1, 'evaluations': sorted(selected.values(), key=lambda item: (item['query_formulation'], item['id']))}
    from services.batch_evaluation import validate_document
    validate_document(document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, nargs='+', required=True, help='Batch JSONL checkpoints, including live runs.')
    parser.add_argument('--output', type=Path, required=True, help='New report JSON path; Markdown is written beside it.')
    parser.add_argument('--audit-db', action='store_true', help='Also inventory reference articles/chunks with read-only SQL.')
    parser.add_argument('--pilot-output', type=Path, help='Optionally create a 16-query diagnostic pilot input, without running searches.')
    parser.add_argument('--env-file', type=Path, default=Path(__file__).resolve().parents[1] / '.env')
    parser.add_argument('--timeout-ms', type=int, default=60000)
    args = parser.parse_args()
    paths = (args.output, args.output.with_suffix('.md'))
    if any(path.exists() for path in paths) or (args.pilot_output and args.pilot_output.exists()):
        raise FileExistsError('Choose new output paths; existing reports will not be overwritten')
    runs = [read_checkpoint(path) for path in args.inputs]
    urls = {url for run in runs for pool in run['pools'] for url in pool['relevant_urls']}
    inventory = audit_database(urls, args) if args.audit_db else None
    for run in runs:
        for pool in run['pools']:
            enrich(pool, inventory)
        run['aggregates'] = {field: aggregate_pools(run['pools'], field) for field in ('theme', 'query_formulation')}
        rankings = defaultdict(list)
        for row in run['rankings']:
            rankings[row['ranking']].append(row)
        run['ranking_aggregates'] = sorted([{
            'ranking': ranking, 'rows': len(entries),
            'fixed_precision_at5': mean(row['fixed_reference_metrics']['5']['precision'] for row in entries),
            'fixed_recall_at5': mean(row['fixed_reference_metrics']['5']['recall'] for row in entries),
            'fixed_f1_at5': mean(row['fixed_reference_metrics']['5']['f1'] for row in entries),
            'fixed_f1_at20': mean(row['fixed_reference_metrics']['20']['f1'] for row in entries),
            'oracle_fixed_recall_at20': mean(row['oracle_fixed_recall_at20'] for row in entries),
        } for ranking, entries in rankings.items()], key=lambda row: -row['fixed_f1_at20'])
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'inventory_now': inventory,
              'runs': runs, 'matched_depth_comparison': matched_depths(runs)}
    pilot = pilot_document(runs) if args.pilot_output else None
    if pilot:
        report['pilot'] = {'file': str(args.pilot_output), 'evaluations': len(pilot['evaluations'])}
    for path, content in ((paths[0], json.dumps(report, ensure_ascii=False, indent=2) + '\n'),
                          (paths[1], markdown(report))):
        with path.open('x', encoding='utf-8') as stream:
            stream.write(content)
        print(path)
    if pilot:
        with args.pilot_output.open('x', encoding='utf-8') as stream:
            json.dump(pilot, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(args.pilot_output)


if __name__ == '__main__':
    main()
