"""The clock records real emitter outcomes; the workflow cages only observations."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / '.github/scripts/twin-sweep.py'
WORKFLOW = ROOT / '.github/workflows/twin-sweep.yml'


class TwinClock(unittest.TestCase):
    def test_check_outcomes_are_appended_before_the_gate_and_never_emit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'twin').mkdir()
            (root / 'party.yaml').write_text('party: fixture\n')
            (root / 'twin/PIN.yaml').write_text('twin_version: 0.1.0\ntag_cut: false\n')
            emitter = root / 'twin/emit-forward-intel.py'
            ledger = root / 'observations/twin-sweep.jsonl'
            previous = b''
            for code, status in [(0, 'unchanged'), (1, 'review_required'), (3, 'could_not_look')]:
                emitter.write_text(f'import sys\nassert sys.argv[1:] == ["--check"]\nprint("fixture missing instrument" if {code} == 3 else "fixture render result")\nraise SystemExit({code})\n')
                run_id = f'fixture-{code}'
                command = [sys.executable, str(HELPER), 'record', '--adopter-dir', str(root),
                           '--at', '2026-09-10T00:00:00Z', '--run-id', run_id, '--hub-ref', 'a' * 40, '--adopter-ref', 'b' * 40]
                # bash -e must not swallow the exit3 observation before it is written.
                import shlex
                result = subprocess.run(['bash', '-e', '-c', shlex.join(command)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                content = ledger.read_bytes()
                self.assertTrue(content.startswith(previous))
                record = json.loads(content.splitlines()[-1])
                self.assertEqual(record['status'], status)
                self.assertEqual(record['emitter_exit'], code)
                if code == 3:
                    self.assertIsNone(record['moved'])
                    self.assertIn('missing instrument', record['detail'])
                self.assertFalse((root / 'twin/forward-intel/v1/feed.json').exists())
                gate = subprocess.run([sys.executable, str(HELPER), 'gate', '--adopter-dir', str(root),
                                       '--run-id', run_id], capture_output=True, text=True)
                self.assertEqual(gate.returncode, code, gate.stderr)
                previous = content

    def test_loader_signer_and_observer_live_in_the_same_job(self):
        doc = yaml.safe_load(WORKFLOW.read_text())
        job = doc['jobs']['sweep']
        party = yaml.safe_load((ROOT / 'party.yaml').read_text())['party']
        checkout = f'hub/.estate-clone/{party}'
        self.assertEqual(job['defaults']['run']['working-directory'], checkout)
        steps = job['steps']
        paths = [s.get('with', {}).get('path') for s in steps if s.get('uses', '').startswith('actions/checkout@')]
        self.assertIn('hub', paths)
        self.assertIn(checkout, paths)
        install = next(i for i, s in enumerate(steps) if s.get('id') == 'install')
        self.assertIn('.github/actions/install-gitsign', steps[install]['run'])
        observe = next(i for i, s in enumerate(steps) if s.get('id') == 'observe')
        self.assertLess(install, observe)
        self.assertTrue((ROOT / '.github/actions/install-gitsign/install.sh').is_file())
        self.assertIn('--hub-ref', steps[observe]['run'])
        self.assertIn('--adopter-ref', steps[observe]['run'])

    def test_workflow_cage_blocks_declarations_and_precedes_final_gate(self):
        doc = yaml.safe_load(WORKFLOW.read_text())
        steps = doc['jobs']['sweep']['steps']
        observe = next(i for i, step in enumerate(steps) if step.get('id') == 'observe')
        cage = next(i for i, step in enumerate(steps) if 'observation cage' in step.get('name', ''))
        sign = next(i for i, step in enumerate(steps) if step.get('id') == 'sign')
        gate = next(i for i, step in enumerate(steps) if step.get('id') == 'result')
        self.assertLess(observe, cage)
        self.assertLess(cage, sign)
        self.assertLess(sign, gate)
        self.assertIn('commit -S', steps[sign]['run'])
        self.assertNotIn('gh pr', '\n'.join(s.get('run', '') for s in steps))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = dict(os.environ, GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='tag.gpgsign',
                       GIT_CONFIG_VALUE_1='false', GIT_CONFIG_KEY_2='core.hooksPath',
                       GIT_CONFIG_VALUE_2='/dev/null', GITHUB_REF_NAME='main',
                       OBSERVATION_LANE=doc['env']['OBSERVATION_LANE'])
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
            body = steps[cage]['run']
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


if __name__ == '__main__':
    unittest.main()
