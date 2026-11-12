"""Generic local consent handling; never select reject or selected-only consent."""
import re
import time
from playwright.sync_api import Error as PlaywrightError

IMPLEMENTED = True
SCOPES = ','.join(('[role="dialog"]', '[role="alertdialog"]', '[aria-modal="true"]',
    '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]',
    '[class*="consent" i]', '#onetrust-banner-sdk'))
CONSENT_TEXT = re.compile(r'cookies?|consent|tracking|personal data|persoonlijke gegevens|toestemming', re.I)
ACCEPT_ALL = re.compile(
    r'^\s*(accept|allow|agree to|enable)\s+all(?:\s+cookies)?[.!]?\s*$|'
    r'^\s*(alles accepteren|alles toestaan|alle cookies accepteren|alle cookies toestaan|'
    r'accepteer alle cookies|accepteer alles|sta alles toe)[.!]?\s*$', re.I)
ACCEPT = re.compile(r'^\s*(accept(?: cookies)?|allow cookies|i agree|agree|'
                    r'akkoord|ik ga akkoord|accepteren|toestaan)[.!]?\s*$', re.I)
KNOWN_ACCEPT = '#onetrust-accept-btn-handler, #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, #didomi-notice-agree-button'


def visible_banners(page):
    """CSS locators traverse open shadow roots; inspect frames separately."""
    banners = []
    for frame in page.frames:
        if frame.is_detached():
            continue
        for scope in frame.locator(SCOPES).all():
            if scope.evaluate('(e) => ["HTML","BODY","A","BUTTON","INPUT"].includes(e.tagName)'):
                continue
            if not scope.is_visible() or not scope.locator('button, [role="button"], input, a').count():
                continue
            # A permanent "Cookie settings" launcher is not an active consent prompt.
            explanation = scope.evaluate('''e => {
                const copy = e.cloneNode(true);
                copy.querySelectorAll('button, [role="button"], input, a').forEach(n => n.remove());
                return copy.textContent;
            }''')
            if CONSENT_TEXT.search(explanation):
                banners.append(scope)
    # Prefer the dialog itself over a persistent outer wrapper.
    return sorted(banners, key=lambda scope: len(scope.inner_text(timeout=500)))


def accept_consent(page):
    """Return accepted, not_found, or failed; verify dismissal after clicking.

    shortcut: unfamiliar preference-only flows fail when detected; extend generic
    selectors/labels when manual evidence warrants it. Closed shadow roots cannot
    be inspected, so not_found is a detector result, not proof no dialog exists.
    """
    deadline = time.monotonic() + 12
    clicked = False
    try:
        for _ in range(3):
            banners = visible_banners(page)
            if not banners:
                return 'accepted' if clicked else 'not_found'
            candidate = None
            for pattern in (ACCEPT_ALL, ACCEPT):
                if pattern is ACCEPT and any(scope.get_by_role(role).count() for scope in banners for role in ('checkbox', 'switch', 'radio')):
                    continue
                for scope in banners:
                    controls = scope.get_by_role('button', name=pattern).all()
                    controls += scope.get_by_role('link', name=pattern).all()
                    controls += scope.locator(KNOWN_ACCEPT).all()
                    for control in controls:
                        if control.is_visible() and control.is_enabled():
                            candidate = (scope, control)
                            break
                    if candidate:
                        break
                if candidate:
                    break
            if candidate is None or time.monotonic() >= deadline:
                return 'failed'
            scope, control = candidate
            # A locator might resolve to a different banner after the click.
            original = scope.element_handle(timeout=500)
            if original is None:
                return 'failed'
            try:
                control.click(timeout=min(1500, max(1, (deadline - time.monotonic()) * 1000)))
                dismissed_by = min(deadline, time.monotonic() + 2.5)
                while original.is_visible() and time.monotonic() < dismissed_by:
                    page.wait_for_timeout(100)
                if original.is_visible():
                    return 'failed'
            finally:
                original.dispose()
            clicked = True
            page.wait_for_timeout(300)
        return 'failed' if visible_banners(page) else 'accepted'
    except PlaywrightError:
        return 'failed'
