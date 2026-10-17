"""Exercise the actual release tag caller without issuing a signature or tag."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class ReleaseSigning(unittest.TestCase):
    def test_actual_release_tag_call_embeds_rekor_proof(self) -> None:
        document = yaml.load((ROOT / '.github/workflows/cut-release.yml').read_text(),
                             Loader=yaml.BaseLoader)
        step = next(step for step in document['jobs']['cut']['steps']
                    if step.get('name') == 'create the signed annotated tag (ambient Actions identity, no interactive login)')
        command = step['run'].replace('${{ inputs.version }}', 'v0.0.0-synthetic-probe').replace(
            '${{ inputs.message }}', 'synthetic refusing signer probe')
        self.assertNotIn('${{', command, 'the actual signing step has an unbound workflow input')
        with tempfile.TemporaryDirectory(prefix='release-signing-mode-') as temporary:
            root = Path(temporary)
            tools = root / 'bin'
            tools.mkdir()
            record = root / 'signing-mode'
            signer = tools / 'gitsign'
            signer.write_text(
                '#!/bin/sh\n'
                'mode="$(git config --get gitsign.rekorMode || true)"\n'
                'printf "%s\\n" "${mode:-<unset>}" >> "$SIGNING_MODE_PROBE"\n'
                '# Deliberately refuse issuance before any signature or tag exists.\n'
                'exit 97\n')
            signer.chmod(0o755)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                       GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='tag.gpgsign',
                       GIT_CONFIG_VALUE_1='false', GIT_CONFIG_KEY_2='core.hooksPath',
                       GIT_CONFIG_VALUE_2=os.devnull, SIGNING_MODE_PROBE=str(record),
                       GITHUB_REPOSITORY_OWNER='synthetic-fixture',
                       PATH=str(tools) + os.pathsep + os.environ['PATH'])
            env.pop('GITSIGN_REKOR_MODE', None)
            for name in tuple(env):
                if name.endswith('_TOKEN') or name == 'PAVC_OTHER_HAND_PRIVATE_KEY':
                    env.pop(name)

            def git(*args: str) -> str:
                return subprocess.check_output(['git', *args], cwd=root, env=env,
                                               text=True, stderr=subprocess.DEVNULL).strip()

            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'synthetic fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / 'fixture').write_text('No release identity, key or remote.\n')
            git('add', 'fixture')
            git('commit', '-qm', 'synthetic unsigned fixture')
            before = git('rev-parse', 'HEAD')
            result = subprocess.run(['bash', '-e', '-c', command], cwd=root, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, 'the refusing signer must stop the actual caller')
            self.assertTrue(record.is_file(), 'the actual Git signing call must reach the signer probe')
            self.assertEqual(git('tag', '--list'), '', 'the probe must issue no tag')
            self.assertEqual(git('rev-parse', 'HEAD'), before)
            self.assertEqual(git('remote'), '', 'the probe must have no publication destination')
            self.assertEqual(record.read_text(), 'offline\n',
                             'the exact signing call must embed its Rekor proof, once')


if __name__ == '__main__':
    unittest.main()
