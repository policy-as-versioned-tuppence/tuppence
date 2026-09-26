#!/usr/bin/env python3
"""Observe the existing twin emitter; never emit a feed or choose an action.

Record first, sign only the observation lane, then gate the recorded outcome.
Exit3 remains could-not-look, and a changed valid render remains review-required:
this instrument supplies no new publishing contract (tickets28/64, ADR-0024).

Since eco-system ticket 143 the record is written for a WRITER to append: `record --handoff DIR`
puts the one line in DIR/observation.jsonl and touches no ledger, because the job that runs this
program holds `contents: read` and the job that appends runs no program at all. Without
`--handoff` the line is appended to observations/twin-sweep.jsonl as before, which is what `gate`
and the tests read.

A refused directory is not a move (ticket 143 item 5). The emitter's exit 1 is two different
readings: its own `--check` sentence, a render that MOVED and needs review; and an uncaught
exception, such as the loader's ModelError over a directory it refuses, which is a render that
could not be made at all. Until ticket 143 both were recorded as `moved: true`. Now only the
emitter's own sentence is a move; a traceback, a REFUSED line or any other exit 1 is recorded as
`could_not_render`, with `moved: null`, and the run stays non-green.
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
HANDOFF_FILE = 'observation.jsonl'
STATES = {0: 'unchanged', 1: 'review_required', 3: 'could_not_look'}
COULD_NOT_RENDER = 'could_not_render'
# The emitter's own --check sentence (twin/emit-forward-intel.py main(): "FAIL: <feed> is not
# what the overlay renders"). tests/test_twin_clock.py fails when the emitter no longer says it.
MOVED_SENTENCE = 'is not what the overlay renders'
TRACEBACK = 'Traceback (most recent call last):'


def classify(code: int, stdout: str, stderr: str) -> tuple[str, bool | None]:
    """(status, moved) for one emitter run. Exit 1 is a move only when the emitter said so."""
    if code in (0, 3):
        return STATES[code], (False if code == 0 else None)
    if code == 1:
        if TRACEBACK not in stderr and MOVED_SENTENCE in stdout:
            return STATES[1], True
        return COULD_NOT_RENDER, None
    return 'error', None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'gate'])
    parser.add_argument('--adopter-dir', type=Path, default=Path('.'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--at')
    parser.add_argument('--hub-ref')
    parser.add_argument('--adopter-ref')
    parser.add_argument('--handoff', type=Path,
                        help='write the one line to DIR/observation.jsonl for the writer job, and '
                             'leave the ledger alone')
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
        status, moved = classify(code, result.stdout, result.stderr)
        detail = '\n'.join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
        if moved:
            detail += '\nA changed render needs review; this clock has no authority to create a publishing contract.'
        elif status == COULD_NOT_RENDER:
            detail += ('\nThe emitter exited 1 without its own "moved" sentence, so this is a render that '
                       'could not be made, not a scenario that moved; nothing here is proposed.')
        record = {'swept_at': args.at, 'org': party, 'feed': 'forward-intel',
                  'run': args.run_id, 'status': status,
                  'emitter_exit': code, 'moved': moved,
                  'detail': detail, 'adopter_ref': args.adopter_ref,
                  'hub_ref': args.hub_ref, 'twin_pin': pin}
        encoded = json.dumps(record, sort_keys=True) + '\n'
        if args.handoff is not None:
            args.handoff.mkdir(parents=True, exist_ok=True)
            (args.handoff / HANDOFF_FILE).write_text(encoded)
        else:
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
