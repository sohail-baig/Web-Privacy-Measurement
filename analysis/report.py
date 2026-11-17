"""Build a PDF report (same text, tables and figures as report.ipynb) from the current analysis outputs.

Data-derived numbers are recomputed for every run; Q13 and the reference notes are fixed text.
"""

import base64
import csv
import html
from datetime import datetime
from pathlib import Path

import pandas as pd

from crawler_src.common import MODES, read_json
from analysis.questions import COUNTRY_ORDER, MODE_LABELS, header_values

ONES = ('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen '
        'sixteen seventeen eighteen nineteen').split()
TENS = ' ten twenty thirty forty fifty sixty seventy eighty ninety'.split(' ')
OUTCOME_LABELS = {'accepted': 'accepted', 'not_found': 'not found', 'failed': 'failed', 'not_attempted': 'untouched'}


def number_text(count, start=False):
    """Report style: numbers up to ten as words, larger as digits; spelled out (<100) at sentence start."""
    if count <= 10 or (start and count < 100):
        word = ONES[count] if count < 20 else TENS[count // 10] + (f'-{ONES[count % 10]}' if count % 10 else '')
        return word.capitalize() if start else word
    return f'{count:,}'


def join_words(items):
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


# --- Table and figure rendering, as in report.ipynb ---

def table_html(rows, label, caption):
    def row_html(row, tag):
        return '<tr>' + ''.join(f'<{tag}>{html.escape(str(cell))}</{tag}>' for cell in row) + '</tr>'

    header, *data = rows
    if not data:
        data = [['None observed'] + [''] * (len(header) - 1)]
    title = f'<b>Table {html.escape(label)}.</b> {html.escape(caption)}'
    return (f'<table><caption>{title}</caption><thead>{row_html(header, "th")}</thead><tbody>'
            + ''.join(row_html(row, 'td') for row in data) + '</tbody></table>')


def table_rows(key, kind, detail, output_dir):
    with (output_dir / f'{key}.csv').open(newline='', encoding='utf-8') as file:
        rows = list(csv.reader(file))
    if kind == 'summary':
        headers = [detail, 'Sites', 'All requests', 'Third-party requests',
                   'Third-party domains', 'Mapped third-party entities']
        return [headers] + [
            row[:2] + [' / '.join(value.removesuffix('.0') for value in row[i:i + 3]) for i in range(2, 14, 3)]
            for row in rows[1:]]
    if kind == 'rank':
        return [['Website', 'Tranco rank', 'Country', 'Third-party domains']] + [
            row[:2] + [row[2].upper(), row[3]] for row in rows[1:]]
    if detail:
        rows[0] = detail
    return rows


MISSING = '<p class="missing">Not generated in this run.</p>'


def show_table(output, key, label, caption, kind='table', detail=None):
    if not (output / f'{key}.csv').is_file():
        return f'<p><b>Table {html.escape(label)}.</b> {html.escape(caption)}</p>{MISSING}'
    return table_html(table_rows(key, kind, detail, output), label, caption)


def show_figure(output, key, label, caption):
    caption_html = f'<p class="caption"><b>Figure {html.escape(label)}.</b> {html.escape(caption)}</p>'
    file = output / f'{key}.png'
    if not file.is_file():
        return caption_html + MISSING
    image = base64.b64encode(file.read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{image}" alt="{html.escape(caption)}">{caption_html}</figure>'


def paragraphs(*texts):
    return ''.join(f'<p>{text}</p>' for text in texts)


# --- Numbers recomputed per run ---

def load_manifests(root):
    manifests = {}
    for mode in MODES:
        path = Path(root) / f'crawl_data_{mode}' / 'manifest.json'
        if path.is_file():
            manifests[mode] = read_json(path)
    return manifests


def design_text(manifests):
    tools = []
    for key, name in (('playwright_version', 'Playwright'), ('browser_version', 'headless Chromium')):
        versions = sorted({manifest['identity'].get(key) for manifest in manifests.values()} - {None})
        tools.append(f'{name} {" / ".join(versions)}' if versions else name)
    return f'Crawl using {tools[0]} and {tools[1]}.'


def coverage_table(coverage, visits, requests):
    rows = ['<tr><th>Mode</th><th>Completed</th><th>Consent outcome</th><th>Responses</th></tr>']
    for mode in MODES:
        counts = coverage.get(mode, {})
        attempted = sum(counts.values())
        if not attempted:
            continue
        outcomes = visits[visits['mode'] == mode]['consent_outcome'].value_counts()
        consent = ', '.join(f'{outcomes[key]} {label}' for key, label in OUTCOME_LABELS.items() if key in outcomes)
        rows.append(f'<tr><td>{MODE_LABELS[mode]}</td><td>{counts.get("complete", 0)} / {attempted}</td>'
                    f'<td>{html.escape(consent)}</td><td>{(requests["mode"] == mode).sum():,}</td></tr>')
    return ('<table><caption><b>Table 1.</b> Coverage, logged consent outcomes and received HTTP responses '
            'by mode.</caption>' + ''.join(rows) + '</table>')


# --- Fixed text (Q13 and reference notes) ---

Q13 = '''
<h3>Q13a. Most interesting observed difference</h3>
<p>Leaving cookie banners untouched still produced Advertising requests on 17 of 30 sites and Analytics requests on 18. Blocking reduced both counts to zero, although other third-party traffic remained.</p>
<h3>Q13b. A limitation and its effect</h3>
<p>Our consent handler could miss unfamiliar banners, so some “accept” visits may have run without consent being accepted. This could affect comparisons with Ignore mode.</p>
<h3>Q13c. Technical challenge and response</h3>
<p>Handling different cookie banners was the hardest part. We used English and Dutch button labels, checked iframes, and tested whether banners disappeared after clicking.</p>
<h3>Data and reference snapshots</h3>
<p>The report uses the prepared visits.csv and requests.csv, the Q1–Q12 outputs, and the archived Q12 DNS cache. Regenerating the analysis from those inputs and local references reproduced every result CSV and chart. Response counts were also reconciled to visits.csv by website and mode.</p>
'''

STYLE = '''
body { font-family: "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #111; }
h1 { font-size: 20pt; margin: 0 0 6pt; } h2 { font-size: 15pt; margin-top: 18pt; } h3 { font-size: 12pt; margin-top: 14pt; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0 12pt; break-inside: avoid; font-size: 9.5pt; }
caption { caption-side: top; text-align: left; padding-bottom: 4pt; }
th, td { text-align: left; padding: 3pt 6pt; border-bottom: 1px solid #ccc; } th { border-bottom: 1px solid #333; }
tbody tr:nth-child(odd) { background: #f5f5f5; }
figure { margin: 8pt 0 12pt; break-inside: avoid; } img { width: 440pt; max-width: 100%; }
.caption { margin-top: 2pt; } .missing { color: #a00; font-style: italic; }
'''


def report_html(root):
    output = Path(root) / 'analysis' / 'output'
    visits = pd.read_csv(output / 'visits.csv')
    requests = pd.read_csv(output / 'requests.csv')
    coverage = read_json(output / 'coverage.json')
    manifests = load_manifests(root)
    completed = {mode: int((visits['mode'] == mode).sum()) for mode in MODES}
    modes = [mode for mode in MODES if completed[mode]]
    per_mode = join_words([f'{MODE_LABELS[m]} ({completed[m]}{" visits" if i == 0 else ""})'
                           for i, m in enumerate(modes)])
    denominators = join_words([str(completed[m]) for m in modes])
    country_sites = {}
    for mode in ('desktop', 'ignore'):
        part = visits[visits['mode'] == mode]['country'].str.upper().value_counts()
        values = {int(part.get(c, 0)) for c in COUNTRY_ORDER}
        country_sites[mode] = (number_text(values.pop()), True) if len(values) == 1 else (
            ', '.join(f'{c} {int(part.get(c, 0))}' for c in COUNTRY_ORDER), False)
    desktop_n, desktop_equal = country_sites['desktop']
    ignore_n, ignore_equal = country_sites['ignore']
    mobile_first_party = requests[(requests['mode'] == 'mobile') & (requests['is_third_party'] == False)]
    senders = {site for site, headers in zip(mobile_first_party['site'], mobile_first_party['response_headers'])
               if header_values(headers, 'permissions-policy')}
    t, f = (lambda *a, **k: show_table(output, *a, **k)), (lambda *a: show_figure(output, *a))
    rank_cols = ['Rank', 'Third-party domain', 'Sites', 'Disconnect categories']
    cname_cols = ['First-party subdomain', 'CNAME target', 'Entity', 'Category']
    total_sites = visits['site'].nunique()

    body = [
        '<h1>Online Tracking and Privacy - Assignment 2</h1>',
        f'<p>A comparative measurement of {total_sites} university homepages across four browser configurations.</p>',
        '<h3>Measurement design</h3>',
        paragraphs(
            design_text(manifests) + ' Desktop used a 1366 × 768 viewport. Mobile emulated a Pixel 10. Both attempted '
            'to accept all cookies when a consent dialog was detected. Block used the desktop configuration and the '
            'same consent procedure, with Disconnect-based blocking for Advertising, Analytics, Social, '
            'FingerprintingInvasive and FingerprintingGeneral. Ignore used the desktop configuration and left consent untouched.',
            'The crawler waited 10 seconds after page load, handled consent where applicable, waited 5 seconds, '
            'scrolled, then waited 5 seconds before closing. Ignore skipped the consent interaction and its associated wait.'),
        coverage_table(coverage, visits, requests),

        '<h2>Request distributions</h2>', '<h3>Q1. Traffic per completed visit</h3>',
        paragraphs(f'Each plot uses {per_mode}. Boxes span the first and third quartiles, with the median marked '
                   'inside. Whiskers end at the furthest observations within 1.5 interquartile ranges of the box. '
                   'Circles mark observations beyond the whiskers. Completed visits with zero counts are included.'),
        f('q1_requests', 'Q1a', 'All received requests per completed website visit, grouped by crawl mode.'),
        f('q1_third_party_requests', 'Q1b', 'Received third-party requests per completed website visit, grouped by crawl mode.'),
        f('q1_third_party_domains', 'Q1c', 'Distinct third-party domains per completed website visit, grouped by crawl mode.'),
        f('q1_third_party_entities', 'Q1d', 'Distinct mapped third-party entities per completed website visit, grouped by crawl mode.'),
        '<h3>Q2. Summary by mode</h3>',
        t('q2', 'Q2', 'Minimum / median / maximum of each per-visit metric, grouped by crawl mode.', kind='summary', detail='Mode'),

        '<h2>Advertising and analytics</h2>', '<h3>Q3. Category prevalence by mode</h3>',
        f('q3_advertising', 'Q3a', f'Websites with at least one received Advertising response. '
          f'{join_words([MODE_LABELS[m] for m in modes])} denominators are {denominators}.'),
        f('q3_analytics', 'Q3b', f'Websites with at least one received Analytics response. '
          f'{join_words([MODE_LABELS[m] for m in modes])} denominators are {denominators}.'),
        paragraphs('Category counts include both first and third-party responses classified by Disconnect. Each '
                   'website is counted once per category within each group and may count in both categories.'),
        '<h3>Q4. Desktop summary by country</h3>',
        t('q4', 'Q4', f'Minimum / median / maximum of each per-visit metric for the {desktop_n} Desktop visits in each country.'
          if desktop_equal else f'Minimum / median / maximum of each per-visit metric for the Desktop visits in each country ({desktop_n}).',
          kind='summary', detail='Country'),
        '<h3>Q5. Category prevalence without consent interaction</h3>',
        f('q5_advertising', 'Q5a', 'Ignore websites with at least one received Advertising response, out of '
          + (f'{ignore_n} sampled sites per country.' if ignore_equal else f'the sampled sites per country ({ignore_n}).')),
        f('q5_analytics', 'Q5b', 'Ignore websites with at least one received Analytics response, out of '
          + (f'{ignore_n} sampled sites per country.' if ignore_equal else f'the sampled sites per country ({ignore_n}).')),

        '<h2>Third-party domain prevalence</h2>', '<h3>Q6. Domains exclusive to Desktop or Mobile</h3>',
        t('q6', 'Q6', 'Three most prevalent third-party domains seen exclusively in each mode across the completed '
          'visits. Sites counts distinct websites. Ties are ordered alphabetically by domain. '
          + (f'Desktop and Mobile each have {completed["desktop"]} visits.' if completed['desktop'] == completed['mobile']
             else f'Desktop has {completed["desktop"]} visits and Mobile has {completed["mobile"]}.'),
          detail=['Exclusive to', 'Third-party domain', 'Sites']),
        '<h3>Q7. Top domains by mode</h3>',
        paragraphs('The rankings count each website once per third-party domain. Ties are ordered alphabetically by '
                   'domain. Categories are the union of labels observed for that domain in the mode. NA indicates '
                   'that no category was assigned in those observations.'),
        *[t(f'q7_{mode}', f'Q7{letter}', f'{MODE_LABELS[mode]} mode. Ten most prevalent third-party domains by number '
            f'of websites, out of {completed[mode]} completed visits.' + (' NA indicates no observed category.' if letter in 'cd' else ''),
            detail=rank_cols) + ('<h2>Domain rankings</h2><h3>Q7. Top domains by mode (continued)</h3>' if letter == 'b' else '')
          for mode, letter in zip(MODES, 'abcd')],

        '<h3>Q8. Desktop extremes and popularity</h3>',
        t('q8_highest_desktop', 'Q8a', 'Three Desktop websites with the most distinct third-party domains. Tranco ranks '
          'are dated 14 November 2026. Ties are ordered alphabetically.', kind='rank'),
        t('q8_lowest_desktop', 'Q8b', 'Three Desktop websites with the fewest distinct third-party domains. Tranco ranks '
          'are dated 14 November 2026. Ties are ordered alphabetically.', kind='rank'),

        '<h2>Session replay and response policies</h2>', '<h3>Q9. Requests to session replay domains</h3>',
        t('q9', 'Q9', 'Website–domain pairs with a received response from a domain flagged for session replay by '
          'Disconnect. Modes list where each pair was observed. The flag identifies the domain and cannot establish '
          'whether replay code ran.', detail=['Website', 'Country', 'Session replay domain', 'Observed modes']),
        '<h3>Q10. Explicitly disabled permissions</h3>',
        t('q10', 'Q10', 'Five most frequently disabled permissions among Mobile first-party responses. Each site is '
          'counted once per permission with an explicit empty allowlist. '
          f'{number_text(len(senders), start=True)} of {completed["mobile"]} completed Mobile visits received a '
          'first-party Permissions-Policy header.', detail=['Permission', 'Sites disabling', 'Sites sending header']),
        '<h3>Q11. Effective no-referrer policy</h3>',
        t('q11', 'Q11', 'Desktop websites with at least one first-party response whose effective Referrer-Policy was '
          'no-referrer. The response count uses the last recognized token across repeated headers and comma-separated '
          'fallback values.', detail=['Website', 'Country', 'Qualifying responses']),
        paragraphs('Q10 and Q11 measure headers on individual first-party responses, including subresources and '
                   'redirects. Their counts describe the presence of these headers in the captured traffic.'),

        '<h2>CNAME matches</h2>', '<h3>Q12. First-party aliases to listed domains</h3>',
        *[t(f'q12_{mode}', f'Q12{letter}', f'{MODE_LABELS[mode]} mode. First-party request subdomains whose cached '
            'CNAME chains contained a target matched to a Disconnect service.', detail=cname_cols)
          for mode, letter in zip(MODES, 'abcd')],

        '<h2>Discussion and reproducibility</h2>', Q13,
    ]
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>Assignment 2 report</title>'
            f'<style>{STYLE}</style></head><body>{"".join(body)}</body></html>')


def build_report(root):
    """Write analysis/output/reports/report_<UTC timestamp>.pdf for this run and return its path."""
    from playwright.sync_api import sync_playwright

    reports = Path(root) / 'analysis' / 'output' / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f'report_{datetime.now():%Y%m%d-%H%M%S}.pdf'
    document = report_html(root)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(document, wait_until='load')
        page.pdf(path=str(path), format='A4', print_background=True,
                 margin={'top': '18mm', 'bottom': '18mm', 'left': '18mm', 'right': '18mm'},
                 display_header_footer=True, header_template='<span></span>',
                 footer_template='<div style="font-size:8pt;width:100%;text-align:center">'
                                 '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        browser.close()
    return path


assert number_text(7, start=True) == 'Seven' and number_text(30, start=True) == 'Thirty' and number_text(48) == '48'
