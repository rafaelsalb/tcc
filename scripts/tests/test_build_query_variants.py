import copy
import importlib.util
import json
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'build_query_variants.py'
SPEC = importlib.util.spec_from_file_location('build_query_variants', SCRIPT)
variants = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(variants)


class VariantTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((variants.REPO / 'evals_curated_2025_2026.json').read_text())

    def test_forty_distinct_queries_with_ordered_references_and_baselines(self):
        original = copy.deepcopy(self.base)
        result = variants.build_variants(self.base)
        self.assertEqual(self.base, original)
        self.assertEqual(len(result['evaluations']), 40)
        self.assertEqual(len({e['id'] for e in result['evaluations']}), 40)
        self.assertEqual(len({e['query'] for e in result['evaluations']}), 40)
        by_id = {e['id']: e for e in self.base['evaluations']}
        for evaluation in result['evaluations']:
            key, style = evaluation['id'].split('__')
            self.assertEqual(evaluation['query_formulation'], style)
            self.assertEqual(evaluation['relevant_urls'], by_id[key]['relevant_urls'])
            self.assertEqual(len(evaluation['relevant_urls']), 20)
            if style == 'baseline':
                self.assertEqual(evaluation['query'], by_id[key]['query'])

    def test_all_themes_are_interleaved_by_style(self):
        result = variants.build_variants(self.base)['evaluations']
        for offset, style in enumerate(variants.STYLES):
            group = result[offset * 5:offset * 5 + 5]
            self.assertEqual({e['id'].split('__')[0] for e in group}, set(variants.QUERIES))
            self.assertTrue(all(e['id'].endswith('__' + style) for e in group))

    def test_generated_file_matches_reproducible_recipe(self):
        actual = json.loads((variants.REPO / 'evals_curated_query_variants_stages_2025_2026.json').read_text())
        self.assertEqual(actual, variants.build_variants(self.base))

    def test_bad_source_is_rejected(self):
        for document in [dict(self.base, schema_version=True),
                         dict(self.base, evaluations=[]),
                         dict(self.base, extra='field')]:
            with self.subTest(document=document.keys()):
                with self.assertRaises(ValueError):
                    variants.build_variants(document)
        self.base['evaluations'][0]['relevant_urls'] *= 2
        with self.assertRaises(ValueError):
            variants.build_variants(self.base)


if __name__ == '__main__':
    unittest.main()
