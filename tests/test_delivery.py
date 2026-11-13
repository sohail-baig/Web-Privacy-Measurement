import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch
from zipfile import ZipFile

from analysis.run import main as analysis_main
from analysis.questions import QUESTIONS
from submission import check_submission, package_submission
from crawler_src.common import ROOT, MODES, ReferenceData, read_sites, atomic_json, validate_artifacts, sha256
from crawler_src.crawl import run_identity
from analysis.prepare import prepare
from analysis.run import execute_question
from report.render import report_inputs


class DeliveryTests(unittest.TestCase):
    def test_unfinished_question_stubs_are_explicit(self):
        implemented = {1, 2, 3, 4, 5, 6, 7, 9, 10, 11}
        for number in sorted(set(range(1,13)) - implemented):
            with self.subTest(question=number), self.assertRaisesRegex(NotImplementedError, f'Q{number}'):
                QUESTIONS[number](Path('.'))
        self.assertEqual(analysis_main(['--question','8']), 2)

    def write_prepared(self, root, visits, requests):
        output = root/'analysis/output'
        output.mkdir(parents=True)
        lines = ['site,country,mode,final_url,first_party_domain,request_count,consent_outcome']
        lines += [f'{site},{country},{mode},https://{site}/,{site},0,accepted' for site, country, mode in visits]
        (output/'visits.csv').write_text('\n'.join(lines) + '\n')
        with (output/'requests.csv').open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['site','country','mode','final_url','url','hostname','domain','is_third_party','status','response_headers','categories','entities','session_replay'])
            # Optional trailing fields: categories, response headers as (name, value) pairs, session replay.
            for site, country, mode, domain, third_party, entities, *extra in requests:
                categories, headers, replay = [*extra, *[[], [], False][len(extra):]]
                headers = json.dumps([{'name': name, 'value': value} for name, value in headers])
                writer.writerow([site, country, mode, f'https://{site}/', f'https://{domain}/x', domain, domain, third_party, 200, headers, json.dumps(categories), json.dumps(entities), replay])
        return output

    def read_rows(self, path):
        with path.open(newline='') as handle:
            return list(csv.DictReader(handle))

    def test_q5_counts_ignore_sites_per_category_and_country(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [('a.nl','nl','ignore'), ('b.nl','nl','ignore'), ('c.edu','us','ignore'), ('d.uk','uk','desktop')]
            requests = [('a.nl','nl','ignore','ads.com',True,[],['Advertising']),
                        ('a.nl','nl','ignore','stats.com',True,[],['Analytics']),
                        ('c.edu','us','ignore','stats.com',True,[],['Analytics']),
                        ('d.uk','uk','desktop','ads.com',True,[],['Advertising'])]
            output = self.write_prepared(root, visits, requests)
            self.assertEqual([path.name for path in QUESTIONS[5](root)], ['q5.csv','q5_advertising.png','q5_analytics.png'])
            self.assertEqual(self.read_rows(output/'q5.csv'), [
                {'country':'NL','sites_visited':'2','advertising_sites':'1','analytics_sites':'1'},
                {'country':'US','sites_visited':'1','advertising_sites':'0','analytics_sites':'1'}])

    def test_q6_uses_global_set_difference_and_alphabetical_ties(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [(site, 'nl', mode) for site in ('a.nl','b.nl') for mode in ('desktop','mobile')]
            requests = [('a.nl','nl','desktop','shared.com',True,[]), ('a.nl','nl','mobile','shared.com',True,[]),
                        # Seen on Mobile at another site, so not Desktop-only globally.
                        ('a.nl','nl','desktop','global.com',True,[]), ('b.nl','nl','mobile','global.com',True,[]),
                        ('a.nl','nl','desktop','one.com',True,[]), ('b.nl','nl','desktop','one.com',True,[]),
                        ('a.nl','nl','desktop','zed.com',True,[]), ('b.nl','nl','desktop','bee.com',True,[]),
                        ('a.nl','nl','desktop','cat.com',True,[]), ('a.nl','nl','mobile','phone.com',True,[]),
                        ('a.nl','nl','mobile','a.nl',False,[])]
            output = self.write_prepared(root, visits, requests)
            QUESTIONS[6](root)
            self.assertEqual([(row['exclusive_to'], row['domain'], row['sites']) for row in self.read_rows(output/'q6.csv')], [
                ('Desktop only','one.com','2'), ('Desktop only','bee.com','1'), ('Desktop only','cat.com','1'),
                ('Mobile only','phone.com','1')])

    def test_q7_ranks_by_sites_and_unions_categories_or_na(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [('a.nl','nl','desktop'), ('b.nl','nl','desktop')]
            requests = [('a.nl','nl','desktop','track.com',True,[],['Analytics']),
                        ('b.nl','nl','desktop','track.com',True,[],['Advertising']),
                        ('a.nl','nl','desktop','plain.com',True,[]),
                        ('a.nl','nl','desktop','a.nl',False,[],['Content'])]
            output = self.write_prepared(root, visits, requests)
            self.assertEqual([path.name for path in QUESTIONS[7](root)], ['q7_desktop.csv'])
            self.assertEqual(self.read_rows(output/'q7_desktop.csv'), [
                {'rank':'1','domain':'track.com','sites':'2','categories':'Advertising; Analytics'},
                {'rank':'2','domain':'plain.com','sites':'1','categories':'NA'}])

    def test_q9_lists_session_replay_sites_with_all_observed_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [('a.nl', 'nl', mode) for mode in ('desktop','mobile','ignore')] + [('b.uk','uk','desktop')]
            requests = [('a.nl','nl','ignore','hotjar.com',True,[],[],[],True),
                        ('a.nl','nl','desktop','hotjar.com',True,[],[],[],True),
                        ('a.nl','nl','mobile','hotjar.com',True,[],[],[],False),
                        ('b.uk','uk','desktop','ads.com',True,[],[],[],False)]
            output = self.write_prepared(root, visits, requests)
            QUESTIONS[9](root)
            self.assertEqual(self.read_rows(output/'q9.csv'), [
                {'site':'a.nl','country':'NL','session_replay_domain':'hotjar.com','modes':'Desktop, Ignore'}])

    def test_q10_counts_explicitly_disabled_mobile_first_party_permissions(self):
        from analysis.questions import disabled_permissions
        self.assertEqual(disabled_permissions('camera=(), geolocation=(self), microphone=( ), usb=*'), {'camera','microphone'})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [(site, 'nl', 'mobile') for site in ('a.nl','b.nl','c.nl','d.nl')] + [('e.nl','nl','desktop')]
            requests = [('a.nl','nl','mobile','a.nl',False,[],[],[('Permissions-Policy','camera=(), microphone=()')]),
                        ('b.nl','nl','mobile','b.nl',False,[],[],[('permissions-policy','camera=()'), ('Permissions-Policy','geolocation=()')]),
                        ('c.nl','nl','mobile','cdn.com',True,[],[],[('Permissions-Policy','payment=()')]),
                        ('d.nl','nl','mobile','d.nl',False,[],[],[('Permissions-Policy','geolocation=(self)')]),
                        ('e.nl','nl','desktop','e.nl',False,[],[],[('Permissions-Policy','usb=()')])]
            output = self.write_prepared(root, visits, requests)
            QUESTIONS[10](root)
            self.assertEqual([(row['permission'], row['sites'], row['sites_sending_header']) for row in self.read_rows(output/'q10.csv')],
                             [('camera','2','3'), ('geolocation','1','3'), ('microphone','1','3')])

    def test_q11_uses_last_recognized_referrer_policy(self):
        from analysis.questions import effective_referrer_policy
        for values, expected in ((['no-referrer', 'same-origin'], 'same-origin'), (['no-referrer, future-policy'], 'no-referrer'),
                                 (['strict-origin, no-referrer'], 'no-referrer'), ([' NO-REFERRER '], 'no-referrer'), ([''], None), ([], None)):
            with self.subTest(values=values):
                self.assertEqual(effective_referrer_policy(values), expected)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [('a.nl','nl','desktop'), ('b.uk','uk','desktop'), ('c.edu','us','desktop'), ('d.nl','nl','mobile')]
            no_referrer = [('Referrer-Policy','no-referrer')]
            requests = [('a.nl','nl','desktop','a.nl',False,[],[],no_referrer), ('a.nl','nl','desktop','a.nl',False,[],[],no_referrer),
                        ('b.uk','uk','desktop','b.uk',False,[],[],[('Referrer-Policy','no-referrer'), ('Referrer-Policy','same-origin')]),
                        ('c.edu','us','desktop','cdn.com',True,[],[],no_referrer),
                        ('d.nl','nl','mobile','d.nl',False,[],[],no_referrer)]
            output = self.write_prepared(root, visits, requests)
            QUESTIONS[11](root)
            self.assertEqual(self.read_rows(output/'q11.csv'), [{'site':'a.nl','country':'NL','no_referrer_responses':'2'}])

    def two_mode_fixture(self, root):
        visits = [('a.nl','nl','desktop'), ('b.uk','uk','desktop'), ('c.edu','us','desktop'),
                  ('a.nl','nl','mobile'), ('b.uk','uk','mobile'), ('c.edu','us','mobile')]
        requests = [
            ('a.nl','nl','desktop','a.nl',False,[],['Analytics']),  # first-party request still counts for Q3
            ('a.nl','nl','desktop','ads.com',True,['AdCo'],['Advertising']),
            ('a.nl','nl','desktop','ads.com',True,['AdCo'],['Advertising']),
            ('a.nl','nl','desktop','stats.com',True,['StatCo'],['Analytics']),
            ('b.uk','uk','desktop','b.uk',False,[]),
            ('b.uk','uk','desktop','ads.com',True,['AdCo'],['Advertising','Analytics']),
            # c.edu completed on desktop with zero requests.
            ('a.nl','nl','mobile','a.nl',False,[]),
            ('b.uk','uk','mobile','b.uk',False,[]),
            ('c.edu','us','mobile','c.edu',False,[]),
            ('c.edu','us','mobile','cdn.com',True,[],['Content']),
        ]
        return self.write_prepared(root, visits, requests)

    def test_q1_writes_per_visit_table_and_four_labelled_box_plots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.two_mode_fixture(root)
            files = QUESTIONS[1](root)
            self.assertEqual([path.name for path in files], ['q1_per_visit.csv', 'q1_requests.png', 'q1_third_party_requests.png',
                                                             'q1_third_party_domains.png', 'q1_third_party_entities.png'])
            for path in files[1:]:
                self.assertTrue(path.read_bytes().startswith(b'\x89PNG'))
            with (output/'q1_per_visit.csv').open(newline='') as handle:
                rows = {(row['site'], row['mode']): row for row in csv.DictReader(handle)}
            self.assertEqual(len(rows), 6)
            self.assertEqual({k: rows[('a.nl','Desktop')][k] for k in ('requests','third_party_requests','third_party_domains','third_party_entities')},
                             {'requests':'4','third_party_requests':'3','third_party_domains':'2','third_party_entities':'2'})
            self.assertEqual(rows[('c.edu','Desktop')]['requests'], '0')
            self.assertEqual(rows[('c.edu','Mobile')]['third_party_requests'], '1')

    def test_q2_summarises_metrics_by_mode_in_fixed_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.two_mode_fixture(root)
            self.assertEqual(QUESTIONS[2](root), [output/'q2.csv'])
            with (output/'q2.csv').open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row['mode'] for row in rows], ['Desktop','Mobile'])
            desktop, mobile = rows
            self.assertEqual(desktop['sites'], '3')
            self.assertEqual(tuple(float(desktop[f'requests_{n}']) for n in ('min','median','max')), (0, 2, 4))
            self.assertEqual(tuple(float(mobile[f'third_party_domains_{n}']) for n in ('min','median','max')), (0, 0, 1))

    def test_q3_counts_distinct_sites_per_category_and_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.two_mode_fixture(root)
            files = QUESTIONS[3](root)
            self.assertEqual([path.name for path in files], ['q3.csv', 'q3_advertising.png', 'q3_analytics.png'])
            with (output/'q3.csv').open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [
                {'mode':'Desktop','sites_visited':'3','advertising_sites':'2','analytics_sites':'2'},
                {'mode':'Mobile','sites_visited':'3','advertising_sites':'0','analytics_sites':'0'},
            ])

    def test_questions_refuse_to_run_without_visits(self):
        for number in (1, 2, 3, 5, 6, 7, 9, 10, 11):
            with self.subTest(question=number), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output = self.write_prepared(root, [], [])
                with self.assertRaisesRegex(ValueError, f'Q{number}'):
                    QUESTIONS[number](root)
                self.assertEqual(sorted(path.name for path in output.iterdir()), ['requests.csv', 'visits.csv'])

    def test_q4_groups_desktop_metrics_by_country(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            visits = [('a.nl','nl','desktop'), ('b.nl','nl','desktop'), ('c.nl','nl','desktop'),
                      ('d.edu','us','desktop'), ('a.nl','nl','mobile')]
            requests = [
                ('a.nl','nl','desktop','a.nl',False,[]),
                ('a.nl','nl','desktop','t1.com',True,['Google']),
                ('a.nl','nl','desktop','t1.com',True,['Google']),
                ('a.nl','nl','desktop','t2.com',True,['Meta']),
                ('a.nl','nl','desktop','t3.com',True,[]),
                ('b.nl','nl','desktop','b.nl',False,[]),
                ('b.nl','nl','desktop','t1.com',True,['Google']),
                # c.nl completed with zero requests and must still count.
                ('d.edu','us','desktop','d.edu',False,[]),
                ('a.nl','nl','mobile','mobile-only.com',True,['Other']),
            ]
            output = self.write_prepared(root, visits, requests)
            self.assertEqual(QUESTIONS[4](root), [output/'q4.csv'])
            with (output/'q4.csv').open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row['country'] for row in rows], ['NL','US'])
            nl, us = rows
            self.assertEqual(nl['sites'], '3')
            expected = {'requests':(0,2,5), 'third_party_requests':(0,1,4), 'third_party_domains':(0,1,3), 'third_party_entities':(0,1,2)}
            for metric, values in expected.items():
                actual = tuple(float(nl[f'{metric}_{name}']) for name in ('min','median','max'))
                self.assertEqual(actual, values, metric)
            self.assertEqual((us['sites'], float(us['requests_max']), float(us['third_party_requests_max'])), ('1', 1, 0))

    def test_q4_refuses_to_write_results_without_desktop_visits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.write_prepared(root, [('a.nl','nl','mobile')], [])
            with self.assertRaisesRegex(ValueError, 'Q4'):
                QUESTIONS[4](root)
            self.assertFalse((output/'q4.csv').exists())

    def test_checker_lists_missing_work_and_packager_refuses_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            issues = check_submission(root)
            self.assertTrue(any('sites.csv' in issue for issue in issues))
            self.assertTrue(any('report' in issue for issue in issues))
            with self.assertRaises(ValueError):
                package_submission(root, 'my-group')
            self.assertFalse((root / 'my-group.zip').exists())
            with self.assertRaises(ValueError):
                package_submission(root, '../escape')

    def test_desktop_cli_validates_input_before_browser_launch(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable,'crawler_src/crawl.py','-m','desktop','-l','missing-sites.csv'], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('missing-sites.csv', result.stderr)

    def make_ready_fixture(self, root):
        for folder in ('crawler_src','analysis','report','tests'):
            shutil.copytree(ROOT/folder, root/folder, ignore=shutil.ignore_patterns('__pycache__','output'))
        for name in ('sites.csv','requirements.txt','submission.py'):
            shutil.copyfile(ROOT/name, root/name)
        sites, refs = read_sites(root/'sites.csv'), ReferenceData()
        for mode in MODES:
            directory = root/f'crawl_data_{mode}'
            directory.mkdir()
            visits = {}
            for site in sites:
                atomic_json(directory/f'{site.domain}.har', {'log':{'entries':[]}})
                for suffix in ('pre_consent',) if mode == 'ignore' else ('pre_consent','post_consent'):
                    (directory/f'{site.domain}_{suffix}.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
                (directory/f'{site.domain}.webm').write_bytes(b'\x1a\x45\xdf\xa3fixture')
                visits[site.domain] = {'domain':site.domain,'country':site.country,'mode':mode,'outcome':'complete',
                    'final_url':f'https://{site.domain}/','consent_outcome':'not_attempted' if mode == 'ignore' else 'accepted',
                    'artifact_hashes':validate_artifacts(directory,site.domain,mode)}
            atomic_json(directory/'manifest.json', {'identity':run_identity(mode, sites, refs,'fixture'), 'visits':visits})
        prepare(root, refs)
        def fixture_question(project):
            path = project/'analysis/output/fixture.csv'
            path.write_text('metric,value\nfixture,0\n')
            return [path]
        with patch.dict(QUESTIONS, {n:fixture_question for n in range(1,13)}):
            for number in range(1,13):
                execute_question(number,root)
        (root/'report.pdf').write_bytes(b'%PDF-1.7\nfixture only\n%%EOF')
        atomic_json(root/'report/build.json', {'draft':False,'html_hash':sha256(root/'report/template.html'),'pdf_hash':sha256(root/'report.pdf'), 'input_hashes':report_inputs(root)})

    def test_ready_fixture_packages_and_detects_stale_measurement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_ready_fixture(root)
            self.assertEqual(check_submission(root), [])
            target = package_submission(root,'fixture-group')
            with ZipFile(target) as archive:
                names = set(archive.namelist())
                self.assertIn('sites.csv', names)
                self.assertIn('report.pdf', names)
                self.assertIn('crawler_src/crawl.py', names)
                self.assertIn('analysis/run.py', names)
                self.assertIn('tests/test_foundation.py', names)
                self.assertIn('crawl_data_ignore/uva.nl.har', names)
                self.assertFalse(any('__pycache__' in name or '.staging' in name for name in names))
                self.assertIsNone(archive.testzip())
            manifest = root/'crawl_data_ignore/manifest.json'
            data = json.loads(manifest.read_text())
            data['visits']['uva.nl']['final_url'] = 'https://different.example/'
            atomic_json(manifest,data)
            self.assertTrue(any('prepared' in issue.lower() for issue in check_submission(root)))

    def test_pdf_becomes_stale_after_analysis_or_report_asset_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_ready_fixture(root)
            self.assertEqual(check_submission(root), [])
            path = root/'analysis/output/fixture.csv'
            path.write_text('metric,value\nfixture,1\n')
            completion_path = root/'analysis/output/completion.json'
            completion = json.loads(completion_path.read_text())
            for entry in completion.values():
                entry['outputs']['fixture.csv'] = sha256(path)
            atomic_json(completion_path,completion)
            self.assertTrue(any('report.pdf' in issue and 'stale' in issue for issue in check_submission(root)))
            build_path = root/'report/build.json'
            build = json.loads(build_path.read_text())
            build['input_hashes'] = report_inputs(root)
            atomic_json(build_path,build)
            self.assertEqual(check_submission(root), [])
            (root/'report/style.css').write_text('body { color: red; }')
            self.assertTrue(any('report.pdf' in issue and 'stale' in issue for issue in check_submission(root)))

    def test_wrong_mode_or_site_identity_cannot_enter_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_ready_fixture(root)
            manifest_path = root/'crawl_data_mobile/manifest.json'
            original = json.loads(manifest_path.read_text())
            cases = [('identity mode', lambda m: m['identity'].update(mode='desktop')),
                     ('visit mode', lambda m: m['visits']['uva.nl'].update(mode='desktop')),
                     ('visit domain', lambda m: m['visits']['uva.nl'].update(domain='wrong.example'))]
            for label, mutate in cases:
                changed = json.loads(json.dumps(original))
                mutate(changed)
                atomic_json(manifest_path,changed)
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ValueError, 'identity'):
                        prepare(root)
                    self.assertTrue(any('identity' in issue for issue in check_submission(root)))


if __name__ == '__main__':
    unittest.main()
