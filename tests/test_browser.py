"""Real local-browser tests. Set OTP_BROWSER_TESTS=1 to include them."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import subprocess
import sys
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from crawler_src.common import Site, ReferenceData, validate_artifacts
from crawler_src.crawl import SETTINGS, collect_visit, scroll_page, crawl_sites
from analysis.prepare import prepare
from report.render import render_report


class LocalPage(BaseHTTPRequestHandler):
    hits = []
    def do_GET(self):
        type(self).hits.append(self.path)
        if self.path.startswith('/tracker'):
            body = b'window.trackerLoaded = true;'
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript')
        else:
            body = b'''<!doctype html><html><body style="height:2400px">
            <div id="banner" role="dialog">We use cookies.<button onclick="document.querySelector('#banner').remove()">Accept all</button></div>
            <script>document.body.dataset.previousCookie = document.cookie; document.cookie='fixture=1';</script>
            <script src="/tracker.js"></script><h1>Local measurement fixture</h1></body></html>'''
            self.send_response(200)
            self.send_header('Content-Type','text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get('OTP_BROWSER_TESTS') == '1', 'Set OTP_BROWSER_TESTS=1 for local Chromium checks')
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1',0), LocalPage)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/'
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_all_modes_capture_flush_and_fresh_context(self):
        refs = ReferenceData()
        refs.categories['127.0.0.1'] = {'Advertising'}
        # Block the local tracker path, not the fixture document itself.
        original_blocked = refs.blocked
        refs.blocked = lambda url: '/tracker.js' in url and original_blocked(url)
        site = Site('fixture.example','nl')
        fast = {**SETTINGS, 'before_consent_ms':1,'after_consent_ms':1,'after_scroll_ms':1,'scroll_pause_ms':10}
        for mode in ('desktop','mobile','block','ignore'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary)
                def handler(page):
                    self.assertEqual(page.locator('body').get_attribute('data-previous-cookie'), '')
                    page.get_by_role('button', name='Accept all').click()
                    return 'accepted'
                with patch.dict(SETTINGS, fast):
                    metadata = collect_visit(self.browser, self.playwright.devices, site, mode, target, refs, handler, self.url)
                hashes = validate_artifacts(target, site.domain, mode)
                self.assertEqual(len(hashes), 3 if mode == 'ignore' else 4)
                self.assertEqual(metadata['consent_outcome'], 'not_attempted' if mode == 'ignore' else 'accepted')
                self.assertEqual(metadata['blocked_request_count'] > 0, mode == 'block')
                har = json.loads((target/'fixture.example.har').read_text())
                tracker = [e for e in har['log']['entries'] if '/tracker.js' in e['request']['url']]
                received = [e for e in tracker if e.get('response',{}).get('status',0) > 0]
                self.assertEqual(bool(received), mode != 'block')

    def test_scroll_stops_when_dialog_prevents_movement(self):
        page = self.browser.new_page()
        try:
            page.set_content('<body style="overflow:hidden"><div style="height:5000px">Locked</div></body>')
            scroll_page(page)
            self.assertEqual(page.evaluate('window.scrollY'), 0)
        finally:
            page.close()

    def test_ignore_full_waits_resume_and_prepare_roundtrip(self):
        refs = ReferenceData()
        sites = [Site('fixture.example','nl')]
        def local_visit(browser, devices, site, mode, staging, references, handler):
            return collect_visit(browser, devices, site, mode, staging, references, handler, self.url)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('crawler_src.crawl.collect_visit', side_effect=local_visit):
                result = crawl_sites(self.browser,self.playwright.devices,sites,'ignore',root,refs)
                self.assertEqual(result, {'complete':1,'failed':0,'pending':0})
                before = len(LocalPage.hits)
                self.assertEqual(crawl_sites(self.browser,self.playwright.devices,sites,'ignore',root,refs), result)
                self.assertEqual(len(LocalPage.hits), before)
            coverage = prepare(root,refs)
            self.assertEqual(coverage['ignore']['complete'],1)
            self.assertIn('fixture.example', (root/'analysis/output/visits.csv').read_text())

    def test_draft_pdf_is_real_and_recorded_as_draft(self):
        source = Path(__file__).resolve().parents[1] / 'report/template.html'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'report').mkdir()
            (root/'report/template.html').write_bytes(source.read_bytes())
            result = subprocess.run([sys.executable, '-m', 'report.render', '--root', str(root)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root/'report.pdf').read_bytes().startswith(b'%PDF-'))
            self.assertGreater((root/'report.pdf').stat().st_size, 10000)
            self.assertTrue(json.loads((root/'report/build.json').read_text())['draft'])

    def test_desktop_production_consent_capture_and_resume(self):
        refs = ReferenceData()
        sites = [Site('fixture.example','nl')]
        def local_visit(browser, devices, site, mode, staging, references, handler):
            return collect_visit(browser, devices, site, mode, staging, references, handler, self.url)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('crawler_src.crawl.collect_visit', side_effect=local_visit):
                result = crawl_sites(self.browser,self.playwright.devices,sites,'desktop',root,refs)
                self.assertEqual(result, {'complete':1,'failed':0,'pending':0})
                manifest = json.loads((root/'crawl_data_desktop/manifest.json').read_text())
                self.assertEqual(manifest['visits']['fixture.example']['consent_outcome'],'accepted')
                self.assertEqual(len(validate_artifacts(root/'crawl_data_desktop','fixture.example','desktop')),4)
                before = len(LocalPage.hits)
                self.assertEqual(crawl_sites(self.browser,self.playwright.devices,sites,'desktop',root,refs),result)
                self.assertEqual(len(LocalPage.hits), before)
