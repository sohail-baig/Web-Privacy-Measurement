"""Check assignment readiness and build the exact required submission layout."""
import argparse
from pathlib import Path
import re
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from crawler_src.common import ROOT, MODES, ReferenceData, read_json, read_sites, sha256, validate_artifacts, required_artifacts, validate_manifest_identity
from analysis.prepare import provenance
from report.render import report_inputs


def check_submission(root):
    root = Path(root)
    issues = []
    try:
        sites = read_sites(root / 'sites.csv')
        if len(sites) != 30 or {s.country for s in sites} != {'nl','uk','us'}:
            issues.append('sites.csv must contain 30 distinct sites covering NL, UK and US')
    except (OSError, ValueError) as exc:
        sites = []
        issues.append(f'sites.csv: {exc}')
    try:
        refs = ReferenceData(root / 'crawler_src/reference_data')
    except (OSError, ValueError, KeyError) as exc:
        refs = None
        issues.append(f'Reference inputs: {exc}')
    for mode in MODES:
        directory = root / f'crawl_data_{mode}'
        try:
            manifest = read_json(directory / 'manifest.json')
            validate_manifest_identity(manifest, mode)
            if set(manifest['visits']) != {s.domain for s in sites}:
                issues.append(f'{mode}: manifest does not match sites.csv')
            if refs and manifest['identity']['reference_hashes'] != refs.hashes:
                issues.append(f'{mode}: reference snapshots differ from crawl')
            for site in sites:
                visit = manifest['visits'].get(site.domain, {})
                if visit.get('outcome') != 'complete' or visit.get('country') != site.country:
                    issues.append(f'{mode}/{site.domain}: incomplete visit or wrong country')
                    continue
                validate_artifacts(directory, site.domain, mode, visit['artifact_hashes'])
                if mode != 'ignore' and visit.get('consent_outcome') not in ('accepted','not_found'):
                    issues.append(f'{mode}/{site.domain}: invalid consent outcome')
        except (OSError, ValueError, KeyError) as exc:
            issues.append(f'{mode}: {exc}')
    output = root / 'analysis/output'
    try:
        if refs and read_json(output / 'provenance.json') != provenance(root, refs):
            issues.append('Prepared data is stale: rerun preparation and all questions')
    except (OSError, ValueError, KeyError) as exc:
        issues.append(f'Prepared data provenance: {exc}')
    try:
        completion = read_json(output / 'completion.json')
        for number in range(1,13):
            entry = completion.get(str(number))
            if not entry:
                issues.append(f'Q{number}: not completed')
                continue
            if entry['code_hash'] != sha256(root / 'analysis/questions.py'):
                issues.append(f'Q{number}: analysis code changed; rerun')
            for name in ('visits.csv','requests.csv','coverage.json','provenance.json'):
                if entry['input_hashes'].get(name) != sha256(output / name):
                    issues.append(f'Q{number}: prepared data changed; rerun')
            if not entry['outputs']:
                issues.append(f'Q{number}: no outputs')
            for name, digest in entry['outputs'].items():
                path = (output / name).resolve()
                if not path.is_relative_to(output.resolve()) or sha256(path) != digest:
                    issues.append(f'Q{number}: missing or modified output {name}')
    except (OSError, ValueError, KeyError) as exc:
        issues.append(f'Q1–Q12 completion evidence: {exc}')
    try:
        build = read_json(root / 'report/build.json')
        if build['draft']:
            issues.append('report.pdf is a draft: replace all TODO sections, including Q13, then render again')
        if build['html_hash'] != sha256(root / 'report/template.html') or build['pdf_hash'] != sha256(root / 'report.pdf'):
            issues.append('report.pdf is stale or modified; render again')
        if build.get('input_hashes') != report_inputs(root):
            issues.append('report.pdf is stale: analysis results or local report assets changed; render again')
        with (root / 'report.pdf').open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                issues.append('report.pdf has an invalid signature')
    except (OSError, ValueError, KeyError) as exc:
        issues.append(f'report.pdf/build evidence: {exc}')
    for name in ('requirements.txt','crawler_src/README.md'):
        if not (root / name).is_file():
            issues.append(f'Missing {name}')
    return issues


def submission_files(root):
    root = Path(root)
    yield root / 'report.pdf', 'report.pdf'
    yield root / 'requirements.txt', 'requirements.txt'
    yield root / 'sites.csv', 'sites.csv'
    if (root / 'README.md').is_file():
        yield root / 'README.md', 'README.md'
    # Include the report build sources and entrypoint with the analysis source.
    yield root / 'submission.py', 'submission.py'
    for folder in ('crawler_src', 'analysis', 'report', 'tests'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and not any(part in ('__pycache__', '.staging', '.venv') or part.startswith('.') for part in path.relative_to(root).parts):
                yield path, path.relative_to(root).as_posix()
    for mode in MODES:
        directory = root / f'crawl_data_{mode}'
        manifest = read_json(directory / 'manifest.json')
        yield directory / 'manifest.json', f'crawl_data_{mode}/manifest.json'
        for domain, metadata in manifest['visits'].items():
            for name in required_artifacts(domain, mode):
                path = directory / name
                yield path, path.relative_to(root).as_posix()


def package_submission(root, group_name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,79}', group_name):
        raise ValueError('Group name must contain only letters, numbers, spaces, hyphens or underscores')
    issues = check_submission(root)
    if issues:
        raise ValueError('Submission is not ready:\n- ' + '\n- '.join(issues))
    target = Path(root) / f'{group_name}.zip'
    if target.exists():
        raise ValueError(f'Archive already exists: {target}; move it before packaging again')
    with ZipFile(target, 'x', compression=ZIP_DEFLATED) as archive:
        for path, name in submission_files(root):
            archive.write(path, name)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--package', metavar='GROUP_NAME')
    args = parser.parse_args(argv)
    try:
        if args.package:
            print(package_submission(args.root, args.package))
            return 0
        issues = check_submission(args.root)
        print('\n'.join('- ' + issue for issue in issues) if issues else 'Submission structure is ready. Review scientific results and PDF manually before upload.')
        return 1 if issues else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
