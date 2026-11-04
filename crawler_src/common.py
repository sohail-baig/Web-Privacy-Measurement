"""Shared input, reference data and artifact contracts (no online lookups)."""
import csv
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import tldextract
import requests
from requests_file import FileAdapter

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = Path(__file__).resolve().parent / 'reference_data'
MODES = ('desktop', 'mobile', 'block', 'ignore')
BLOCK_CATEGORIES = frozenset(('Advertising', 'Analytics', 'Social', 'FingerprintingInvasive', 'FingerprintingGeneral'))


@dataclass(frozen=True)
class Site:
    domain: str
    country: str
    university: str = ''


def read_sites(path):
    sites, seen = [], set()
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        for number, row in enumerate(csv.reader(stream), 1):
            if not row or all(not value.strip() for value in row):
                continue
            if number == 1 and [s.strip().lower() for s in row[:2]] == ['domain', 'country']:
                continue
            if len(row) not in (2, 3):
                raise ValueError(f'{path}:{number}: expected domain,country[,university]')
            domain, country = row[0].strip().lower(), row[1].strip().lower()
            try:
                domain = domain.encode('idna').decode('ascii')
            except UnicodeError as exc:
                raise ValueError(f'Invalid domain at line {number}') from exc
            labels = domain.split('.')
            if len(domain) > 253 or len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
                raise ValueError(f'Invalid domain at line {number}: {domain}')
            if country not in ('nl', 'uk', 'us'):
                raise ValueError(f'Invalid country at line {number}: {country}')
            if domain in seen:
                raise ValueError(f'Duplicate site: {domain}')
            seen.add(domain)
            sites.append(Site(domain, country, row[2].strip() if len(row) == 3 else ''))
    if not sites:
        raise ValueError('Site list is empty')
    return sites


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hostname(value):
    host = urlsplit(value if '://' in value else '//' + value).hostname or ''
    return host.rstrip('.').lower().encode('idna').decode('ascii')


def suffixes(host):
    parts = hostname(host).split('.')
    return ['.'.join(parts[index:]) for index in range(len(parts))]


def close_psl_response(response, *args, **kwargs):
    # tldextract reads response.text without closing the file:// response.
    try:
        response.content
    finally:
        response.close()
    return response


class ReferenceData:
    def __init__(self, directory=REFERENCE_DIR):
        directory = Path(directory).resolve()
        records = read_json(directory / 'sources.json')
        self.hashes = {}
        for name in ('services.json', 'entities.json', 'public_suffix_list.dat'):
            path = directory / name
            actual = sha256(path)
            record = next((r for r in records if Path(r['path']).name == name), None)
            if not record or actual != record['sha256']:
                raise ValueError(f'Reference checksum mismatch: {name}')
            self.hashes[name] = actual
        self.extract = tldextract.TLDExtract(
            cache_dir=None, suffix_list_urls=((directory / 'public_suffix_list.dat').as_uri(),),
            fallback_to_snapshot=False, include_psl_private_domains=True,
        )
        with requests.Session() as session:
            session.mount('file://', FileAdapter())
            session.hooks['response'].append(close_psl_response)
            self.extract('example.com', session=session)
        self.categories, self.entities, self.replay = {}, {}, set()
        services = read_json(directory / 'services.json')['categories']
        if not BLOCK_CATEGORIES <= services.keys():
            raise ValueError('Disconnect file is missing required blocking categories')
        for category, companies in services.items():
            for company in companies:
                for details in company.values():
                    replay = str(details.get('session-replay', '')).lower() == 'true'
                    for key, domains in details.items():
                        if not key.startswith(('http://', 'https://')):
                            continue
                        if not isinstance(domains, list):
                            raise ValueError(f'Invalid Disconnect domains for {key}')
                        for value in domains:
                            host = hostname(value)
                            self.categories.setdefault(host, set()).add(category)
                            if replay:
                                self.replay.add(host)
        for entity, details in read_json(directory / 'entities.json')['entities'].items():
            for value in details.get('properties', []) + details.get('resources', []):
                self.entities.setdefault(hostname(value), set()).add(entity)

    def domain(self, value):
        host = hostname(value)
        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            result = self.extract(host)
            return result.top_domain_under_public_suffix or host

    def classify(self, host):
        categories, entities, replay = set(), set(), False
        for suffix in suffixes(host):
            categories.update(self.categories.get(suffix, ()))
            entities.update(self.entities.get(suffix, ()))
            replay |= suffix in self.replay
        return {'categories': sorted(categories), 'entities': sorted(entities), 'session_replay': replay}

    def blocked(self, url):
        return bool(BLOCK_CATEGORIES.intersection(self.classify(hostname(url))['categories']))


def required_artifacts(domain, mode):
    names = [f'{domain}.har', f'{domain}_pre_consent.png', f'{domain}.webm']
    if mode != 'ignore':
        names.append(f'{domain}_post_consent.png')
    return names


def validate_manifest_identity(manifest, mode):
    if manifest.get('identity', {}).get('mode') != mode:
        raise ValueError(f'{mode}: manifest identity does not match its crawl folder')
    for domain, visit in manifest['visits'].items():
        if visit.get('domain') != domain or visit.get('mode') != mode:
            raise ValueError(f'{mode}/{domain}: visit identity does not match its manifest')
        if hostname(domain) != domain or any(char in domain for char in '/\\:'):
            raise ValueError(f'{mode}: invalid domain identity')
        if visit.get('country') not in ('nl','uk','us'):
            raise ValueError(f'{mode}/{domain}: invalid country identity')


def validate_artifacts(directory, domain, mode, expected_hashes=None):
    directory = Path(directory)
    hashes = {}
    for name in required_artifacts(domain, mode):
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Missing or empty artifact: {path}')
        if path.suffix == '.har':
            if not isinstance(read_json(path).get('log', {}).get('entries'), list):
                raise ValueError(f'Invalid HAR: {path}')
        else:
            with path.open('rb') as stream:
                signature = stream.read(8)
            expected = b'\x89PNG\r\n\x1a\n' if path.suffix == '.png' else b'\x1a\x45\xdf\xa3'
            if not signature.startswith(expected):
                raise ValueError(f'Invalid artifact signature: {path}')
        hashes[name] = sha256(path)
        if expected_hashes is not None and expected_hashes.get(name) != hashes[name]:
            raise ValueError(f'Artifact checksum mismatch: {name}')
    return hashes
