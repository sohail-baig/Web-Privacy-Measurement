import os
import unittest
from playwright.sync_api import sync_playwright
from crawler_src.consent import accept_consent


@unittest.skipUnless(os.environ.get('OTP_BROWSER_TESTS') == '1', 'Requires local Chromium')
class ConsentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)

    def test_english_and_dutch_accept_all_not_reject(self):
        for label in ('Accept all cookies', 'Alles accepteren', 'Alle cookies toestaan'):
            self.page.set_content(f'''<div role="dialog">We use cookies
                <button onclick="window.rejected=true">Reject all</button>
                <button onclick="this.parentElement.remove()">{label}</button></div>''')
            self.assertEqual(accept_consent(self.page), 'accepted')
            self.assertFalse(self.page.evaluate('Boolean(window.rejected)'))

    def test_no_banner_does_not_click_unrelated_accept(self):
        self.page.set_content('<button onclick="window.clicked=true">Accept all</button>')
        self.assertEqual(accept_consent(self.page), 'not_found')
        self.assertFalse(self.page.evaluate('Boolean(window.clicked)'))

    def test_iframe(self):
        self.page.set_content('''<iframe srcdoc="&lt;div role='dialog'&gt;Cookies
            &lt;button onclick='this.parentElement.remove()'&gt;Allow all&lt;/button&gt;&lt;/div&gt;"></iframe>''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_open_shadow_root(self):
        self.page.set_content('<div id="host"></div>')
        self.page.evaluate('''() => document.querySelector('#host').attachShadow({mode:'open'}).innerHTML =
            `<div role="dialog">Cookies <button onclick="this.parentElement.remove()">Accept all</button></div>`''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_unknown_or_disabled_controls_are_failed(self):
        for button in ('<button>Preferences</button>', '<button disabled>Accept all</button>'):
            self.page.set_content(f'<div role="dialog">Cookies {button}</div>')
            self.assertEqual(accept_consent(self.page), 'failed')

    def test_click_without_dismissal_is_failed(self):
        self.page.set_content('<div role="dialog">Cookies <button>Accept all</button></div>')
        self.assertEqual(accept_consent(self.page), 'failed')

    def test_reject_selected_and_hidden_decoys_not_clicked(self):
        self.page.set_content('''<div role="dialog">Cookies
          <button style="display:none">Accept all</button>
          <button onclick="window.wrong=true">Accept selected</button>
          <button onclick="this.parentElement.remove()">Accept all</button></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')
        self.assertFalse(self.page.evaluate('Boolean(window.wrong)'))

    def test_generic_accept_requires_cookie_context(self):
        self.page.set_content('''<div role="dialog">We use cookies.
            <button onclick="this.parentElement.remove()">I agree</button></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_persistent_body_cookie_class_and_policy_link(self):
        self.page.set_content('''<body class="cookie-consent-open"><a class="cookie-policy">Cookie policy</a>
            <div class="cookie-wrapper"><div role="dialog">We use cookies
            <button onclick="this.closest('.cookie-wrapper').remove()">Alle cookies toestaan</button>
            </div></div></body>''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_generic_accept_does_not_save_partial_preferences(self):
        self.page.set_content('''<div role="dialog">Cookie preferences
            <label><input type="checkbox">Analytics</label>
            <div class="cookie-buttons"><button onclick="this.closest('[role=dialog]').remove()">Accept cookies</button></div></div>''')
        self.assertEqual(accept_consent(self.page), 'failed')
        self.assertTrue(self.page.get_by_role('dialog').is_visible())

    def test_accept_wordings_seen_on_crawled_sites(self):
        for label in ('I Accept Cookies', "I'm OK with that", 'Accept recommended settings',
                      'Accept all functional, advertising and performance cookies'):
            with self.subTest(label=label):
                self.page.set_content(f'''<div role="dialog">We use cookies
                    <button onclick="window.rejected=true">Reject all cookies</button>
                    <button onclick="this.parentElement.remove()">{label}</button></div>''')
                self.assertEqual(accept_consent(self.page), 'accepted')
                self.assertFalse(self.page.evaluate('Boolean(window.rejected)'))

    def test_tiered_prompt_selects_complete_level(self):
        self.page.set_content('''<div class="cookieconsent"><p>Choose your cookie level</p>
            <button onclick="window.wrong=true">Essential Provides basic functions and uses anonymized cookies.</button>
            <button onclick="this.parentElement.remove()">Complete Provides personalized content and uses marketing cookies.</button></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')
        self.assertFalse(self.page.evaluate('Boolean(window.wrong)'))

    def test_emptied_wrapper_with_hidden_consent_copy_is_not_a_banner(self):
        self.page.set_content('''<div class="consent-host"><button aria-label="Cookie settings"></button>
            <span hidden>Cookie consent preferences</span>
            <div role="dialog">We use cookies <button onclick="this.parentElement.remove()">Accept all</button></div></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_wrapper_that_stays_rendered_after_acceptance(self):
        self.page.set_content('''<div class="cookie-wrap" style="min-height:20px">
            <div id="prompt">We use cookies <button onclick="document.querySelector('#prompt').remove()">Accept all</button></div></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')

    def test_static_notice_below_the_fold_is_not_a_prompt(self):
        self.page.set_content('''<div style="height:3000px"></div>
            <div class="cookie">We use cookies <button onclick="window.clicked=true">I Accept</button></div>''')
        self.assertEqual(accept_consent(self.page), 'not_found')
        self.assertFalse(self.page.evaluate('Boolean(window.clicked)'))

    def test_settings_launcher_left_after_acceptance_is_not_a_banner(self):
        self.page.set_content('''<div id="cookie-wrapper"><div role="dialog">We use cookies
            <button onclick="this.parentElement.remove()">Accept all</button></div>
            <button>Cookie settings</button></div>''')
        self.assertEqual(accept_consent(self.page), 'accepted')
