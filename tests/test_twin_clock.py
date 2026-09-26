"""The clock records real emitter outcomes; a read-only twin job hands them to a writer that
appends only what it has validated (tickets 28/64; eco-system ticket 143, ADR-0031 point 4).

Run: python3 -m unittest discover -s tests -p test_twin_clock.py

The workflow is graded as GitHub reads it (parsed, never grepped, except for the version comment
beside each pinned `uses:`, which YAML drops), and the writer's own validation and cage shells are
run here as an adversary: every wrong handoff refused by name, every declaration kept out.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / '.github/scripts/twin-sweep.py'
WORKFLOW = ROOT / '.github/workflows/twin-sweep.yml'
EMITTER = ROOT / 'twin/emit-forward-intel.py'
PIN = ROOT / 'twin/PIN.yaml'
REQUIREMENTS = ROOT / '.github/requirements/twin-sweep.txt'
GITSIGN_ACTION = ROOT / '.github/actions/install-gitsign/action.yml'
HUB = 'policy-as-versioned-flux/policy-as-versioned-flux'
SHA = re.compile(r'^[0-9a-f]{40}$')
PINNED_USES = re.compile(r'^\s*-?\s*uses:\s*(\S+?)@([0-9a-f]{40})\s+#\s*v\d+(?:\.\d+)*\s*$')
INERT = ('actions/checkout', 'actions/upload-artifact', 'actions/download-artifact')
# The shape the hub's verify/schedules/schedules.py reads a `run:` with for programs it cannot
# read (python, bash, sh, npx, node, ./x). The writer stays inline shell by test, not by promise.
PROGRAM = re.compile(
    r"(?m)(?:^|(?<=[;&|]))\s*(?:(?:if|then|else|do|!|-)\s+)*(?:[A-Za-z_][\w]*=\S*\s+)*"
    r"(?:(?:python3?|bash|sh|npx|node)\s+[^\n|;&]*|\./[^\s|;&]+[^\n|;&]*)")
COMMENT = re.compile(r'(?m)^\s*#[^\n]*\n?')
CONTINUED = re.compile(r'\\\n\s*')
CAGE_SHELL = ('git reset', 'OBSERVATION_LANE', 'git add', 'git diff --cached --name-only', 'exit 1')
MOVED_SENTENCE = 'is not what the overlay renders'


def _steps(job):
    return job['steps']


def _step(job, **needle):
    key, value = next(iter(needle.items()))
    found = [s for s in _steps(job) if value in str(s.get(key, ''))]
    assert len(found) == 1, (needle, [s.get('name') for s in found])
    return found[0]


def _index(job, **needle):
    return _steps(job).index(_step(job, **needle))


def _fixture_repo(temp):
    root = Path(temp)
    (root / 'twin').mkdir()
    (root / 'party.yaml').write_text('party: fixture\n')
    (root / 'twin/PIN.yaml').write_text('twin_version: 0.1.0\ntag_cut: false\nhub_commit: ' + 'a' * 40 + '\n')
    return root


def _record(root, run_id, handoff=None):
    command = [sys.executable, str(HELPER), 'record', '--adopter-dir', str(root),
               '--at', '2026-09-10T00:00:00Z', '--run-id', run_id, '--hub-ref', 'a' * 40, '--adopter-ref', 'b' * 40]
    if handoff is not None:
        command += ['--handoff', str(handoff)]
    # bash -e must not swallow the exit3 observation before it is written.
    return subprocess.run(['bash', '-e', '-c', shlex.join(command)], capture_output=True, text=True)


class TwinClock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.doc = yaml.safe_load(cls.text)
        cls.party = yaml.safe_load((ROOT / 'party.yaml').read_text())['party']
        cls.twin = cls.doc['jobs']['twin']
        cls.write = cls.doc['jobs']['write']
        cls.pin = yaml.safe_load(PIN.read_text())

    # --- the record ------------------------------------------------------------------------------
    def test_check_outcomes_are_appended_before_the_gate_and_never_emit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = _fixture_repo(temp)
            emitter = root / 'twin/emit-forward-intel.py'
            ledger = root / 'observations/twin-sweep.jsonl'
            previous = b''
            for code, status in [(0, 'unchanged'), (1, 'review_required'), (3, 'could_not_look')]:
                said = {0: 'ok  fixture render matches', 1: 'FAIL: fixture ' + MOVED_SENTENCE,
                        3: 'CANNOT LOOK: fixture missing instrument'}[code]
                emitter.write_text(f'import sys\nassert sys.argv[1:] == ["--check"]\nprint({said!r})\nraise SystemExit({code})\n')
                run_id = f'fixture-{code}'
                result = _record(root, run_id)
                self.assertEqual(result.returncode, 0, result.stderr)
                content = ledger.read_bytes()
                self.assertTrue(content.startswith(previous))
                record = json.loads(content.splitlines()[-1])
                self.assertEqual(record['status'], status)
                self.assertEqual(record['emitter_exit'], code)
                self.assertEqual(record['moved'], {0: False, 1: True, 3: None}[code])
                if code == 3:
                    self.assertIn('missing instrument', record['detail'])
                self.assertEqual(record['twin_pin']['hub_commit'], 'a' * 40)
                self.assertFalse((root / 'twin/forward-intel/v1/feed.json').exists())
                gate = subprocess.run([sys.executable, str(HELPER), 'gate', '--adopter-dir', str(root),
                                       '--run-id', run_id], capture_output=True, text=True)
                self.assertEqual(gate.returncode, code, gate.stderr)
                previous = content

    def test_a_refused_directory_is_not_a_move(self):
        """Ticket 143 item 5: the loader's ModelError leaves the emitter at exit 1 with a traceback,
        and so does a REFUSED line. Neither is a render that moved; both are a render that could
        not be made, recorded as such, and the run stays non-green (gate exit 1)."""
        self.assertIn(MOVED_SENTENCE, EMITTER.read_text(),
                      'the helper keys on the emitter\'s own --check sentence; the emitter must still say it')
        cases = {
            'a loader ModelError': 'import sys\nclass ModelError(RuntimeError): pass\n'
                                   'raise ModelError("twin/orgs/fixture: refused directory")\n',
            'a REFUSED line': 'import sys\nsys.exit("REFUSED: twin/PIN.yaml pins twin 0.1.0 and the package is 0.2.0")\n',
            'the sentence inside a traceback': 'import sys\nprint("FAIL: x ' + MOVED_SENTENCE + '")\n'
                                               'raise RuntimeError("and then it fell over")\n',
            'a bare exit 1': 'import sys\nraise SystemExit(1)\n',
        }
        with tempfile.TemporaryDirectory() as temp:
            root = _fixture_repo(temp)
            emitter = root / 'twin/emit-forward-intel.py'
            ledger = root / 'observations/twin-sweep.jsonl'
            for n, (why, body) in enumerate(cases.items()):
                emitter.write_text(body)
                result = _record(root, f'fixture-render-{n}')
                self.assertEqual(result.returncode, 0, (why, result.stderr))
                record = json.loads(ledger.read_bytes().splitlines()[-1])
                self.assertEqual(record['status'], 'could_not_render', why)
                self.assertEqual(record['emitter_exit'], 1, why)
                self.assertIsNone(record['moved'], why)
                self.assertIn('could not be made', record['detail'], why)
                self.assertNotIn('needs review', record['detail'], why)
                gate = subprocess.run([sys.executable, str(HELPER), 'gate', '--adopter-dir', str(root),
                                       '--run-id', f'fixture-render-{n}'], capture_output=True, text=True)
                self.assertEqual(gate.returncode, 1, why)
                self.assertTrue(gate.stdout.startswith('could_not_render: '), (why, gate.stdout))

    def test_record_hands_off_one_line_and_leaves_the_ledger_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            root = _fixture_repo(temp)
            (root / 'twin/emit-forward-intel.py').write_text('import sys\nprint("CANNOT LOOK: fixture")\nraise SystemExit(3)\n')
            handoff = Path(temp) / 'handoff'
            result = _record(root, 'fixture-handoff', handoff)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / 'observations').exists(), 'the twin job writes no ledger; the writer appends')
            lines = (handoff / 'observation.jsonl').read_text()
            self.assertEqual(lines.count('\n'), 1)
            self.assertTrue(lines.endswith('\n'))
            record = json.loads(lines)
            self.assertEqual((record['run'], record['status'], record['moved']), ('fixture-handoff', 'could_not_look', None))
            self.assertEqual(result.stdout, lines)

    # --- the pin ----------------------------------------------------------------------------------
    def test_pin_names_a_full_hub_commit_and_the_twin_job_checks_the_hub_out_at_it(self):
        self.assertRegex(str(self.pin['hub_commit']), SHA)
        self.assertEqual(self.pin['tag_cut'], False)
        self.assertNotIn('ref: main', self.text, 'the hub is never checked out at a branch')
        self.assertEqual(sorted(self.doc['jobs']), ['twin', 'write'])
        self.assertEqual(self.doc['permissions'], {'contents': 'read'})
        self.assertEqual(self.twin['permissions'], {'contents': 'read'})
        checkouts = [s for s in _steps(self.twin) if str(s.get('uses', '')).startswith('actions/checkout@')]
        hub = [s for s in checkouts if s.get('with', {}).get('repository') == HUB]
        own = [s for s in checkouts if 'repository' not in s.get('with', {})]
        self.assertEqual((len(hub), len(own), len(checkouts)), (1, 1, 2))
        self.assertEqual(hub[0]['with']['ref'], '${{ steps.pin.outputs.hub_commit }}')
        self.assertEqual(hub[0]['with']['fetch-depth'], 1)
        self.assertEqual(hub[0]['with']['path'], 'hub')
        self.assertIs(hub[0]['with']['persist-credentials'], False)
        self.assertIs(own[0]['with']['persist-credentials'], False)
        self.assertEqual(own[0]['with']['path'], 'adopter')
        self.assertLess(_steps(self.twin).index(own[0]), _index(self.twin, id='pin'))
        self.assertLess(_index(self.twin, id='pin'), _steps(self.twin).index(hub[0]))
        checkout = f'hub/.estate-clone/{self.party}'
        self.assertEqual(self.twin['defaults']['run']['working-directory'], checkout)
        mover = _step(self.twin, run=f'mv adopter {checkout}')
        self.assertIn('rev-parse HEAD', mover['run'])
        self.assertIn('HUB_COMMIT', mover['run'])
        observe = _step(self.twin, id='observe')
        self.assertIn('--hub-ref', observe['run'])
        self.assertIn('--adopter-ref', observe['run'])
        self.assertIn('--handoff', observe['run'])
        shell = '\n'.join(str(s.get('run', '')) for s in _steps(self.twin))
        self.assertNotIn('git push', shell)
        self.assertNotIn('gh pr', shell)
        self.assertNotIn('gitsign', shell, 'the twin job signs nothing')
        upload = _step(self.twin, uses='actions/upload-artifact@')
        self.assertEqual(upload['with']['name'], 'twin-sweep-handoff')
        self.assertEqual(upload['with']['if-no-files-found'], 'error')

    def test_pin_step_reads_the_same_commit_yaml_reads_and_refuses_a_bad_pin(self):
        shell = _step(self.twin, id='pin')['run']

        def run(pin_text):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / 'twin').mkdir()
                (Path(tmp) / 'twin/PIN.yaml').write_text(pin_text)
                out = Path(tmp) / 'out'
                out.write_text('')
                done = subprocess.run(['bash', '-e', '-c', shell], cwd=tmp, capture_output=True, text=True,
                                      env=dict(os.environ, GITHUB_OUTPUT=str(out)))
                return done.returncode, out.read_text().strip(), done.stdout + done.stderr

        rc, output, _ = run(PIN.read_text())
        self.assertEqual(rc, 0)
        self.assertEqual(output, f"hub_commit={self.pin['hub_commit']}")
        for bad, why in ((PIN.read_text() + 'hub_commit: ' + 'b' * 40 + '\n', 'two hub_commit lines'),
                         (PIN.read_text().replace(self.pin['hub_commit'], 'abc123'), 'a short sha'),
                         (PIN.read_text().replace(self.pin['hub_commit'], 'main'), 'a branch name'),
                         ('twin_version: 0.1.0\n', 'no hub_commit at all')):
            rc, output, said = run(bad)
            self.assertNotEqual(rc, 0, why)
            self.assertEqual(output, '', why)
            self.assertIn('::error::', said, why)

    # --- the network dial ---------------------------------------------------------------------------
    def test_every_download_is_pinned_by_hash(self):
        uses = [line for line in self.text.splitlines() if re.match(r'^\s*-?\s*uses:', line)]
        self.assertGreaterEqual(len(uses), 5)
        for line in uses:
            m = PINNED_USES.match(line)
            self.assertIsNotNone(m, f'not pinned to a full commit with its version beside it: {line.strip()}')
            self.assertIn(m.group(1), INERT, line)
        pip = [s for s in _steps(self.twin) if 'pip install' in str(s.get('run', ''))]
        self.assertEqual(len(pip), 1)
        self.assertIn('--require-hashes -r .github/requirements/twin-sweep.txt', pip[0]['run'])
        self.assertNotIn('pip install', '\n'.join(str(s.get('run', '')) for s in _steps(self.write)))
        lines = [l.strip() for l in REQUIREMENTS.read_text().splitlines() if l.strip() and not l.startswith('#')]
        self.assertRegex(lines[0], r'^pyyaml==\d+\.\d+\.\d+ \\$')
        self.assertGreaterEqual(len(lines), 2)
        for h in lines[1:]:
            self.assertRegex(h, r'^--hash=sha256:[0-9a-f]{64}( \\)?$', h)
        self.assertEqual(sum(1 for l in lines if not l.startswith('--hash=')), 1, 'one requirement, nothing else')
        # gitsign: the writer reads the shared action's pin as data, and reads it right
        install = _step(self.write, id='install')
        self.assertIn('.github/actions/install-gitsign/action.yml', install['run'])
        self.assertIn('sha256sum -c -', install['run'])
        self.assertNotIn('install.sh', install['run'], 'the shared action\'s script is a program from the checkout')
        action = yaml.safe_load(GITSIGN_ACTION.read_text())['runs']['steps'][0]['env']
        probe = '\n'.join(line for line in install['run'].splitlines()
                          if line.startswith(('version=', 'digest=')))
        probe += '\nprintf "%s %s\\n" "$version" "$digest"\n'
        done = subprocess.run(['bash', '-e', '-c', probe], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split(), [str(action['GITSIGN_VERSION']), action['GITSIGN_SHA256']])

    # --- the split ----------------------------------------------------------------------------------
    def test_write_job_has_no_hub_checkout_and_runs_inline_shell_only(self):
        self.assertEqual(self.write['needs'], 'twin')
        self.assertEqual(self.write['permissions'], {'contents': 'write', 'id-token': 'write'})
        for step in _steps(self.write):
            uses = str(step.get('uses', ''))
            if uses:
                self.assertNotIn('repository', step.get('with', {}), 'the writer checks out this repository alone')
                self.assertTrue(uses.startswith(INERT), uses)
            script = CONTINUED.sub(' ', COMMENT.sub('', str(step.get('run', ''))))
            hit = PROGRAM.search(script)
            self.assertIsNone(hit, f"the writer runs a program the checker cannot read: {hit and hit.group(0)!r}")
        download = _step(self.write, uses='actions/download-artifact@')
        self.assertEqual(download['with']['name'], 'twin-sweep-handoff')
        validate = _index(self.write, id='handoff')
        install = _index(self.write, id='install')
        observe = _index(self.write, id='observe')
        cage = _index(self.write, name='observation cage')
        sign = _index(self.write, id='sign')
        gate = _index(self.write, id='result')
        self.assertLess(_steps(self.write).index(download), validate)
        self.assertLess(validate, install)
        self.assertLess(install, observe)
        self.assertLess(observe, cage)
        self.assertLess(cage, sign)
        self.assertLess(sign, gate)
        self.assertIn('commit -S', _steps(self.write)[sign]['run'])
        self.assertNotIn('gh pr', '\n'.join(str(s.get('run', '')) for s in _steps(self.write)))
        cage_shell = _steps(self.write)[cage]['run']
        for fragment in CAGE_SHELL:
            self.assertIn(fragment, cage_shell)
        self.assertEqual(_steps(self.write)[cage]['if'], 'always()')
        self.assertIn('emitter_exit', _steps(self.write)[gate]['run'])

    # --- the writer as an adversary: every wrong handoff is refused by name ------------------------
    def test_validation_refuses_every_wrong_handoff_and_admits_the_right_one(self):
        shell = _step(self.write, id='handoff')['run']
        pin = self.pin['hub_commit']
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            repo.mkdir()
            env = dict(os.environ, GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='core.hooksPath',
                       GIT_CONFIG_VALUE_1='/dev/null', GITHUB_RUN_ID='4242')

            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], env=env, text=True).strip()

            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (repo / 'twin').mkdir()
            (repo / 'twin/PIN.yaml').write_text(PIN.read_text())
            git('add', 'twin/PIN.yaml')
            git('commit', '-qm', 'fixture')
            head = git('rev-parse', 'HEAD')

            def line(**over):
                rec = {'swept_at': '2026-09-26T07:17:00Z', 'org': self.party, 'feed': 'forward-intel',
                       'run': '4242', 'status': 'could_not_look', 'emitter_exit': 3, 'moved': None,
                       'detail': 'CANNOT LOOK: fixture', 'adopter_ref': head, 'hub_ref': pin,
                       'twin_pin': dict(self.pin)}
                rec.update(over)
                return json.dumps(rec, sort_keys=True) + '\n'

            case = {'n': 0}

            def run(observation, extra=None):
                case['n'] += 1
                handoff = Path(tmp) / f'handoff-{case["n"]}'
                handoff.mkdir()
                if observation is not None:
                    (handoff / 'observation.jsonl').write_text(observation)
                for rel, body in (extra or {}).items():
                    (handoff / rel).parent.mkdir(parents=True, exist_ok=True)
                    (handoff / rel).write_text(body)
                out = Path(tmp) / f'out-{case["n"]}'
                out.write_text('')
                done = subprocess.run(['bash', '-e', '-c', shell], cwd=repo, capture_output=True, text=True,
                                      env=dict(env, HANDOFF=str(handoff), GITHUB_OUTPUT=str(out)))
                return done.returncode, out.read_text(), done.stdout + done.stderr

            for status, code, moved in (('could_not_look', 3, None), ('unchanged', 0, False),
                                        ('review_required', 1, True), ('could_not_render', 1, None)):
                rc, out, said = run(line(status=status, emitter_exit=code, moved=moved))
                self.assertEqual(rc, 0, (status, said))
                self.assertEqual(out, f'emitter_exit={code}\n', status)

            other_pin = dict(self.pin, hub_commit='c' * 40)
            refused = [
                ('no observation at all', None, None, 'no observation.jsonl'),
                ('two lines', line() + line(), None, '2 line(s)'),
                ('no final newline', line().rstrip('\n'), None, 'final newline'),
                ('not JSON', 'not json\n', None, 'not one JSON object'),
                ('an extra key', line(action='tighten'), None, 'keys'),
                ('a missing key', json.dumps({'swept_at': '2026-09-26T07:17:00Z'}) + '\n', None, 'keys'),
                ('another run', line(run='4243'), None, 'names run 4243'),
                ('another org', line(org='driftwood'), None, f"{self.party}'s forward-intel line"),
                ('a dateless sweep', line(swept_at='yesterday'), None, 'swept_at'),
                ('a state this clock does not record', line(status='enacted'), None, 'not a state this clock records'),
                ('an exit the emitter does not have', line(emitter_exit=2), None, "not one of the emitter's exits"),
                ('a string moved', line(moved='true'), None, 'moved is neither'),
                ('the hub at main', line(hub_ref='main'), None, 'hub_ref main is not the pinned'),
                ('the hub at another commit', line(hub_ref='c' * 40), None, 'is not the pinned'),
                ('a pin that disagrees with the checkout', line(twin_pin=other_pin), None, 'is not the pinned'),
                ('a commit this repository lacks', line(adopter_ref='d' * 40), None, 'not a commit this repository has'),
                ('a proposal this clock cannot make', line(), {'proposal/twin/forward-intel/v1/feed.json': '{}\n'},
                 'proposal/twin/forward-intel/v1/feed.json is not the observation'),
                ('a stray file in a lane-shaped path', line(), {'observations/twin-sweep.jsonl': '{}\n'},
                 'observations/twin-sweep.jsonl is not the observation'),
            ]
            for why, observation, extra, expect in refused:
                rc, out, said = run(observation, extra)
                self.assertNotEqual(rc, 0, why)
                self.assertEqual(out, '', why + ': nothing may be output when the handoff is refused')
                self.assertIn('::error::the handoff is refused', said, why)
                self.assertIn(expect, said, why)

    # --- the cage, on what its shell does -----------------------------------------------------------
    def test_workflow_cage_blocks_declarations_and_precedes_final_gate(self):
        body = _step(self.write, name='observation cage')['run']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = dict(os.environ, GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='tag.gpgsign',
                       GIT_CONFIG_VALUE_1='false', GIT_CONFIG_KEY_2='core.hooksPath',
                       GIT_CONFIG_VALUE_2='/dev/null', GITHUB_REF_NAME='main',
                       OBSERVATION_LANE=self.doc['env']['OBSERVATION_LANE'])

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], env=env, text=True).strip()

            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'party.yaml').write_text('party: fixture\n')
            git('add', '.')
            git('commit', '-qm', 'fixture')
            (root / 'observations').mkdir()
            (root / 'observations/twin-sweep.jsonl').write_text('{}\n')
            clean = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertEqual(git('diff', '--cached', '--name-only'), 'observations/twin-sweep.jsonl')
            (root / 'party.yaml').write_text('party: changed\n')
            git('add', 'party.yaml')
            rejected = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn('party.yaml', git('diff', '--cached', '--name-only'))
            git('checkout', '--', 'party.yaml')
            git('switch', '-qc', 'proposal')
            wrong_branch = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(wrong_branch.returncode, 0)

    def test_append_step_appends_the_validated_line_and_refuses_a_torn_ledger(self):
        body = _step(self.write, id='observe')['run']
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            root.mkdir()
            handoff = Path(temp) / 'handoff'
            handoff.mkdir()
            (handoff / 'observation.jsonl').write_text('{"run": "1"}\n')
            out = Path(temp) / 'out'
            out.write_text('')
            env = dict(os.environ, HANDOFF=str(handoff), GITHUB_OUTPUT=str(out))
            first = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual((root / 'observations/twin-sweep.jsonl').read_text(), '{"run": "1"}\n')
            self.assertEqual(out.read_text(), 'recorded=true\n')
            (handoff / 'observation.jsonl').write_text('{"run": "2"}\n')
            second = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((root / 'observations/twin-sweep.jsonl').read_text(), '{"run": "1"}\n{"run": "2"}\n')
            (root / 'observations/twin-sweep.jsonl').write_text('{"run": "1"}')
            torn = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(torn.returncode, 0)
            self.assertIn('final newline', torn.stdout + torn.stderr)
            self.assertEqual((root / 'observations/twin-sweep.jsonl').read_text(), '{"run": "1"}')


if __name__ == '__main__':
    unittest.main()
