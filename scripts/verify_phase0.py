"""Verify preserved LAK inputs and existing offline tests using stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or later is required')
    baseline = json.loads((ROOT / 'docs/baseline_files.json').read_text(encoding='utf-8'))
    mismatches = []
    for relative, digest in baseline.items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            mismatches.append(relative)
    syntax_errors = []
    for relative in baseline:
        if relative.endswith('.py'):
            try:
                path = ROOT / relative
                compile(path.read_bytes(), str(path), 'exec')
            except (SyntaxError, OSError) as exc:
                syntax_errors.append({'path': relative, 'error': str(exc)})
    run = subprocess.run(
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
         '-p', 'test_transform.py', '-v'],
        cwd=ROOT, capture_output=True, text=True,
    )
    sys.path.insert(0, str(ROOT))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('lak_original_relevance_tests', ROOT / 'tests/test_relevance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    relevance = []
    for name in sorted(n for n in vars(module) if n.startswith('test_') and callable(getattr(module, n))):
        try:
            getattr(module, name)()
            relevance.append({'test': name, 'passed': True})
        except Exception as exc:
            relevance.append({'test': name, 'passed': False, 'error': repr(exc)})
    passed = not mismatches and not syntax_errors and run.returncode == 0 and len(relevance) == 6 and all(r['passed'] for r in relevance)
    report = {
        'phase': 0, 'passed': passed,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'python': platform.python_version(), 'platform': platform.platform(),
        'baseline_file_count': len(baseline), 'baseline_mismatches': mismatches,
        'syntax_errors': syntax_errors,
        'unittest_returncode': run.returncode,
        'unittest_stdout': run.stdout, 'unittest_stderr': run.stderr,
        'relevance_checks': relevance,
        'not_tested': ['Docker runtime', 'PostgreSQL runtime', 'Airflow runtime',
                       'FastAPI runtime', 'MediaCloud live API', 'CDC', 'ML'],
    }
    print(run.stdout, end='')
    print(run.stderr, end='')
    print(json.dumps({k: v for k, v in report.items() if not k.startswith('unittest_')}, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PHASE 0 CHECKS PASSED' if passed else 'PHASE 0 CHECKS FAILED')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
