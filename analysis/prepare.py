import json
from pathlib import Path

import pandas as pd

from crawler_src.common import MODES, ReferenceData, atomic_json, hostname, read_json, validate_artifacts, sha256, validate_manifest_identity

VISIT_COLUMNS = ['site', 'country', 'mode', 'final_url', 'first_party_domain', 'request_count', 'consent_outcome']
REQUEST_COLUMNS = ['site', 'country', 'mode', 'final_url', 'url', 'hostname', 'domain', 'is_third_party', 'status', 'response_headers', 'categories', 'entities', 'session_replay']


def provenance(root, references):
    root = Path(root)
    return {'manifests': {mode: sha256(root / f'crawl_data_{mode}/manifest.json')
                         if (root / f'crawl_data_{mode}/manifest.json').exists() else None for mode in MODES},
            'reference_hashes': references.hashes, 'loader_hash': sha256(Path(__file__)),
            'classifier_hash': sha256(Path(__file__).parents[1] / 'crawler_src/common.py')}


def load_visit(metadata, har_path, references):
    if metadata['outcome'] != 'complete':
        raise ValueError('Only completed visits can enter the measurement dataset')
    first_party = references.domain(metadata['final_url'])
    identity = {'site': metadata['domain'], 'country': metadata['country'], 'mode': metadata['mode']}
    rows = []
    for entry in read_json(har_path)['log']['entries']:
        response = entry.get('response') or {}
        status = response.get('status', 0)
        if not isinstance(status, int) or not 100 <= status <= 599:
            continue
        url = entry['request']['url']
        if not url.startswith(('http://', 'https://')):
            continue
        host = hostname(url)
        domain = references.domain(url)
        rows.append({**identity, 'final_url': metadata['final_url'], 'url': url,
                     'hostname': host, 'domain': domain, 'is_third_party': domain != first_party,
                     'status': status, 'response_headers': response.get('headers', []),
                     **references.classify(host)})
    visit = {**identity, 'final_url': metadata['final_url'], 'first_party_domain': first_party,
             'request_count': len(rows), 'consent_outcome': metadata.get('consent_outcome', 'unknown')}
    return visit, rows


def prepare(root, references=None):
    root = Path(root)
    references = references or ReferenceData()
    visits, requests, coverage = [], [], {}
    for mode in MODES:
        directory = root / f'crawl_data_{mode}'
        manifest_path = directory / 'manifest.json'
        manifest = read_json(manifest_path) if manifest_path.exists() else {'visits': {}}
        if manifest_path.exists():
            validate_manifest_identity(manifest, mode)
        coverage[mode] = {'complete': 0, 'failed': 0, 'pending': 0}
        if manifest.get('identity', {}).get('reference_hashes', references.hashes) != references.hashes:
            raise ValueError(f'{mode}: reference data differs from the crawl')
        for domain, metadata in manifest['visits'].items():
            outcome = metadata['outcome']
            coverage[mode]['complete' if outcome == 'complete' else 'failed' if outcome == 'failed' else 'pending'] += 1
            if outcome != 'complete':
                continue
            validate_artifacts(directory, domain, mode, metadata['artifact_hashes'])
            visit, rows = load_visit(metadata, directory / f'{domain}.har', references)
            visits.append(visit)
            requests.extend(rows)
    output = root / 'analysis/output'
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(visits, columns=VISIT_COLUMNS).to_csv(output / 'visits.csv', index=False)
    frame = pd.DataFrame(requests, columns=REQUEST_COLUMNS)
    for column in ('response_headers', 'categories', 'entities'):
        frame[column] = frame[column].map(lambda value: json.dumps(value, ensure_ascii=False))
    frame.to_csv(output / 'requests.csv', index=False)
    atomic_json(output / 'coverage.json', coverage)
    atomic_json(output / 'provenance.json', provenance(root, references))
    return coverage
