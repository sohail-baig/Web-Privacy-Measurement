"""Render the local report template to an A4 PDF; no external resources allowed."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright
from crawler_src.common import ROOT, atomic_json, sha256


def report_inputs(root):
    root = Path(root)
    files = {}
    for folder in ('report', 'analysis/output'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and path.name != 'build.json' and '__pycache__' not in path.parts:
                files[path.relative_to(root).as_posix()] = sha256(path)
    return files


def render_report(root=ROOT):
    root = Path(root).resolve()
    source = root / 'report/template.html'
    target = root / 'report.pdf'
    temporary = root / 'report.pending.pdf'
    inputs = report_inputs(root)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route('http://**/*', lambda route: route.abort())
            page.route('https://**/*', lambda route: route.abort())
            page.goto(source.as_uri(), wait_until='load')
            page.evaluate('document.fonts.ready')
            for number in range(1,14):
                if page.locator(f'#q{number}').count() != 1:
                    raise ValueError(f'Report needs exactly one Q{number} section')
            draft = page.locator('[data-draft="true"], .todo').count() > 0
            page.pdf(path=str(temporary), format='A4', print_background=True,
                     prefer_css_page_size=True, display_header_footer=True,
                     header_template='<span></span>',
                     footer_template='<div style="font-size:9px;color:#667085;width:100%;text-align:center">Online Tracking &amp; Privacy · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        finally:
            browser.close()
    if report_inputs(root) != inputs:
        raise ValueError('Report inputs changed while rendering; rerun')
    temporary.replace(target)
    atomic_json(root / 'report/build.json', {'draft':draft, 'html_hash':sha256(source), 'pdf_hash':sha256(target), 'input_hashes':inputs})
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(render_report(args.root))


if __name__ == '__main__':
    main()
