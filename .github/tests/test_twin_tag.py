"""Actual workflow-shell fixtures; unsigned local tags and a substituted verifier.

These tests cannot authenticate the real release. The genuine tag, source and
wrong-identity proof are separate prerequisites before source publication.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
TAG = 'twin/v0.1.0'
IDENTITY = (r'^https://github\.com/policy-as-versioned-flux/policy-as-versioned-flux/'
            r'\.github/workflows/cut-release\.yml@refs/heads/main$')
ISSUER = 'https://token.actions.githubusercontent.com'


class TwinReleaseWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load((ROOT / '.github/workflows/twin-sweep.yml').read_text())
        cls.steps = cls.workflow['jobs']['twin']['steps']
        cls.reader = next(s['run'] for s in cls.steps if s.get('id') == 'pin')
        cls.verifier = next(s for s in cls.steps if s.get('name') ==
                            'verify the authenticated twin release before running its code')

    @staticmethod
    def pin(commit):
        return ('twin_version: 0.1.0\ntwin_tag: twin/v0.1.0\n'
                'tag_cut: true\nhub_commit: ' + commit + '\n')

    def test_pin_reader_refuses_uncut_duplicate_malformed_and_mismatched_fields(self):
        valid = self.pin('a' * 40)
        cases = [valid, valid.replace('true', 'false'), valid.replace('true', '"true"'),
                 valid.replace('a' * 40, 'abc123'), valid.replace('twin/v0.1.0', 'main'),
                 valid.replace('twin_version: 0.1.0', 'twin_version: 0.2.0')]
        cases += [valid + key + ': invalid\n' for key in
                  ('hub_commit', 'twin_version', 'twin_tag', 'tag_cut')]
        for index, text in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp); (path / 'twin').mkdir()
                (path / 'twin/PIN.yaml').write_text(text)
                output = path / 'output'; output.write_text('')
                done = subprocess.run(['bash', '-e', '-c', self.reader], cwd=path,
                                      env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                                      text=True, capture_output=True)
                if index == 0:
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(output.read_text(), 'hub_commit=' + 'a' * 40 + '\n')
                else:
                    self.assertNotEqual(done.returncode, 0)
                    self.assertEqual(output.read_text(), '')

    def test_real_verifier_step_restores_tag_object_and_fails_closed(self):
        for mode in ('restored', 'missing', 'lightweight', 'wrong-pin', 'wrong-head',
                     'wrong-version', 'verifier-failure', 'wrong-identity', 'online'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); hub = root / 'hub'; adopter = root / 'adopter'
                adopter.mkdir(); (adopter / 'twin').mkdir()
                env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                           GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='2',
                           GIT_CONFIG_KEY_0='commit.gpgsign', GIT_CONFIG_VALUE_0='false',
                           GIT_CONFIG_KEY_1='core.hooksPath', GIT_CONFIG_VALUE_1='/dev/null')
                def git(*args):
                    return subprocess.check_output(['git', '-c', 'tag.gpgsign=false', *args],
                                                   env=env, text=True, stderr=subprocess.DEVNULL).strip()
                remote = root / 'remote.git'
                git('init', '--bare', str(remote)); git('init', '-b', 'main', str(hub))
                git('-C', str(hub), 'config', 'user.name', 'Unsigned fixture')
                git('-C', str(hub), 'config', 'user.email', 'fixture@example.invalid')
                (hub / 'twin').mkdir()
                (hub / 'twin/VERSION').write_text('0.2.0\n' if mode == 'wrong-version' else '0.1.0\n')
                git('-C', str(hub), 'add', 'twin/VERSION')
                git('-C', str(hub), 'commit', '-m', 'unsigned fixture')
                commit = git('-C', str(hub), 'rev-parse', 'HEAD')
                git('-C', str(hub), 'remote', 'add', 'origin', str(remote))
                git('-C', str(hub), 'push', 'origin', 'HEAD:refs/heads/main')
                if mode != 'missing':
                    args = ('tag', TAG) if mode == 'lightweight' else ('tag', '-a', TAG, '-m', 'unsigned fixture')
                    git('-C', str(hub), *args)
                    git('-C', str(hub), 'push', 'origin', 'refs/tags/' + TAG)
                if mode == 'restored':
                    git('-C', str(hub), 'update-ref', 'refs/tags/' + TAG, commit)
                if mode == 'wrong-head':
                    git('-C', str(hub), 'commit', '--allow-empty', '-m', 'different HEAD')
                (adopter / 'twin/PIN.yaml').write_text(self.pin('b' * 40 if mode == 'wrong-pin' else commit))
                bindir = root / 'bin'; bindir.mkdir(); verifier = bindir / 'gitsign'
                expected = ['verify-tag', TAG,
                            '--certificate-identity-regexp=' + IDENTITY,
                            '--certificate-oidc-issuer=' + ISSUER]
                # Pinned gitsign 0.17.1 prefixes refs/tags/ itself. Resolve the
                # same reference against real fixture Git data before allowing
                # the substituted signature verdict; accepting a qualified ref
                # here hid the scheduled workflow's reference-not-found error.
                verifier.write_text('#!/usr/bin/env python3\nimport json,os,subprocess,sys\n'
                                    'args=sys.argv[1:]\n'
                                    'open(os.environ["FIXTURE_CALL"],"w").write(json.dumps(args))\n'
                                    'resolved=subprocess.run(["git","show-ref","--verify",'
                                    '"refs/tags/"+args[1]],capture_output=True)\n'
                                    'if resolved.returncode: print("Error: error resolving tag reference: '
                                    'reference not found",file=sys.stderr); sys.exit(1)\n'
                                    'sys.exit(0 if args == ' + repr(expected) +
                                    ' and os.environ.get("GITSIGN_REKOR_MODE")=="offline"'
                                    ' and os.environ.get("FIXTURE_FAIL")!="1" else 1)\n')
                verifier.chmod(0o755)
                shell = self.verifier['run']
                if mode == 'wrong-identity':
                    shell = shell.replace('@refs/heads/main$', '@refs/heads/other$')
                done = subprocess.run(['bash', '-e', '-c', shell], cwd=adopter,
                                      env=dict({**env, **self.verifier['env'],
                                                **({'GITSIGN_REKOR_MODE': 'online'} if mode == 'online' else {})},
                                               PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                                               GITHUB_WORKSPACE=str(root),
                                               FIXTURE_CALL=str(root / 'call.json'),
                                               FIXTURE_FAIL='1' if mode == 'verifier-failure' else '0'),
                                      text=True, capture_output=True)
                if mode == 'restored':
                    self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertEqual(git('-C', str(hub), 'cat-file', '-t', 'refs/tags/' + TAG), 'tag')
                    self.assertEqual(json.loads((root / 'call.json').read_text()), expected)
                else:
                    self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == '__main__':
    unittest.main()
