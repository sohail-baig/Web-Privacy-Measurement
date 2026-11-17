import argparse
from pathlib import Path
import sys

from crawler_src.common import ROOT, atomic_json, read_json, sha256
from analysis.prepare import prepare
from analysis.questions import QUESTIONS
from analysis.report import build_report


def execute_question(number, root):
    output = (Path(root) / 'analysis/output').resolve()
    for name in ('visits.csv', 'requests.csv', 'coverage.json', 'provenance.json'):
        if not (output / name).is_file():
            raise ValueError('Run python -m analysis.run --prepare first')
    paths = QUESTIONS[number](Path(root))
    if not paths:
        raise ValueError(f'Q{number} produced no artifacts')
    hashes = {}
    for path in paths:
        path = Path(path).resolve()
        if not path.is_relative_to(output) or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Q{number}: expected a nonempty file inside {output}: {path}')
        hashes[path.relative_to(output).as_posix()] = sha256(path)
    completion_path = output / 'completion.json'
    completion = read_json(completion_path) if completion_path.exists() else {}
    completion[str(number)] = {'outputs': hashes, 'input_hashes': {
        name: sha256(output / name) for name in ('visits.csv','requests.csv','coverage.json','provenance.json')},
        'code_hash': sha256(Path(__file__).with_name('questions.py'))}
    atomic_json(completion_path, completion)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prepare received-response data or run one assignment question.')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--question', type=int, nargs='+', choices=range(1,13))
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        if args.prepare:
            print(prepare(args.root))
        else:
            for number in args.question:
                print(f"Running question {number}...")
                execute_question(number, args.root)
                print(f"Question {number} completed successfully.")
            print(f'Report written to {build_report(args.root)}')
        return 0
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
