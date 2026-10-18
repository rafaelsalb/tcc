"""Verificações offline do utilitário, sem importar a aplicação."""

import copy
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'relevance_research.py'
SPEC = importlib.util.spec_from_file_location('relevance_research', SCRIPT)
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2025, 6, 1)
        self.end = date(2026, 5, 20)
        self.row = {
            'url': 'https://example.test/article', 'title': 'Uma história | G1',
            'date': '2025-06-01', 'body': 'Um fato central. Contexto adicional.',
            'fetched_at': '2026-05-06 13:54:19+00',
            'sitemap_article_lastmod': '2026-05-06T13:00:00Z',
        }
        self.selection = {'version': 1, 'themes': [{
            'id': 'X', 'name': 'Uma história', 'articles': [{
                'rank': 1, 'url': self.row['url'], 'date': self.row['date'],
                'title': 'Uma história', 'rationale': 'Explica o acontecimento.',
                'evidence': 'Um fato central.', 'notes': '',
            }],
        }]}

    def validate(self, selection=None, row=None, count=None):
        row = self.row if row is None else row
        return research.validate_selection(
            self.selection if selection is None else selection,
            {row['url']: row}, self.start, self.end, count,
        )

    def test_valid_selection_and_prefix(self):
        result = self.validate(count=1)
        self.assertTrue(result['valid'])
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['themes'][0]['sets'], {'1': [self.row['url']]})

    def test_inclusive_date_boundaries(self):
        for boundary in (self.start, self.end):
            row = dict(self.row, date=boundary.isoformat())
            selection = copy.deepcopy(self.selection)
            selection['themes'][0]['articles'][0]['date'] = row['date']
            self.assertTrue(self.validate(selection, row)['valid'])

    def test_out_of_range(self):
        row = dict(self.row, date='2025-05-31')
        self.assertFalse(self.validate(row=row)['valid'])

    def test_wrong_title_date_evidence_rank_and_count(self):
        for field, value in [('title', 'Outro'), ('date', '2025-06-02'),
                             ('evidence', 'um fato central.'), ('rank', 2),
                             ('rationale', '')]:
            with self.subTest(field=field):
                selection = copy.deepcopy(self.selection)
                selection['themes'][0]['articles'][0][field] = value
                self.assertFalse(self.validate(selection)['valid'])
        self.assertFalse(self.validate(count=20)['valid'])

    def test_missing_url_and_empty_themes(self):
        result = research.validate_selection(self.selection, {}, self.start, self.end)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['themes'][0]['snapshot_sha256'])
        self.assertFalse(research.validate_selection(
            {'themes': []}, {}, self.start, self.end,
        )['valid'])

    def test_duplicate_url_or_body_within_theme(self):
        selection = copy.deepcopy(self.selection)
        second = dict(selection['themes'][0]['articles'][0], rank=2)
        selection['themes'][0]['articles'].append(second)
        self.assertFalse(self.validate(selection)['valid'])
        second['url'] = 'https://example.test/duplicate-body'
        rows = {self.row['url']: self.row, second['url']: dict(self.row, url=second['url'])}
        result = research.validate_selection(selection, rows, self.start, self.end)
        self.assertTrue(any('corpo idêntico' in error for error in result['errors']))

    def test_cross_theme_url_is_allowed(self):
        selection = copy.deepcopy(self.selection)
        other = copy.deepcopy(selection['themes'][0])
        other['id'] = 'Y'
        selection['themes'].append(other)
        self.assertTrue(self.validate(selection)['valid'])

    def test_temporal_warnings_are_not_relevance_errors(self):
        for field, value in [('fetched_at', '2026-05-21T00:00:00Z'),
                             ('fetched_at', None),
                             ('sitemap_article_lastmod', 'not-a-date')]:
            with self.subTest(field=field, value=value):
                result = self.validate(row=dict(self.row, **{field: value}))
                self.assertTrue(result['valid'])
                self.assertTrue(result['warnings'])

    def test_snapshot_hash_matches_documented_serialization(self):
        serial = json.dumps(
            {k: self.row[k] for k in ['url', 'title', 'date', 'body']},
            ensure_ascii=False, sort_keys=True, separators=(',', ':'),
        )
        self.assertEqual(research.snapshot_hash([self.row]), hashlib.sha256(serial.encode()).hexdigest())
        changed = dict(self.row, body=self.row['body'] + ' Nova informação.')
        self.assertNotEqual(research.snapshot_hash([self.row]), research.snapshot_hash([changed]))

    def test_archived_hash_detects_changes_outside_evidence(self):
        selection = copy.deepcopy(self.selection)
        selection['themes'][0]['snapshot_sha256'] = research.snapshot_hash([self.row])
        self.assertTrue(self.validate(selection)['valid'])
        changed = dict(self.row, body=self.row['body'] + ' Nova informação.')
        result = self.validate(selection, changed)
        self.assertFalse(result['valid'])
        self.assertTrue(any('hash do snapshot' in error for error in result['errors']))

    def test_passage_review_is_partial_and_bounded(self):
        later = 'A polícia investiga a origem do problema. ' * 4
        body = 'x' * 1300 + '\n' + later + '\n' + 'Veja também: ' + later
        lead, extra = research.review_passages(body)
        self.assertEqual(len(lead), 1250)
        self.assertIn(later.strip(), extra)
        self.assertNotIn('Veja também', extra)
        self.assertLessEqual(len(extra), 750)
        self.assertEqual(research.review_passages(None), ('', ''))

    def test_json_no_overwrite_and_legacy_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'snapshot.json'
            research.write_json(path, [self.row])
            self.assertEqual(research.candidate_rows(path), [self.row])
            with self.assertRaises(FileExistsError):
                research.write_json(path, [])
            research.write_json(path, {'articles': [self.row]}, force=True)
            self.assertEqual(research.candidate_rows(path), [self.row])

    def test_import_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.md'
            path.write_text(
                '## 4. Caso X — Uma história\n\n'
                '### X01 — Relevância 1\n'
                '- **2025-06-01 — [Uma história](https://example.test/article)**\n'
                '- **Motivo:** Explica o acontecimento.\n'
                '- **Evidência no corpo:** “Um fato central.” Nota histórica.\n\n'
                '**Exclusões e substituições:** nada aqui.\n', encoding='utf-8',
            )
            selection = research.import_report(path)
            self.assertTrue(self.validate(selection)['valid'])
            self.assertEqual(selection['themes'][0]['articles'][0]['notes'], 'Nota histórica.')
            path.write_text('Sem entradas reconhecidas.', encoding='utf-8')
            with self.assertRaises(ValueError):
                research.import_report(path)


if __name__ == '__main__':
    unittest.main()
