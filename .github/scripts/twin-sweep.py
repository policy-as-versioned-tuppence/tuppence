#!/usr/bin/env python3
"""Observe the existing twin emitter; never emit a feed or choose an action.

Record first, sign only the observation lane, then gate the recorded outcome.
Exit3 remains could-not-look, and a changed valid render remains review-required:
this instrument supplies no new publishing contract (tickets28/64, ADR-0024).
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

LEDGER = Path('observations/twin-sweep.jsonl')
STATES = {0: 'unchanged', 1: 'review_required', 3: 'could_not_look'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'gate'])
    parser.add_argument('--adopter-dir', type=Path, default=Path('.'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--at')
    parser.add_argument('--hub-ref')
    parser.add_argument('--adopter-ref')
    args = parser.parse_args()
    root = args.adopter_dir.resolve()
    target = root / LEDGER
    try:
        if args.command == 'gate':
            record = json.loads(target.read_text().splitlines()[-1])
            if record['run'] != args.run_id:
                raise ValueError('the last observation belongs to another run')
            print(f"{record['status']}: {record['detail']}")
            code = record['emitter_exit']
            return code if code in STATES else 1
        if not args.at or not args.at.endswith('Z'):
            raise ValueError('--at must be the UTC observation time ending in Z')
        datetime.fromisoformat(args.at.replace('Z', '+00:00'))
        for label, ref in [('hub', args.hub_ref), ('adopter', args.adopter_ref)]:
            if not ref or not re.fullmatch(r'[a-f0-9]{40}', ref):
                raise ValueError(f'--{label}-ref must be the actual checked-out commit SHA')
        party = yaml.safe_load((root / 'party.yaml').read_text())['party']
        pin = yaml.safe_load((root / 'twin/PIN.yaml').read_text())
        result = subprocess.run([sys.executable, str(root / 'twin/emit-forward-intel.py'), '--check'],
                                cwd=root, capture_output=True, text=True)
        code = result.returncode
        detail = '\n'.join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
        if code == 1:
            detail += '\nA changed render needs review; this clock has no authority to create a publishing contract.'
        record = {'swept_at': args.at, 'org': party, 'feed': 'forward-intel',
                  'run': args.run_id, 'status': STATES.get(code, 'error'),
                  'emitter_exit': code, 'moved': (code == 1) if code in (0, 1) else None,
                  'detail': detail, 'adopter_ref': args.adopter_ref,
                  'hub_ref': args.hub_ref, 'twin_pin': pin}
        encoded = json.dumps(record, sort_keys=True) + '\n'
        if target.exists() and target.stat().st_size:
            with target.open('rb') as stream:
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b'\n':
                    raise ValueError('observation ledger lacks a final newline; refusing to repair history')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('a') as stream:
            stream.write(encoded)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('recorded=true\n')
        print(encoded, end='')
        return 0
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f'REFUSED: twin observation: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
