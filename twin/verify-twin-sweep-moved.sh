#!/usr/bin/env bash
# Observe both halves of the TU/LU observation-only moved path (tickets64/72/143).
# Execute ONLY jobs.twin.steps[id=observe]'s own shell on disposable source copies.
# Offline handoffs are labelled fixtures, never live observations. The live half
# reads committed history; no genuine moved witness remains SKIP, not PASS.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
HUB=""
d="$HERE"
while [ "$d" != / ]; do
  if [ -f "$d/twin/repo.py" ] && [ -f "$d/clone-estate.sh" ]; then HUB="$d"; break; fi
  d="$(dirname "$d")"
done
[ -n "$HUB" ] || { echo 'SKIP: no twin hub checkout above the adopter'; exit 3; }
PY="$HUB/.venv/bin/python"
[ -x "$PY" ] || PY=python3
"$PY" -c 'import yaml' 2>/dev/null || { echo 'SKIP: the selected Python lacks PyYAML'; exit 3; }
HUB="$HUB" REPO="$REPO" "$PY" - <<'PYTHON'
import ast
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import yaml

HUB, REPO = (Path(os.environ[k]) for k in ('HUB', 'REPO'))
RESULTS = []
SHA = re.compile(r'[0-9a-f]{40}')
MOVED = 'is not what the overlay renders'
KEYS = {'swept_at', 'org', 'feed', 'run', 'status', 'emitter_exit', 'moved',
        'detail', 'adopter_ref', 'hub_ref', 'twin_pin'}


def note(status, detail):
    RESULTS.append(status)
    print(f'{status}: {detail}', flush=True)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   stderr=subprocess.PIPE, text=True).strip()


def read_step():
    doc = yaml.safe_load((REPO / '.github/workflows/twin-sweep.yml').read_text())
    job = doc['jobs']['twin']
    require(job.get('permissions') == {'contents': 'read'}, 'twin job must retain contents: read only')
    steps = [s for s in job['steps'] if s.get('id') == 'observe']
    require(len(steps) == 1 and isinstance(steps[0].get('run'), str),
            'expected exactly one read-job observe step with a run shell')
    script = steps[0]['run']
    # Execute the extracted shell, never a retyped recorder command. Restrict its
    # syntax to the existing observation-only contract before executing anything.
    lines = script.strip().splitlines()
    require(lines[0].strip() == 'set -euo pipefail', 'observe must retain its bash-e boundary')
    command = ' '.join(line.strip().removesuffix('\\') for line in lines[1:])
    expected = r'''python3 .github/scripts/twin-sweep.py record --at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --run-id "$GITHUB_RUN_ID" --hub-ref "$(git -C "$GITHUB_WORKSPACE/hub" rev-parse HEAD)" --adopter-ref "$(git rev-parse HEAD)" --handoff "${HANDOFF}"'''
    require(shlex.split(command) == shlex.split(expected),
            'observe must be only the existing record --handoff command and actual source refs')
    return script


def selected_feed():
    tree = ast.parse((REPO / 'twin/emit-forward-intel.py').read_text())
    versions = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in n.targets)
                and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
    require(len(versions) == 1 and re.fullmatch(r'[1-9][0-9]*\.[0-9]+\.[0-9]+', versions[0]),
            'emitter must declare one literal semantic VERSION')
    path = Path('twin/forward-intel') / ('v' + versions[0].split('.')[0]) / 'feed.json'
    require((REPO / path).is_file(), f'selected emitter feed is absent: {path}')
    return path


def live_witnesses(party):
    path = REPO / 'observations/twin-sweep.jsonl'
    if not path.is_file():
        return []
    raw = path.read_bytes()
    committed = subprocess.check_output(['git', '-C', str(REPO), 'show',
                                         'HEAD:observations/twin-sweep.jsonl'], stderr=subprocess.PIPE)
    require(raw == committed, 'observation ledger differs from committed history')
    require(not raw or raw.endswith(b'\n'), 'observation ledger lacks its final newline')
    witnesses = []
    for number, line in enumerate(raw.decode().splitlines(), 1):
        try:
            rec = json.loads(line)
            require(isinstance(rec, dict) and set(rec) == KEYS, 'record keys')
            require(rec['org'] == party and rec['feed'] == 'forward-intel', 'party/feed')
            require(isinstance(rec['run'], str) and re.fullmatch(r'[1-9][0-9]*', rec['run']), 'run id')
            require(isinstance(rec['swept_at'], str) and rec['swept_at'].endswith('Z'), 'UTC swept_at')
            datetime.fromisoformat(rec['swept_at'].replace('Z', '+00:00'))
            require(all(isinstance(rec[k], str) and SHA.fullmatch(rec[k])
                        for k in ('adopter_ref', 'hub_ref')), 'actual source refs')
            require(isinstance(rec['twin_pin'], dict), 'recorded pin shape')
            # Early real non-moved observations predate full-commit PINs. Their
            # actual historical source is authoritative; do not impose today's
            # shape on them or silently turn an unanchored move into proof.
            if 'hub_commit' in rec['twin_pin']:
                require(rec['twin_pin']['hub_commit'] == rec['hub_ref'], 'pin/source agreement')
            code, moved, status, detail = (rec[k] for k in ('emitter_exit', 'moved', 'status', 'detail'))
            require(type(code) is int and isinstance(detail, str), 'typed emitter reading')
            expected = {0: ('unchanged', False), 3: ('could_not_look', None)}.get(code)
            if code == 1:
                is_move = MOVED in detail and 'Traceback (most recent call last):' not in detail
                expected = ('review_required', True) if is_move else ('could_not_render', None)
            require(expected is not None and status == expected[0] and moved is expected[1],
                    'contradictory status/emitter_exit/moved reading')
            source = subprocess.run(['git', '-C', str(REPO), 'show',
                                     rec['adopter_ref'] + ':twin/PIN.yaml'],
                                    capture_output=True, text=True)
            if source.returncode != 0:
                note('SKIP', f'observation line {number}: historical source PIN unavailable '
                     f'at {rec["adopter_ref"]}; no witness inferred')
                continue
            source_pin = yaml.safe_load(source.stdout)
            require(source_pin == rec['twin_pin'], 'recorded pin differs from the actual adopter source')
            if moved is True:
                if rec['twin_pin'].get('hub_commit') != rec['hub_ref']:
                    note('SKIP', f'observation line {number} moved but lacks a full historical hub PIN anchor')
                else:
                    witnesses.append(rec)
        except (ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
            raise ValueError(f'observation line {number}: {exc}') from exc
    return witnesses


def offline_cases(script, party, feed):
    with tempfile.TemporaryDirectory(prefix='.sweep-moved-', dir=HUB) as tmp:
        work = Path(tmp)
        # The enclosing primary may be newer than this adopter's authenticated
        # clock pin. Select its actual existing source object without requiring
        # HEAD==PIN and without silently running a newer clock implementation.
        pin = yaml.safe_load((REPO / 'twin/PIN.yaml').read_text())
        pinned = str(pin['hub_commit'])
        require(SHA.fullmatch(pinned), 'PIN must name a full actual hub commit')
        clock_hub = work / 'hub'
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(HUB), str(clock_hub)],
                       check=True, capture_output=True, text=True, timeout=30)
        subprocess.run(['git', '-C', str(clock_hub), 'switch', '--detach', pinned],
                       check=True, capture_output=True, text=True, timeout=20)
        print(f'INPUT: enclosing hub {git(HUB, "rev-parse", "HEAD")}; '
              f'clock PIN source {git(clock_hub, "rev-parse", "HEAD")}', flush=True)
        estate = clock_hub / '.estate-clone'
        estate.mkdir(exist_ok=True)
        feeds = HUB / '.estate-clone/feeds'
        if feeds.is_dir():
            subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(feeds), str(estate / 'feeds')],
                           check=True, capture_output=True, text=True, timeout=30)
        tools = work / 'tools'
        tools.mkdir()
        (tools / 'python3').symlink_to(sys.executable)
        cases = [('fresh selected feed', None, 'unchanged', 0, False),
                 ('stale selected feed', 'stale', 'review_required', 1, True),
                 ('missing ladder', 'missing', 'could_not_look', 3, None),
                 ('refused world pin', 'refused', 'could_not_render', 1, None)]
        for retained in sorted((REPO / 'twin/forward-intel').glob('v*/feed.json')):
            relative = retained.relative_to(REPO)
            if relative != feed:
                cases.append((f'stale retained {retained.parent.name} feed', relative,
                              'unchanged', 0, False))
        for index, (label, mutation, status, code, moved) in enumerate(cases):
            plant = estate / f'case-{index}' / party
            plant.parent.mkdir()
            subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(REPO), str(plant)],
                           check=True, capture_output=True, text=True, timeout=30)
            if mutation == 'stale':
                with (plant / feed).open('a') as stream:
                    stream.write('\n')
            elif mutation == 'missing':
                (plant / 'twin/ladder.yaml').unlink()
            elif mutation == 'refused':
                meta = plant / 'twin/orgs' / party / 'meta.yaml'
                doc = yaml.safe_load(meta.read_text())
                doc['world_ref'] = 'refused'
                meta.write_text(yaml.safe_dump(doc))
            elif isinstance(mutation, Path):
                with (plant / mutation).open('a') as stream:
                    stream.write('\n')
            handoff, output = work / f'handoff-{index}', work / f'output-{index}'
            output.write_text('')
            ledger = plant / 'observations/twin-sweep.jsonl'
            ledger_before = ledger.read_bytes() if ledger.is_file() else None
            env = dict(os.environ, HANDOFF=str(handoff), GITHUB_OUTPUT=str(output),
                       GITHUB_WORKSPACE=str(work), GITHUB_RUN_ID='offline-moved-instrument-fixture',
                       PYTHONDONTWRITEBYTECODE='1', PATH=str(tools) + os.pathsep + os.environ.get('PATH', ''))
            done = subprocess.run(['bash', '-e', '-c', script], cwd=plant, env=env,
                                  capture_output=True, text=True, timeout=60)
            try:
                rows = (handoff / 'observation.jsonl').read_text().splitlines()
                require(len(rows) == 1, 'expected exactly one handoff row')
                rec = json.loads(rows[0])
                require(done.returncode == 0, f'record shell exit {done.returncode}')
                require(rec['status'] == status and type(rec['emitter_exit']) is int
                        and rec['emitter_exit'] == code and rec['moved'] is moved,
                        f'expected {status}/exit{code}/moved={moved}; got {rec}')
                require(rec['run'] == env['GITHUB_RUN_ID'] and rec['org'] == party
                        and rec['adopter_ref'] == git(plant, 'rev-parse', 'HEAD')
                        and rec['hub_ref'] == pinned, 'handoff source/run provenance')
                require((ledger.read_bytes() if ledger.is_file() else None) == ledger_before,
                        'read job changed its source observation ledger')
                require(output.read_text() == 'recorded=true\n', 'recorded handoff output missing')
                note('PASS', f'{label}: actual read-job shell recorded {status}/exit{code}/moved={moved}')
            except (OSError, ValueError, KeyError, TypeError) as exc:
                note('FAIL', f'{label}: {exc}; shell said {(done.stdout + done.stderr)[-1000:]}')


def main():
    try:
        script = read_step()
        party = yaml.safe_load((REPO / 'party.yaml').read_text())['party']
        witnesses = live_witnesses(party)
        offline_cases(script, party, selected_feed())
        if witnesses:
            first = witnesses[0]
            note('PASS', f'committed moved path observed {len(witnesses)} time(s); first '
                 f'{first["swept_at"]}, run {first["run"]}, adopter {first["adopter_ref"]}')
        else:
            note('SKIP', 'no committed moved:true witness in observations/twin-sweep.jsonl; '
                 'offline fixtures are not a live clock firing')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        note('FAIL', str(exc))
    code = 1 if 'FAIL' in RESULTS else 3 if 'SKIP' in RESULTS else 0
    print(f'TOTAL: {RESULTS.count("PASS")} pass, {RESULTS.count("FAIL")} fail, '
          f'{RESULTS.count("SKIP")} could-not-look')
    print(('FAIL: moved-path assertion observed false' if code == 1 else
           'SKIP: offline moved-path assertions passed; no committed moved:true witness' if code == 3 else
           'PASS: offline moved-path assertions and committed live witness observed'))
    return code


raise SystemExit(main())
PYTHON
