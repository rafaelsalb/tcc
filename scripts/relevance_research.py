"""Pesquisa editorial de relevância no G1, independente da aplicação RAG."""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PATTERNS = Path(__file__).with_name('relevance_patterns.json')
ARTICLE_COLUMNS = '''url, final_url, title, date_published::text AS date,
    text_content AS body, fetched_at::text, extracted_at::text,
    sitemap_article_lastmod'''
PRIORITY_WORDS = (
    'entenda', 'o que se sabe', 'o que sabemos', 'cronologia', 'linha do tempo',
    'condena', 'liquida', 'relatório', 'indicia', 'ressarc', 'acordo', 'anula',
    'morre', 'morte', 'resgat', 'resultado', 'termina',
)


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value, force=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w' if force else 'x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use uma data ISO: AAAA-MM-DD') from exc


@contextmanager
def database(args):
    # Imports tardios: revisão de snapshots e importação do relatório são offline.
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(args.env_file)
    dsn = os.getenv('POSTGRES_DSN')
    if not dsn:
        raise ValueError('Defina POSTGRES_DSN no ambiente ou no arquivo .env.')
    for scheme in ('postgresql+psycopg2://', 'postgresql+psycopg://'):
        if dsn.startswith(scheme):
            dsn = 'postgresql://' + dsn[len(scheme):]
            break
    # Opções na conexão e SET TRANSACTION protegem todas as consultas desta sessão.
    with psycopg.connect(
        dsn, connect_timeout=10,
        options=f'-c default_transaction_read_only=on -c statement_timeout={args.timeout_ms}',
        row_factory=psycopg.rows.dict_row,
    ) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        yield conn


def corpus_stats(conn, start, end):
    totals = conn.execute('''SELECT count(*) AS total,
        min(date_published)::text AS first_date,
        max(date_published)::text AS last_date,
        count(*) FILTER (WHERE nullif(btrim(title), '') IS NOT NULL) AS with_title,
        count(*) FILTER (WHERE nullif(btrim(text_content), '') IS NOT NULL) AS with_body
        FROM g1_articles WHERE date_published BETWEEN %s AND %s''', (start, end)).fetchone()
    monthly = conn.execute('''SELECT date_trunc('month', date_published)::date::text AS month,
        count(*) AS total,
        count(*) FILTER (WHERE nullif(btrim(text_content), '') IS NOT NULL) AS with_body
        FROM g1_articles WHERE date_published BETWEEN %s AND %s
        GROUP BY 1 ORDER BY 1''', (start, end)).fetchall()
    return {'totals': totals, 'monthly': monthly}


def candidate_rows(path):
    value = load_json(path)
    # Também aceita os arrays dos scripts temporários usados na pesquisa original.
    return value if isinstance(value, list) else value['articles']


def snapshot_hash(rows):
    payload = '\n'.join(
        json.dumps(
            {key: row[key] for key in ('url', 'title', 'date', 'body')},
            ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        )
        for row in sorted(rows, key=lambda row: row['url'])
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def review_passages(body, lead_chars=1250, extra_chars=750):
    """Heurística original de leitura dirigida; NÃO classifica relevância."""
    body = body or ''
    later = []
    offset = 0
    for paragraph in (p.strip() for p in body.split('\n') if p.strip()):
        start = body.find(paragraph, offset)
        offset = start + len(paragraph)
        if start < lead_chars or not 95 <= len(paragraph) <= 700:
            continue
        if re.search(r'LEIA|Veja também|Saiba mais|ASSISTA|vídeos|Confira', paragraph, re.I):
            continue
        if re.search(
            r'investiga|fraud|bilh|milh|confirm|polícia|Federal|determ|conclu|apont|'
            r'perícia|depoimento|adrenalin|morte|tarifa|ressarc|descont', paragraph, re.I,
        ):
            later.append(paragraph)
    return body[:lead_chars], '\n'.join(later[:2])[:extra_chars]


def import_report(path):
    """Importa o formato do relatório original, preservando decisões editoriais."""
    text = Path(path).read_text(encoding='utf-8')
    names = dict(re.findall(r'^## \d+\. Caso (\w+) — (.+)$', text, re.M))
    hashes = dict(re.findall(r'^\| ([A-Z]+) \| `([a-f0-9]{64})` \|$', text, re.M))
    sections = re.findall(
        r'^### ([A-Z]+)(\d{2,}) — Relevância (\d+)\n(.*?)'
        r'(?=^### |^\*\*Exclusões|^## |\Z)', text, re.M | re.S,
    )
    themes = {}
    for prefix, number, rank, section in sections:
        if int(number) != int(rank):
            raise ValueError(f'{prefix}{number}: ID e relevância divergentes.')
        metadata = re.search(
            r'\*\*(\d{4}-\d\d-\d\d) — \[(.*?)\]\((https://[^\s)]+)\)\*\*', section,
        )
        rationale = re.search(r'\*\*Motivo:\*\* (.+)', section)
        evidence = re.search(r'\*\*Evidência no corpo:\*\* “(.*?)”(.*)', section)
        if not all((metadata, rationale, evidence)):
            raise ValueError(f'{prefix}{number}: entrada incompleta no relatório.')
        published, title, url = metadata.groups()
        theme = themes.setdefault(prefix, {
            'id': prefix, 'name': names.get(prefix, prefix), 'articles': [],
        })
        if prefix in hashes:
            theme['snapshot_sha256'] = hashes[prefix]
        theme['articles'].append({
            'rank': int(rank), 'url': url, 'date': published, 'title': title,
            'rationale': rationale.group(1), 'evidence': evidence.group(1),
            'notes': evidence.group(2).strip(),
        })
    if not themes:
        raise ValueError('Nenhuma entrada reconhecida; consulte o formato documentado.')
    return {'version': 1, 'source_report': str(path), 'themes': list(themes.values())}


def validate_selection(selection, by_url, start, end, expected_count=None):
    errors, warnings, summaries = [], [], []
    seen_themes = set()
    for theme in selection['themes']:
        key = theme['id']
        if key in seen_themes:
            errors.append(f'Tema duplicado: {key}')
        seen_themes.add(key)
        articles = theme['articles']
        if not articles:
            errors.append(f'{key}: lista vazia')
        if expected_count is not None and len(articles) != expected_count:
            errors.append(f'{key}: esperado(s) {expected_count}, encontrado(s) {len(articles)}')
        seen_urls, seen_bodies, matched = set(), set(), []
        for position, judgment in enumerate(articles, 1):
            label = f'{key}{position:02d}'
            url = judgment['url']
            if judgment['rank'] != position:
                errors.append(f'{label}: ranks devem ser consecutivos, na ordem da lista')
            if url in seen_urls:
                errors.append(f'{label}: URL repetida dentro do tema')
            seen_urls.add(url)
            row = by_url.get(url)
            if row is None:
                errors.append(f'{label}: URL ausente da fonte')
                continue
            matched.append(row)
            if not row.get('date') or not start.isoformat() <= row['date'] <= end.isoformat():
                errors.append(f'{label}: publicação fora da janela ou sem data')
            if judgment['date'] != row.get('date'):
                errors.append(f'{label}: data divergente')
            title = (row.get('title') or '').removesuffix(' | G1')
            if judgment['title'].removesuffix(' | G1') != title:
                errors.append(f'{label}: título divergente')
            body = row.get('body') or ''
            if not body.strip():
                errors.append(f'{label}: corpo vazio')
            if not judgment.get('evidence') or judgment['evidence'] not in body:
                errors.append(f'{label}: evidência ausente ou não literal no corpo')
            if not judgment.get('rationale', '').strip():
                errors.append(f'{label}: falta justificativa editorial')
            digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
            if digest in seen_bodies:
                errors.append(f'{label}: corpo idêntico a outro artigo do tema')
            seen_bodies.add(digest)
            for field in ('fetched_at', 'sitemap_article_lastmod'):
                value = row.get(field)
                if not value:
                    warnings.append(f'{label}: {field} ausente; versão temporal não comprovada')
                else:
                    try:
                        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        if timestamp.date() > end:
                            warnings.append(f'{label}: {field} posterior ao corte (verificar atualização)')
                    except ValueError:
                        warnings.append(f'{label}: {field} não é data ISO reconhecida')
        digest = snapshot_hash(matched) if len(matched) == len(articles) else None
        if theme.get('snapshot_sha256') and digest != theme['snapshot_sha256']:
            errors.append(f'{key}: hash do snapshot diverge da referência arquivada')
        summaries.append({
            'theme': key, 'articles': len(articles),
            'snapshot_sha256': digest,
            'sets': {str(k): [a['url'] for a in articles[:k]]
                     for k in (1, 3, 5, 10, 20) if len(articles) >= k},
        })
    if not selection['themes']:
        errors.append('Seleção sem temas')
    return {'valid': not errors, 'errors': errors, 'warnings': warnings, 'themes': summaries}


def chosen_rows(args):
    rows = candidate_rows(args.candidates)
    if args.indices is not None:
        if any(i < 0 or i >= len(rows) for i in args.indices):
            raise ValueError('Índice fora do snapshot; use titles para consultar os índices.')
        return [rows[i] for i in args.indices]
    if args.selection:
        themes = load_json(args.selection)['themes']
        theme = next((t for t in themes if t['id'] == args.theme), None)
        if theme is None:
            raise ValueError('Informe --theme com um ID presente na seleção.')
        urls = [a['url'] for a in theme['articles']]
    else:
        urls = args.urls
    by_url = {row['url']: row for row in rows}
    missing = [url for url in urls if url not in by_url]
    if missing:
        raise ValueError(f'{len(missing)} URL(s) ausente(s) do snapshot.')
    return [by_url[url] for url in urls]


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('O valor deve ser positivo.')
    return number


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=REPO / '.env')
    parser.add_argument('--start', type=parse_date, default=date(2025, 6, 1))
    parser.add_argument('--end', type=parse_date, default=date(2026, 5, 20))
    parser.add_argument('--timeout-ms', type=positive, default=60000)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('stats', help='Estatísticas do corpus, em JSON (banco)')
    sample = sub.add_parser('sample', help='Amostra determinística de títulos (banco)')
    sample.add_argument('--limit', type=positive, default=850)
    discover = sub.add_parser('discover', help='Exporta candidatos por regex (banco)')
    discover.add_argument('--patterns', type=Path, default=DEFAULT_PATTERNS)
    discover.add_argument('--theme', action='append', help='Chave do padrão; repetível')
    discover.add_argument('--output-dir', type=Path, required=True)
    discover.add_argument('--preview', type=positive, default=65)
    discover.add_argument('--force', action='store_true')
    titles = sub.add_parser('titles', help='Lista títulos de um snapshot (offline)')
    titles.add_argument('candidates', type=Path)
    titles.add_argument('--offset', type=int, default=0)
    titles.add_argument('--limit', type=positive, default=65)
    for name, help_text in [('bodies', 'Corpos completos'), ('review', 'Leitura dirigida, não exaustiva')]:
        body = sub.add_parser(name, help=f'{help_text} (offline)')
        body.add_argument('candidates', type=Path)
        choice = body.add_mutually_exclusive_group(required=True)
        choice.add_argument('--indices', type=int, nargs='+')
        choice.add_argument('--urls', nargs='+')
        choice.add_argument('--selection', type=Path)
        body.add_argument('--theme', help='ID do tema na seleção editorial')
    importer = sub.add_parser('import-report', help='Converte julgamentos do Markdown para JSON (offline)')
    importer.add_argument('report', type=Path)
    importer.add_argument('--output', type=Path, required=True)
    importer.add_argument('--force', action='store_true')
    validate = sub.add_parser('validate', help='Confere julgamentos; não decide relevância')
    source = validate.add_mutually_exclusive_group(required=True)
    source.add_argument('--selection', type=Path)
    source.add_argument('--report', type=Path)
    validate.add_argument('--snapshots', type=Path, nargs='+', help='JSONs locais; sem isto consulta o banco')
    validate.add_argument('--expected-count', type=positive)
    return parser


def run(args):
    if args.start > args.end:
        raise ValueError('--start deve ser anterior ou igual a --end.')
    if args.command == 'import-report':
        selection = import_report(args.report)
        write_json(args.output, selection, args.force)
        print(f'{len(selection["themes"])} temas importados em {args.output}')
    elif args.command == 'titles':
        if args.offset < 0:
            raise ValueError('--offset não pode ser negativo.')
        rows = candidate_rows(args.candidates)
        for i in range(args.offset, min(args.offset + args.limit, len(rows))):
            print(f'{i:4} {rows[i]["date"]} {rows[i]["title"]}\n     {rows[i]["url"]}')
    elif args.command in ('bodies', 'review'):
        for position, row in enumerate(chosen_rows(args), 1):
            body = row.get('body') or ''
            print(f'\n### {position} | {row["date"]} | {row["title"]}\n{row["url"]}\nBODY ({len(body)} caracteres):')
            if args.command == 'bodies':
                print(body)
            else:
                lead, extra = review_passages(body)
                print(f'INÍCIO:\n{lead}\nPASSAGENS POSTERIORES:\n{extra}\n[Leitura parcial; use bodies para o texto completo.]')
    elif args.command == 'validate':
        selection = import_report(args.report) if args.report else load_json(args.selection)
        urls = list({a['url'] for t in selection['themes'] for a in t['articles']})
        if args.snapshots:
            by_url = {}
            for path in args.snapshots:
                for row in candidate_rows(path):
                    if row['url'] in by_url and row != by_url[row['url']]:
                        raise ValueError('Snapshots divergentes para a mesma URL; escolha uma versão.')
                    by_url[row['url']] = row
        else:
            with database(args) as conn:
                rows = conn.execute(f'SELECT {ARTICLE_COLUMNS} FROM g1_articles WHERE url = ANY(%s)', (urls,)).fetchall()
            by_url = {row['url']: row for row in rows}
        result = validate_selection(selection, by_url, args.start, args.end, args.expected_count)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['valid'] else 1
    else:
        if args.command == 'discover':
            patterns = load_json(args.patterns)
            if not isinstance(patterns, dict) or not patterns:
                raise ValueError('O arquivo de padrões deve ser um objeto JSON não vazio.')
            keys = args.theme or list(patterns)
            for key in keys:
                if not re.fullmatch(r'[a-zA-Z0-9_-]+', key) or key not in patterns:
                    raise ValueError(f'Chave de tema inválida: {key}')
                if not isinstance(patterns[key], str) or not patterns[key]:
                    raise ValueError(f'{key}: padrão deve ser texto não vazio.')
                if (args.output_dir / f'{key}.json').exists() and not args.force:
                    raise FileExistsError(f'{key}.json já existe; use outro diretório ou --force.')
        with database(args) as conn:
            if args.command == 'stats':
                print(json.dumps(corpus_stats(conn, args.start, args.end), ensure_ascii=False, indent=2))
            elif args.command == 'sample':
                rows = conn.execute('''SELECT date_published::text AS date, title, url
                    FROM g1_articles WHERE date_published BETWEEN %s AND %s
                    ORDER BY md5(url), url LIMIT %s''', (args.start, args.end, args.limit)).fetchall()
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                for key in keys:
                    rows = conn.execute(f'''SELECT {ARTICLE_COLUMNS} FROM g1_articles
                        WHERE date_published BETWEEN %s AND %s AND title ~* %s
                        ORDER BY date_published, url''', (args.start, args.end, patterns[key])).fetchall()
                    write_json(args.output_dir / f'{key}.json', {
                        'version': 1, 'theme': key, 'pattern': patterns[key],
                        'start': args.start.isoformat(), 'end': args.end.isoformat(),
                        'exported_at': datetime.now(timezone.utc).isoformat(), 'articles': rows,
                    }, args.force)
                    print(f'\n### {key}: {len(rows)} candidatos (não são julgamentos positivos)')
                    ordered = sorted(enumerate(rows), key=lambda pair: (
                        not any(word in (pair[1]['title'] or '').lower() for word in PRIORITY_WORDS),
                        pair[1]['date'], pair[1]['url'],
                    ))
                    for i, row in ordered[:args.preview]:
                        print(f'{i:4} {row["date"]} {row["title"]}')
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Erro: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        # Erros de conexão podem conter host/usuário/DSN: nunca imprimir sua mensagem.
        import psycopg
        if isinstance(exc, psycopg.Error):
            print(f'Erro PostgreSQL ({type(exc).__name__}); confira conexão, regex e timeout. DSN omitido.', file=sys.stderr)
            return 1
        raise


if __name__ == '__main__':
    sys.exit(main())
