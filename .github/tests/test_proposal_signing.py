"""Run the real proposal signing callers without a key or publication destination."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ProposalSigning(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix='proposal-signing-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.adopter = self.root / 'tuppence'
        self.adopter.mkdir()
        self.tools = self.root / 'bin'
        self.tools.mkdir()
        self.record = self.root / 'signing-mode'
        self.env = {key: value for key, value in os.environ.items()
                    if not key.endswith('_TOKEN') and not key.startswith('GIT_CONFIG_')
                    and key not in ('GITSIGN_REKOR_MODE', 'PAVC_OTHER_HAND_PRIVATE_KEY')}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.hooksPath',
                        GIT_CONFIG_VALUE_0=os.devnull, RUNNER_TEMP=str(self.root),
                        SIGNING_MODE_PROBE=str(self.record), REAL_PYTHON=sys.executable,
                        PATH=str(self.tools) + os.pathsep + os.environ['PATH'])
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'synthetic fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm',
                 'synthetic unsigned fixture')
        self.before = self.git('rev-parse', 'HEAD')
        self.workflow = yaml.load((ROOT / '.github/workflows/propose-tier.yml').read_text(),
                                  Loader=yaml.BaseLoader)
        self.steps = self.workflow['jobs']['propose-tier']['steps']

    def git(self, *args: str) -> str:
        return subprocess.check_output(['git', '-C', str(self.adopter), *args],
                                       env=self.env, text=True, stderr=subprocess.DEVNULL).strip()

    def executable(self, name: str, body: str) -> None:
        path = self.tools / name
        path.write_text('#!/bin/sh\nset -eu\n' + body)
        path.chmod(0o755)

    def step(self, prefix: str) -> dict:
        return next(step for step in self.steps if step.get('name', '').startswith(prefix))

    def run_step(self, step: dict) -> subprocess.CompletedProcess[str]:
        command = step['run'].replace('${{ steps.recompose.outputs.as_of }}', '2000-01-01')
        self.assertNotIn('${{', command)
        env = dict(self.env)
        for key, value in step.get('env', {}).items():
            env[key] = 'synthetic-not-a-credential' if '${{' in value else value
        return subprocess.run(['bash', '-e', '-c', command], cwd=self.root,
                              env=env, capture_output=True, text=True)

    def test_actual_proposal_commit_call_embeds_rekor_proof(self) -> None:
        # Substitute only the proposal payload: real Git reaches a signer which
        # records the effective caller mode and refuses before any signature exists.
        self.executable('python3',
                        'if [ "$1" = "tuppence/.github/scripts/platform-tools.py" ]; then\n'
                        '  exec git -C tuppence commit --allow-empty -qm "refusing signer probe"\n'
                        'fi\nexec "$REAL_PYTHON" "$@"\n')
        self.executable('gitsign',
                        'mode="$(git config --get gitsign.rekorMode || true)"\n'
                        'printf "%s\\n" "${mode:-<unset>}" > "$SIGNING_MODE_PROBE"\n'
                        'exit 97\n')
        result = self.run_step(self.step('run the proposer --'))
        self.assertNotEqual(result.returncode, 0, 'the refusing signer must stop the actual caller')
        self.assertTrue(self.record.is_file(), result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.before)
        self.assertEqual(self.git('remote'), '', 'the fixture must have no publication destination')
        self.assertEqual(self.record.read_text(), 'offline\n')

    def test_actual_proposal_verifier_uses_embedded_rekor_proof(self) -> None:
        branch = 'wargamer/synthetic-unsigned-probe'
        self.git('branch', branch)
        (self.root / 'proposals.json').write_text(json.dumps([
            {'branch': branch, 'landed': {'action': 'created'}}]))
        self.env.update({key: value for key, value in self.workflow['env'].items()
                         if key in ('EXPECTED_PROPOSAL_IDENTITY_REGEXP', 'EXPECTED_ISSUER')})
        self.executable('gitsign',
                        'printf "%s\\n" "${GITSIGN_REKOR_MODE:-<unset>}" > "$SIGNING_MODE_PROBE"\n'
                        '[ "$1" = verify ] && [ "${GITSIGN_REKOR_MODE:-}" = offline ]\n')
        result = self.run_step(self.step("verify the proposal commit's signature"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.record.read_text(), 'offline\n')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.before)
        self.assertEqual(self.git('remote'), '')



if __name__ == '__main__':
    unittest.main()
