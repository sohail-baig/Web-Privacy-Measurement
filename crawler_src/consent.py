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
    r'^\s*(accept|allow|agree to|enable)\s+all(?:\s+[\w ,-]*?cookies)?[.!]?\s*$|'
    r'^\s*(alles accepteren|alles toestaan|alle cookies accepteren|alle cookies toestaan|'
    r'accepteer alle cookies|accepteer alles|sta alles toe)[.!]?\s*$|'
    # Tiered prompts (Essential / Standard / Complete) name their full-consent level "Complete".
    r'^\s*complete\b.*\bcookies\b', re.I)
ACCEPT = re.compile(r'^\s*(accept(?: cookies)?|allow cookies|i agree|agree|i accept(?: all)?(?: cookies)?|'
                    r'accept recommended(?: settings| cookies)?|i[\'’]?m (?:ok|okay|happy) with (?:that|this)|'
                    r'akkoord|ik ga akkoord|accepteren|toestaan)[.!]?\s*$', re.I)
KNOWN_ACCEPT = '#onetrust-accept-btn-handler, #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, #didomi-notice-agree-button'
# One evaluation per frame: CMPs nest dozens of cookie-classed elements, and a round trip
# per element exceeded the 12 s budget on mobile pages.
BANNERS = '''(scopes, consent) => scopes.flatMap((e, index) => {
    if (["HTML","BODY","A","BUTTON","INPUT"].includes(e.tagName)) return [];
    const box = e.getBoundingClientRect();
    if (!box.width || !box.height || getComputedStyle(e).visibility === "hidden") return [];
    // Prompts appear on screen; a static cookie notice deep in the footer is not one.
    if (box.bottom <= 0 || box.right <= 0 || box.top >= innerHeight || box.left >= innerWidth) return [];
    const selector = 'button, [role="button"], input, a';
    const controls = [...e.querySelectorAll(selector), ...(e.shadowRoot ? e.shadowRoot.querySelectorAll(selector) : [])];
    if (!controls.length) return [];
    // Rendered text only: an emptied wrapper or "Cookie settings" launcher left after
    // acceptance keeps hidden consent copy but is not an active prompt.
    let explanation = e.innerText;
    controls.forEach(control => { explanation = explanation.replace(control.innerText, ''); });
    return new RegExp(consent, "i").test(explanation) ? [[index, e.innerText.length]] : [];
})'''


def visible_banners(page):
    """CSS locators traverse open shadow roots; inspect frames separately."""
    banners = []
    for frame in page.frames:
        if frame.is_detached():
            continue
        scopes = frame.locator(SCOPES)
        banners += [(length, scopes.nth(index)) for index, length in scopes.evaluate_all(BANNERS, CONSENT_TEXT.pattern)]
    # Prefer the dialog itself over a persistent outer wrapper.
    return [scope for _, scope in sorted(banners, key=lambda banner: banner[0])]


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
            button = control.element_handle(timeout=500)
            if original is None or button is None:
                return 'failed'
            try:
                # Banners that slide in after an earlier one closes need time to settle.
                control.click(timeout=min(5000, max(1, (deadline - time.monotonic()) * 1000)))
                dismissed_by = min(deadline, time.monotonic() + 2.5)
                # Some CMP wrappers stay rendered (empty) after acceptance; the re-scan
                # below still requires that no active prompt remains.
                while original.is_visible() and button.is_visible() and time.monotonic() < dismissed_by:
                    page.wait_for_timeout(100)
                if original.is_visible() and button.is_visible():
                    return 'failed'
            finally:
                original.dispose()
                button.dispose()
            clicked = True
            page.wait_for_timeout(300)
        return 'failed' if visible_banners(page) else 'accepted'
    except PlaywrightError:
        return 'failed'
