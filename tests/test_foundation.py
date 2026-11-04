import json
from pathlib import Path
import tempfile
import unittest
import gc
import warnings

from crawler_src.common import read_sites, ReferenceData, atomic_json, required_artifacts, validate_artifacts
from analysis.prepare import load_visit, prepare

ROOT = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = ReferenceData(ROOT / 'crawler_src/reference_data')

    def test_instructor_selection_and_input_validation(self):
        sites = read_sites(ROOT / 'sites.csv')
        self.assertEqual(len(sites), 30)
        self.assertEqual({c: sum(s.country == c for s in sites) for c in ('nl','uk','us')}, {'nl':10,'uk':10,'us':10})
        path = self.root / 'sites.csv'
        path.write_text('Example.COM,nl\n', encoding='utf-8')
        self.assertEqual(read_sites(path)[0].domain, 'example.com')
        for content in ('a.com,nl\nA.com,uk\n', 'a.com,de\n', '../a.com,nl\n', 'https://a.com,nl\n', '', 'domain,country\na.com\n'):
            path.write_text(content, encoding='utf-8')
            with self.subTest(content=content), self.assertRaises(ValueError):
                read_sites(path)

    def test_domains_are_offline_and_boundary_aware(self):
        self.assertEqual(self.refs.domain('https://www.cam.ac.uk/path'), 'cam.ac.uk')
        self.assertEqual(self.refs.domain('https://a.example.com'), 'example.com')
        self.assertEqual(self.refs.domain('https://127.0.0.1:9000'), '127.0.0.1')
        self.assertTrue(self.refs.classify('www.google-analytics.com')['categories'])
        self.assertEqual(self.refs.classify('notgoogle-analytics.com')['categories'], [])
        self.assertEqual(self.refs.classify('unknown.invalid')['entities'], [])
        info = self.refs.classify('www.hotjar.com')
        self.assertTrue(info['session_replay'])
        self.assertIn('Analytics', info['categories'])
        self.assertTrue(info['entities'])

    def test_missing_or_tampered_reference_is_rejected(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            ReferenceData(self.root)
        data = self.root / 'reference_data'
        data.mkdir()
        for source in (ROOT / 'crawler_src/reference_data').iterdir():
            if source.is_file():
                (data / source.name).write_bytes(source.read_bytes())
        (data / 'services.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            ReferenceData(data)

    def test_local_psl_read_closes_file(self):
        gc.collect()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            refs = ReferenceData()
            refs.domain('example.com')
            gc.collect()
        self.assertEqual([str(w.message) for w in caught if issubclass(w.category, ResourceWarning)], [])

    def test_har_keeps_http_errors_and_headers_but_excludes_no_response(self):
        meta = {'domain':'original.edu','country':'us','mode':'desktop','final_url':'https://new.ac.uk/','outcome':'complete'}
        entries = [
            {'request':{'url':'https://assets.new.ac.uk/a'}, 'response':{'status':404,'headers':[{'name':'X-Test','value':'a'},{'name':'X-Test','value':'b'}]}},
            {'request':{'url':'https://www.hotjar.com/a'}, 'response':{'status':200,'headers':[]}},
            {'request':{'url':'https://google-analytics.com/blocked'}, 'response':{'status':0,'headers':[]}},
            {'request':{'url':'https://a.com/no-response'}},
        ]
        har = self.root / 'visit.har'
        atomic_json(har, {'log':{'entries':entries}})
        visit, rows = load_visit(meta, har, self.refs)
        self.assertEqual(visit['request_count'], 2)
        self.assertEqual([r['is_third_party'] for r in rows], [False,True])
        self.assertEqual(rows[0]['status'], 404)
        self.assertEqual(len(rows[0]['response_headers']), 2)
        self.assertEqual(rows[1]['site'], 'original.edu')
        self.assertTrue(rows[1]['session_replay'])

    def test_zero_response_visit_is_preserved(self):
        meta = {'domain':'example.com','country':'nl','mode':'ignore','final_url':'https://example.com/','outcome':'complete'}
        har = self.root / 'empty.har'
        atomic_json(har, {'log':{'entries':[]}})
        visit, rows = load_visit(meta, har, self.refs)
        self.assertEqual(visit['request_count'], 0)
        self.assertEqual(rows, [])

    def test_empty_dataset_has_headers_and_coverage(self):
        prepare(self.root, self.refs)
        self.assertIn('site', (self.root / 'analysis/output/visits.csv').read_text())
        self.assertIn('is_third_party', (self.root / 'analysis/output/requests.csv').read_text())
        coverage = json.loads((self.root / 'analysis/output/coverage.json').read_text())
        self.assertEqual(coverage['ignore']['complete'], 0)

    def test_artifact_contract_checks_content(self):
        self.assertEqual(len(required_artifacts('a.com','ignore')), 3)
        self.assertEqual(len(required_artifacts('a.com','desktop')), 4)
        with self.assertRaises(ValueError):
            validate_artifacts(self.root, 'a.com','ignore')


if __name__ == '__main__':
    unittest.main()
