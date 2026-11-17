"""Build a PDF report (same text, tables and figures as report.ipynb) from the current analysis outputs.

Data-derived numbers are recomputed for every run; Q13 and the reference notes are fixed text.
"""

import base64
import csv
import html
import json
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


def day_text(moment):
    return f'{moment.day} {moment:%B %Y}'


def time_window(stamps):
    """'on 16 November 2026, between 16:47 and 18:05 UTC' (or with both dates when the window spans days)."""
    first, last = min(stamps), max(stamps)
    if first.date() == last.date():
        return f'on {day_text(first)}, between {first:%H:%M} and {last:%H:%M} UTC'
    return f'between {day_text(first)} {first:%H:%M} and {day_text(last)} {last:%H:%M} UTC'


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


def design_text(manifests, visits):
    countries = visits.drop_duplicates('site')['country'].str.upper().value_counts()
    counts = [(number_text(int(countries.get(c, 0))), c) for c in COUNTRY_ORDER]
    if len({count for count, _ in counts}) == 1:
        sample = (f'The sample comprised {counts[0][0]} universities each from the Netherlands (NL), '
                  'United Kingdom (UK) and United States (US).')
    else:
        sample = ('The sample comprised ' + join_words([f'{n} universities from {name} ({c})' for (n, c), name in
                  zip(counts, ('the Netherlands', 'the United Kingdom', 'the United States'))]) + '.')
    stamps = [datetime.fromisoformat(attempt[key]) for manifest in manifests.values()
              for record in manifest['visits'].values() for attempt in record['attempts']
              for key in ('started_at', 'finished_at') if attempt.get(key)]
    tools = []
    for key, name in (('playwright_version', 'Playwright'), ('browser_version', 'headless Chromium')):
        versions = sorted({manifest['identity'].get(key) for manifest in manifests.values()} - {None})
        tools.append(f'{name} {" / ".join(versions)}' if versions else name)
    when = f' took place {time_window(stamps)},' if stamps else ''
    return (f'{sample} Crawl attempts{when} using {tools[0]} and {tools[1]}. The crawler used fresh contexts, '
            'an en-GB locale, the Europe/Amsterdam browser time zone and blocked service workers.')


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


def failure_text(manifests, coverage, visits):
    sentences = []
    for mode in MODES:
        failed = coverage.get(mode, {}).get('failed', 0)
        if not failed:
            continue
        records = [(site, record['attempts'][-1].get('error', '') if record['attempts'] else '')
                   for site, record in manifests.get(mode, {}).get('visits', {}).items() if record['outcome'] == 'failed']
        label = MODE_LABELS[mode]
        if records:
            for site, error in records:
                how = 'failed during consent interaction' if 'Consent interaction failed' in error else 'failed'
                sentences.append(f'The {label} visit to {site} {how} and was excluded.')
            missing = {record['country'].upper() for site, record in manifests[mode]['visits'].items()
                       if record['outcome'] == 'failed'}
            completed = visits[visits['mode'] == mode]['country'].str.upper().value_counts()
            sentences.append(f'{label} therefore includes ' + join_words(
                [f'{number_text(int(completed.get(c, 0)))} {c} sites' for c in COUNTRY_ORDER if c in missing]) + '.')
        else:
            sentences.append(f'{number_text(failed, start=True)} {label} visit{"s" if failed > 1 else ""} '
                             f'failed and {"were" if failed > 1 else "was"} excluded.')
    sentences.append('“Not found” is the crawler’s recorded outcome for consent detection.')
    return ' '.join(sentences)


def rules_text(requests):
    third_party = requests[requests['is_third_party'] == True]
    mapped = int(third_party['entities'].map(lambda value: bool(json.loads(value))).sum())
    share = f' ({mapped / len(third_party):.1%})' if len(third_party) else ''
    return (f'The analysis covers {len(requests):,} HTTP(S) requests with a recorded response status of 100–599, '
            'including redirects and HTTP errors. Each response’s registrable domain (eTLD+1) was compared with the '
            'final page’s registrable domain using the local Public Suffix List, including its private section. '
            f'Of {len(third_party):,} third-party responses, {mapped:,}{share} had at least one mapped entity. '
            'Unmapped entities contributed zero to the distinct-entity count.')


def dns_text(output, requests):
    cache = read_json(output / 'dns_cache.json') if (output / 'dns_cache.json').is_file() else {}
    first_party = requests[requests['is_third_party'] == False].dropna(subset=['hostname'])
    hosts = {host.lower().rstrip('.') for host, domain in zip(first_party['hostname'], first_party['domain'])
             if host.lower().rstrip('.').endswith('.' + str(domain))}  # subdomains only, as Q12 queries them
    results = [result for host, result in cache.items() if host in hosts]
    if not results:
        return 'No cached CNAME lookups were available for this run.'
    stamps = [datetime.fromisoformat(result['queried_at_utc']) for result in results]
    first, last = min(stamps), max(stamps)
    chains = sum(result['status'] == 'ok' for result in results)
    none = sum(result['status'] == 'no_cname' for result in results)
    failures = len(results) - chains - none
    when = (f'on {day_text(first)}, {first:%H:%M:%S}–{last:%H:%M:%S} UTC' if first.date() == last.date()
            else f'between {day_text(first)} {first:%H:%M:%S} and {day_text(last)} {last:%H:%M:%S} UTC')
    failed = ('The cache recorded no lookup failures.' if not failures
              else f'The cache recorded {number_text(failures)} lookup failure{"s" if failures > 1 else ""}.')
    return (f'The analysis followed cached CNAME chains for {number_text(len(results))} distinct observed first-party '
            f'request subdomains. Lookups were made {when}. {number_text(chains, start=True)} lookups returned a chain '
            f'and {number_text(none)} returned no CNAME. {failed} Each distinct matching target, entity and category '
            'combination is listed by crawl mode.')


# --- Fixed text (Q13 and reference notes) ---

Q13 = '''
<h3>Q13a. Most interesting observed difference</h3>
<p>Leaving consent untouched still exposed a substantial part of the university sample to requests in two measured categories. In Ignore, 17 of 30 sites contacted Advertising domains and 18 of 30 contacted Analytics domains, compared with 24 and 27 in Desktop. Block returned zero in both categories (Q3), yet the median Block visit still received 21.5 third-party responses (Q2). The categories covered by the blocking rules therefore explain only part of the third-party traffic observed across the four modes. The Adobe Analytics match behind smetrics.nottingham.ac.uk in Block (Q12) also shows why inspecting DNS can reveal connections hidden by a comparison of registrable domains alone. A listed alias establishes a DNS association, with the purpose of the individual request left unresolved.</p>
<h3>Q13b. A limitation and its effect</h3>
<p>The mode comparisons use one completed visit per site and mode, with Ignore run earlier than the other configurations and with a shorter observation sequence. Timing and the shorter window could affect which requests are captured, so the observed differences cannot be attributed solely to consent interaction. The failed Nottingham Mobile visit also matters for Q6 because Nottingham led Desktop with 35 distinct third-party domains. A repeat using the same 30 sites in every mode could change which domains appear exclusive to Desktop or Mobile.</p>
<h3>Q13c. Technical challenge and response</h3>
<p>One challenge documented in the collection records was distinguishing a completed visit from one with incomplete consent handling. The crawler retained diagnostic artifacts for the failed Nottingham Mobile visit and the preparation step excluded it from the completed dataset. This avoided treating the failure as a zero-traffic observation, while leaving the Mobile coverage gap explicit.</p>
<h3>Data and reference snapshots</h3>
<p>The report uses the prepared visits.csv and requests.csv, the Q1–Q12 outputs, and the archived Q12 DNS cache. Regenerating the analysis from those inputs and local references reproduced every result CSV and chart. Response counts were also reconciled to visits.csv by website and mode.</p>
<p>Reference sources were the instructor-supplied university list, Disconnect services revision a277cd6, Disconnect entity map revision cb1b0c1, and the local Public Suffix List snapshot retrieved 3 November 2026. Q8 uses the local Tranco extract dated 14 November 2026. The extract does not record a list ID or retrieval date. Q12 DNS was queried after the crawl, so the saved answers may differ from the records present during collection.</p>
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
            design_text(manifests, visits),
            'Desktop used a 1366 × 768 viewport. Mobile emulated a Pixel 10. Both attempted to accept all cookies when '
            'a consent dialog was detected. Block used the desktop configuration and the same consent procedure, with '
            'Disconnect-based blocking for Advertising, Analytics, Social, FingerprintingInvasive and '
            'FingerprintingGeneral. Ignore used the desktop configuration and left consent untouched.',
            'The crawler waited 10 seconds after page load, handled consent where applicable, waited 5 seconds, '
            'scrolled, then waited 5 seconds before closing. Ignore skipped the consent interaction and its associated wait.'),
        coverage_table(coverage, visits, requests),
        paragraphs(failure_text(manifests, coverage, visits)),
        '<h3>Analysis rules</h3>', paragraphs(rules_text(requests)),

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
        paragraphs('Category counts include both first- and third-party responses classified by Disconnect. Each '
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
          f'Desktop has {completed["desktop"]} visits and Mobile has {completed["mobile"]}.',
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
        paragraphs(dns_text(output, requests)),
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
