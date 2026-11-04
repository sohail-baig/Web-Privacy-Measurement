import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crawler_src.common import Site, ReferenceData, ROOT, atomic_json
from crawler_src.crawl import preflight, context_options, perform_steps, crawl_sites, run_identity


class RecordingPage:
    """Clock/page spy for the required ordered interaction contract."""
    def __init__(self):
        self.events = []
        self.viewport_size = {'width':1366, 'height':768}

    def goto(self, url, **kwargs):
        self.events.append(('goto', url, kwargs))

    def wait_for_timeout(self, milliseconds):
        self.events.append(('wait', milliseconds))

    def screenshot(self, path, full_page):
        self.events.append(('screenshot', Path(path).name, full_page))


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.refs = ReferenceData()

    def test_unimplemented_consent_fails_before_collection(self):
        for mode in ('desktop','mobile','block'):
            with self.subTest(mode=mode), self.assertRaisesRegex(NotImplementedError, 'consent'):
                preflight(mode)
        preflight('ignore')

    def test_mobile_requires_real_pixel_descriptor(self):
        with self.assertRaisesRegex(ValueError, 'Pixel 10'):
            context_options('mobile', {}, self.root)
        options = context_options('mobile', {'Pixel 10':{'viewport':{'width':412,'height':915},'is_mobile':True,'default_browser_type':'chromium'}}, self.root)
        self.assertTrue(options['is_mobile'])
        self.assertNotIn('default_browser_type', options)
        self.assertEqual(options['record_video_size'], {'width':412,'height':915})
        for mode in ('desktop','block','ignore'):
            self.assertEqual(context_options(mode, {}, self.root)['viewport'], {'width':1366,'height':768})

    def test_exact_visit_sequence_and_ignore_never_calls_consent(self):
        for mode in ('desktop','mobile','block','ignore'):
            page = RecordingPage()
            def accept(current_page):
                current_page.events.append(('consent',))
                return 'not_found'
            with patch('crawler_src.crawl.scroll_page', side_effect=lambda p: p.events.append(('scroll',))):
                outcome = perform_steps(page, 'https://example.com/', 'example.com', mode, self.root, accept)
            expected = [('goto','https://example.com/',{'wait_until':'load','timeout':60000}), ('wait',10000), ('screenshot','example.com_pre_consent.png',False)]
            if mode != 'ignore':
                expected += [('consent',),('wait',5000),('screenshot','example.com_post_consent.png',False)]
            expected += [('scroll',),('wait',5000)]
            self.assertEqual(page.events, expected)
            self.assertEqual(outcome, 'not_attempted' if mode == 'ignore' else 'not_found')

    def test_identity_changes_with_sites_or_configuration(self):
        sites = [Site('a.com','nl')]
        identity = run_identity('ignore', sites, self.refs, 'browser-v1')
        changed = run_identity('ignore', [Site('b.com','nl')], self.refs, 'browser-v1')
        self.assertNotEqual(identity, changed)
        self.assertNotEqual(identity, run_identity('ignore', sites, self.refs, 'browser-v2'))

    def test_resume_preserves_completed_visit_and_retries_interrupt(self):
        # Fake collection writes the real artifact contract; persistence/resume code is real.
        calls = []
        interrupted = [True]
        def visit(browser, devices, site, mode, staging, refs, handler):
            calls.append(site.domain)
            if site.domain == 'b.com' and interrupted[0]:
                interrupted[0] = False
                raise KeyboardInterrupt()
            atomic_json(staging / f'{site.domain}.har', {'log':{'entries':[]}})
            (staging / f'{site.domain}_pre_consent.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            (staging / f'{site.domain}.webm').write_bytes(b'\x1a\x45\xdf\xa3fixture')
            return {'final_url':f'https://{site.domain}/','consent_outcome':'not_attempted'}
        class Browser:
            version = 'fixture'
        sites = [Site('a.com','nl'),Site('b.com','us')]
        with patch('crawler_src.crawl.collect_visit', side_effect=visit):
            with self.assertRaises(KeyboardInterrupt):
                crawl_sites(Browser(), {}, sites, 'ignore', self.root, self.refs)
            summary = crawl_sites(Browser(), {}, sites, 'ignore', self.root, self.refs)
            self.assertEqual(calls, ['a.com','b.com','b.com'])
            self.assertEqual(summary, {'complete':2,'failed':0,'pending':0})
            with self.assertRaisesRegex(ValueError, 'incompatible'):
                crawl_sites(Browser(), {}, [Site('a.com','uk')], 'ignore', self.root, self.refs)
        manifest = json.loads((self.root/'crawl_data_ignore/manifest.json').read_text())
        self.assertEqual(manifest['visits']['a.com']['outcome'], 'complete')
        (self.root/'crawl_data_ignore/a.com.har').write_text('{}')
        with self.assertRaises(ValueError):
            crawl_sites(Browser(), {}, sites, 'ignore', self.root, self.refs)


if __name__ == '__main__':
    unittest.main()
