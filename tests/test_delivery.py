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
    def test_all_question_stubs_are_explicit(self):
        for number in range(1,13):
            with self.subTest(question=number), self.assertRaisesRegex(NotImplementedError, f'Q{number}'):
                QUESTIONS[number](Path('.'))
        self.assertEqual(analysis_main(['--question','1']), 2)

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
