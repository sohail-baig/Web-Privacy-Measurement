"""Sequential Chromium crawler with atomic completion and explicit consent gate."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time
import uuid

# Support the assignment's direct-script command as well as python -m.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright
from crawler_src import consent
from crawler_src.common import (ROOT, MODES, ReferenceData, atomic_json, read_json,
                                read_sites, required_artifacts, sha256, validate_artifacts, validate_manifest_identity)

SETTINGS = {'load_timeout_ms': 60000, 'before_consent_ms': 10000, 'after_consent_ms': 5000,
            'after_scroll_ms': 5000, 'scroll_pause_ms': 250, 'scroll_limit_seconds': 30,
            'viewport': {'width': 1366, 'height': 768}, 'locale': 'en-GB',
            'timezone_id': 'Europe/Amsterdam', 'service_workers': 'block'}


def now():
    return datetime.now(timezone.utc).isoformat()


def preflight(mode):
    if mode not in MODES:
        raise ValueError(f'Invalid crawl mode: {mode}')
    if mode != 'ignore' and not consent.IMPLEMENTED:
        raise NotImplementedError('Consent handling is unfinished: implement crawler_src/consent.py before accept-consent crawls.')


def context_options(mode, devices, staging):
    options = {'viewport': SETTINGS['viewport'].copy()}
    if mode == 'mobile':
        if 'Pixel 10' not in devices:
            raise ValueError('Installed Playwright has no Pixel 10 descriptor; install the pinned requirements. No substitute is allowed.')
        options = dict(devices['Pixel 10'])
        if options.pop('default_browser_type', 'chromium') != 'chromium':
            raise ValueError('Pixel 10 must use Chromium')
    options.update(locale=SETTINGS['locale'], timezone_id=SETTINGS['timezone_id'],
                   service_workers=SETTINGS['service_workers'], record_video_dir=str(staging),
                   record_video_size=options['viewport'].copy(), record_har_mode='full',
                   record_har_content='embed')
    return options


def scroll_page(page):
    deadline = time.monotonic() + SETTINGS['scroll_limit_seconds']
    unchanged = 0
    previous = page.evaluate('window.scrollY')
    while time.monotonic() < deadline:
        page.mouse.wheel(0, page.viewport_size['height'])
        page.wait_for_timeout(SETTINGS['scroll_pause_ms'])
        position, bottom = page.evaluate('[window.scrollY, window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2]')
        unchanged = unchanged + 1 if position == previous else 0
        if bottom or unchanged >= 3:
            return
        previous = position


def perform_steps(page, url, domain, mode, staging, handler):
    page.goto(url, wait_until='load', timeout=SETTINGS['load_timeout_ms'])
    page.wait_for_timeout(SETTINGS['before_consent_ms'])
    page.screenshot(path=str(staging / f'{domain}_pre_consent.png'), full_page=False)
    outcome = 'not_attempted'
    if mode != 'ignore':
        outcome = handler(page)
        if outcome not in ('accepted', 'not_found', 'failed'):
            raise ValueError('Consent handler must return accepted, not_found or failed')
        page.wait_for_timeout(SETTINGS['after_consent_ms'])
        page.screenshot(path=str(staging / f'{domain}_post_consent.png'), full_page=False)
    scroll_page(page)
    page.wait_for_timeout(SETTINGS['after_scroll_ms'])
    if outcome == 'failed':
        raise ValueError('Consent interaction failed; diagnostic artifacts retained, visit is not complete')
    return outcome


def collect_visit(browser, devices, site, mode, staging, references, handler, url=None):
    options = context_options(mode, devices, staging)
    options['record_har_path'] = str(staging / f'{site.domain}.har')
    context = browser.new_context(**options)
    blocked = []
    page = None
    try:
        def route_request(route):
            if mode == 'block' and references.blocked(route.request.url):
                blocked.append(route.request.url)
                route.abort('blockedbyclient')
            else:
                route.continue_()
        # Routing in every mode keeps its cache effects consistent.
        context.route('**/*', route_request)
        page = context.new_page()
        video = page.video
        outcome = perform_steps(page, url or f'https://{site.domain}/', site.domain, mode, staging, handler)
        metadata = {'final_url': page.url, 'consent_outcome': outcome, 'blocked_request_count': len(blocked)}
    finally:
        try:
            atomic_json(staging / 'diagnostics.json', {'final_url': page.url if page else None,
                                                       'blocked_urls': blocked})
        finally:
            context.close()
    video_path = Path(video.path())
    video_path.replace(staging / f'{site.domain}.webm')
    return metadata


def run_identity(mode, sites, references, browser_version):
    site_data = [asdict(site) for site in sites]
    source_hashes = {name: sha256(Path(__file__).with_name(name)) for name in ('crawl.py','common.py','consent.py')}
    return {'mode': mode, 'site_list_hash': hashlib.sha256(json.dumps(site_data, sort_keys=True).encode()).hexdigest(),
            'settings': SETTINGS, 'reference_hashes': references.hashes,
            'code_hashes': source_hashes, 'playwright_version': version('playwright'),
            'browser_version': browser_version}


def crawl_sites(browser, devices, sites, mode, output_root, references, handler=None):
    if handler is None:
        preflight(mode)
        handler = consent.accept_consent
    directory = Path(output_root) / f'crawl_data_{mode}'
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / 'manifest.json'
    identity = run_identity(mode, sites, references, browser.version)
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        validate_manifest_identity(manifest, mode)
        if manifest['identity'] != identity:
            raise ValueError('Existing crawl is incompatible with the current sites, settings, code or references. Use a new --output-root.')
    else:
        manifest = {'schema_version': 1, 'identity': identity, 'visits': {
            site.domain: {**asdict(site), 'mode': mode, 'outcome': 'pending', 'attempts': []} for site in sites}}
    for site in sites:
        record = manifest['visits'][site.domain]
        if record['outcome'] == 'complete':
            validate_artifacts(directory, site.domain, mode, record['artifact_hashes'])
            print(f'Skip completed: {mode} {site.domain}')
            continue
        attempt_id = uuid.uuid4().hex
        staging = directory / '.staging' / attempt_id
        staging.mkdir(parents=True)
        attempt = {'id': attempt_id, 'started_at': now(), 'outcome': 'running',
                   'staging': staging.relative_to(directory).as_posix()}
        for old in record['attempts']:
            if old['outcome'] == 'running':
                old['outcome'] = 'interrupted'
        record['attempts'].append(attempt)
        record.update(outcome='running', requested_url=f'https://{site.domain}/')
        atomic_json(manifest_path, manifest)
        try:
            metadata = collect_visit(browser, devices, site, mode, staging, references, handler)
            hashes = validate_artifacts(staging, site.domain, mode)
            for name in required_artifacts(site.domain, mode):
                (staging / name).replace(directory / name)
            record.update(metadata, outcome='complete', artifact_hashes=hashes,
                          artifacts=required_artifacts(site.domain, mode))
            attempt.update(outcome='complete', finished_at=now())
        except BaseException as exc:
            attempt.update(outcome='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                           finished_at=now(), error=f'{type(exc).__name__}: {exc}')
            record['outcome'] = 'failed'
            atomic_json(staging / 'failure.json', attempt)
            if not isinstance(exc, Exception):
                atomic_json(manifest_path, manifest)
                raise
            print(f'Failed: {mode} {site.domain}: {exc}', file=sys.stderr)
        atomic_json(manifest_path, manifest)
    outcomes = [record['outcome'] for record in manifest['visits'].values()]
    return {'complete': outcomes.count('complete'), 'failed': outcomes.count('failed'),
            'pending': sum(value not in ('complete', 'failed') for value in outcomes)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', required=True, choices=MODES)
    parser.add_argument('-l', required=True, type=Path)
    parser.add_argument('--output-root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        preflight(args.m)
        sites = read_sites(args.l)
        references = ReferenceData()
        with sync_playwright() as playwright:
            # Validate the mobile preset before opening a browser.
            context_options(args.m, playwright.devices, args.output_root)
            browser = playwright.chromium.launch(headless=True)
            try:
                summary = crawl_sites(browser, playwright.devices, sites, args.m, args.output_root, references)
            finally:
                browser.close()
        print(json.dumps(summary))
        return 0 if summary['failed'] == summary['pending'] == 0 else 1
    except KeyboardInterrupt:
        print('Interrupted. Restart the same command to resume.', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
