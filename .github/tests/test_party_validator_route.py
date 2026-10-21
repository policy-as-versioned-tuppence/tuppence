"""Exercise the actual party-check workflow boundary without actions or network.

The local checkers identify executable selection and refusal propagation only.
Real old/new schema admission is separately covered by the publisher parser.
This hidden workflow regression is discovered by compose-check and does not
change the adopter comparison identity.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
NAME = 'tuppence'


class PartyValidatorRoute(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/shift-left.yml').read_text())
        self.steps = self.workflow['jobs']['shift-left']['steps']
        gates = [step for step in self.steps if 'party artefact check' in step.get('name', '')]
        self.assertEqual(len(gates), 1)
        self.gate = gates[0]

    def test_verified_compiler_is_ready_before_party_check(self):
        own = next(step for step in self.steps
                   if step.get('uses', '').startswith('actions/checkout@')
                   and step.get('with', {}).get('path') == NAME
                   and 'repository' not in step.get('with', {}))
        setup = []
        for action in ('install-gitsign', 'platform-tools'):
            found = [step for step in self.steps
                     if step.get('uses') == f'./{NAME}/.github/actions/{action}']
            self.assertEqual(len(found), 1, f'one required {action} action in shift-left')
            step = found[0]
            self.assertNotIn('if', step)
            self.assertFalse(step.get('continue-on-error', False))
            setup.append(step)
        self.assertEqual(setup[1]['with']['adopter-dir'], NAME)
        order = [self.steps.index(step) for step in (own, *setup, self.gate)]
        self.assertEqual(order, sorted(order), 'verify compiler before using its input schema')
        self.assertNotIn('if', self.gate)
        self.assertFalse(self.gate.get('continue-on-error', False))
        self.assertFalse(self.workflow['jobs']['shift-left'].get('continue-on-error', False))
        self.assertTrue(any('python3 platform/shift-left/ci-check.py --resource ' in step.get('run', '')
                            for step in self.steps), 'enforcement still uses accepted policies')

    def run_party_step(self, checker_exit=0, missing=False):
        with tempfile.TemporaryDirectory(prefix='party-route-') as temporary:
            root = Path(temporary)
            (root / NAME).mkdir()
            (root / NAME / 'party.yaml').write_text('overlay:\n  workload_cages: []\n')
            tools = root / 'bin'
            tools.mkdir()
            # Dependency installation is outside this shell-selection test.
            # The workflow's existing tools action supplies PyYAML in CI.
            pip = tools / 'pip'
            pip.write_text('#!/bin/sh\nexit 0\n')
            pip.chmod(0o755)
            (tools / 'python3').symlink_to(sys.executable)
            accepted = root / 'platform/party'
            if not missing:
                accepted.mkdir(parents=True)
                (accepted / 'party_artefact.py').write_text(
                    'raise SystemExit("WRONG: accepted-policy parser selected")\n')
                compiler = root / 'platform-tools/party'
                compiler.mkdir(parents=True)
                (compiler / 'party_artefact.py').write_text(
                    'import json, os, sys\n'
                    'from pathlib import Path\n'
                    'Path("checker-argv.json").write_text(json.dumps(sys.argv[1:]))\n'
                    'raise SystemExit(int(os.environ["SYNTHETIC_CHECKER_EXIT"]))\n')
            command = self.gate['run']
            # Old Ludlow's skip message includes this otherwise unrelated
            # expression; resolve it to a labelled fixture for baseline RED.
            command = command.replace('${{ steps.pin.outputs.tag }}', 'synthetic-policy-tag')
            self.assertNotIn('${{', command)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       SYNTHETIC_CHECKER_EXIT=str(checker_exit), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run(['bash', '-e', '-c', command], cwd=root, env=env,
                                    capture_output=True, text=True)
            record = root / 'checker-argv.json'
            return result, json.loads(record.read_text()) if record.exists() else None

    def test_actual_party_step_selects_compiler_and_propagates_refusal(self):
        for code in (0, 13):
            with self.subTest(checker_exit=code):
                result, arguments = self.run_party_step(checker_exit=code)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual(arguments, ['check', f'{NAME}/party.yaml', '--adopter-dir', NAME])

    def test_missing_required_compiler_checker_fails(self):
        result, arguments = self.run_party_step(missing=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(arguments)
        self.assertNotIn('SKIP', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
