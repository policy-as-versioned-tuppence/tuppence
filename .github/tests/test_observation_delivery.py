"""Protected delivery over real Git; synthetic signing/gh stand-ins are explicit.

These tests execute the producer's actual cage and sign shell. They establish
transport, containment and byte conservation, never genuine gitsign issuance or
live GitHub rights. The shared immutable reviewer is tested in its hub source.
"""
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'a675ee166678fd6b1b0d5d5ebcb35ad96be5b127'
BUNDLE = 'afc5cac1af0f91593a8c4901603cf9dcbd534bc4923d62a5ac224614362c0b23'


def workflow(clock):
    return yaml.load((ROOT / '.github/workflows' / (clock + '.yml')).read_text(), Loader=yaml.BaseLoader)


def shell(clock):
    doc = workflow(clock);job = doc['jobs']['sample' if clock == 'drift-sample' else 'write']
    cage = next(step for step in job['steps'] if step.get('name', '').startswith('the observation cage'))
    body = cage['run']
    sign = [step for step in job['steps'] if step.get('id') == 'sign']
    if sign: body += '\n' + sign[0]['run']
    # Explicit signer substitution: certificates are not fabricated by fixtures.
    return doc, body.replace('commit -S -m', 'commit --no-gpg-sign -m')


class ObservationDelivery(unittest.TestCase):
    def run_producer(self, clock, default='main', ref=None, collision=False, race=False,
                     declaration=False, refuse_pr=False, advance=False):
        doc, body = shell(clock)
        with tempfile.TemporaryDirectory(prefix='observation-transport-') as temporary:
            temp = Path(temporary);root = temp / 'checkout';target = temp / 'remote.git';root.mkdir()
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='tag.gpgsign', GIT_CONFIG_VALUE_1='false',
                       GITHUB_REF_NAME=ref or default, DEFAULT_BRANCH=default, OBSERVATION_CLOCK=clock,
                       OBSERVATION_LANE=doc['env']['OBSERVATION_LANE'], GITHUB_RUN_ID='100',
                       GITHUB_RUN_ATTEMPT='2', GITHUB_REPOSITORY='fixture/adopter',
                       RUNNER_TEMP=str(temp), GH_TOKEN='synthetic-no-permission', GITHUB_OUTPUT=str(temp / 'output'))
            def git(*args, cwd=root, check=True):
                result = subprocess.run(['git', '-C', str(cwd), *args], env=env, capture_output=True)
                if check and result.returncode:
                    raise AssertionError((args, result.stdout.decode(), result.stderr.decode()))
                return result.stdout.decode().strip()
            git('init', '-q', '-b', default);git('config', 'core.hooksPath', os.devnull);git('config', 'user.name', 'synthetic fixture');git('config', 'user.email', 'fixture@example.invalid')
            paths = ['drift/samples.jsonl', 'drift/workload-samples.jsonl', 'drift/oscal-samples.jsonl'] if clock == 'drift-sample' else ['observations/twin-sweep.jsonl']
            for path in paths:
                out = root / path;out.parent.mkdir(exist_ok=True);out.write_bytes(b'{"synthetic":"old exact bytes"}\n')
            (root / 'party.yaml').write_text('party: fixture\n');git('add', '.');git('commit', '-qm', 'fixture measured source')
            source = git('rev-parse', 'HEAD');git('init', '-q', '--bare', '-b', default, str(target));git('remote', 'add', 'origin', str(target));git('push', '-q', 'origin', default)
            # The hook, like the actual rule, rejects producer pushes to default.
            git('config', 'core.hooksPath', str(target / 'hooks'), cwd=target)
            hook = target / 'hooks/update';hook.write_text('#!/bin/sh\nif [ "$1" = refs/heads/' + default + ' ]; then\n test -f reviewed-head || { echo "GH013: Changes must be made through a pull request" >&2; exit 1; }\nfi\n');hook.chmod(0o755)
            branch = 'observations/' + clock + '/100-2'
            if collision: git('push', '-q', 'origin', source + ':refs/heads/' + branch)
            if race:
                wrapper = temp / 'receive-pack';wrapper.write_text('#!/bin/sh\ngit -C "$1" update-ref refs/heads/' + branch + ' ' + source + '\nexec git-receive-pack "$@"\n');wrapper.chmod(0o755);git('config', 'remote.origin.receivepack', str(wrapper))
            before_default = source
            if advance:
                other = temp / 'other';git('clone', '-q', str(target), str(other));git('config', 'core.hooksPath', os.devnull, cwd=other);git('config', 'user.name', 'fixture reviewer', cwd=other);git('config', 'user.email', 'reviewer@example.invalid', cwd=other)
                (other / 'unrelated.md').write_text('reviewed default advanced\n');git('add', '.', cwd=other);git('commit', '-qm', 'reviewed change', cwd=other)
                (target / 'reviewed-head').write_text(git('rev-parse', 'HEAD', cwd=other));git('push', '-q', 'origin', default, cwd=other);before_default = git('rev-parse', default, cwd=target)
                (target / 'reviewed-head').unlink()
            if ref and ref != default: git('switch', '-qc', ref)
            for path in paths:
                with (root / path).open('ab') as stream: stream.write(b'{"synthetic":"one new row"}\n')
            if declaration:
                (root / 'party.yaml').write_text('party: changed\n');git('add', 'party.yaml')
            tools = temp / 'bin';tools.mkdir();gh = tools / 'gh'
            # Observe the actual Git configuration at the real commit call. The
            # fixture still substitutes signing, never a certificate or log proof.
            real_git = shutil.which('git')
            self.assertIsNotNone(real_git)
            git_probe = tools / 'git'
            git_probe.write_text(
                '#!/usr/bin/env python3\n'
                'import os, subprocess, sys\n'
                'from pathlib import Path\n'
                'real_git = ' + repr(real_git) + '\n'
                'args = sys.argv[1:]\n'
                'if "commit" in args:\n'
                '    prefix = args[:args.index("commit")]\n'
                '    result = subprocess.run([real_git, *prefix, "config", "--get", "gitsign.rekorMode"], capture_output=True, text=True)\n'
                '    Path(' + repr(str(temp / 'sign-mode')) + ').write_text(result.stdout.strip() or "<unset>")\n'
                'os.execv(real_git, [real_git, *args])\n')
            git_probe.chmod(0o755)
            gh.write_text('#!/bin/sh\nset -eu\n' + ('exit 1\n' if refuse_pr else
                'test "$(git --git-dir=' + str(target) + ' rev-parse refs/heads/' + branch + ')" = "$(git rev-parse HEAD)"\nprintf "%s\\n" "$*" > ' + str(temp / 'pr-called') + '\n'))
            gh.chmod(0o755);env['PATH'] = str(tools) + os.pathsep + env['PATH']
            result = subprocess.run(['bash', '-e', '-c', body], cwd=root, env=env, capture_output=True, text=True)
            current = git('rev-parse', 'HEAD');pending = git('rev-parse', '--verify', 'refs/heads/' + branch, cwd=target, check=False)
            self.assertEqual(git('rev-parse', default, cwd=target), before_default, 'the clock must never push default')
            if ref and ref != default:
                self.assertEqual(current, source);self.assertFalse(pending);self.assertFalse((temp / 'pr-called').exists());return
            if declaration:
                self.assertNotEqual(result.returncode, 0);self.assertEqual(current, source);self.assertFalse(pending);return
            self.assertEqual((temp / 'sign-mode').read_text(), 'offline',
                             'the actual signing call must embed its Rekor proof')
            if collision or race:
                self.assertNotEqual(result.returncode, 0);self.assertEqual(pending, source);self.assertFalse((temp / 'pr-called').exists());return
            self.assertEqual(result.returncode, 1 if refuse_pr else 0, result.stdout + result.stderr)
            self.assertNotEqual(current, source);self.assertEqual(pending, current, 'original must be durable before PR creation')
            self.assertEqual(git('rev-parse', 'HEAD^'), source, 'fetch/rebase must not replace the measured original')
            party = yaml.load((ROOT / 'party.yaml').read_text(), Loader=yaml.BaseLoader)['party']
            email = clock + '@policy-as-versioned-' + party + '.invalid'
            self.assertEqual(git('show', '-s', '--format=%ae %ce', 'HEAD'), email + ' ' + email)
            self.assertEqual(set(git('diff', '--name-only', source, current).splitlines()), set(paths))
            for path in paths:
                self.assertEqual(git('show', 'HEAD:' + path), git('show', 'refs/heads/' + branch + ':' + path, cwd=target))
            self.assertEqual((temp / 'pr-called').exists(), not refuse_pr)
            self.assertNotIn('RECORDED', result.stdout)

    def test_actual_producer_cages_publish_pending_without_pushing_main(self):
        for clock in ('drift-sample', 'twin-sweep'):
            with self.subTest(clock=clock): self.run_producer(clock)

    def test_original_is_not_rebased_when_default_advanced(self):
        for clock in ('drift-sample', 'twin-sweep'):
            with self.subTest(clock=clock): self.run_producer(clock, advance=True)

    def test_existing_and_racing_ancestor_refs_are_never_updated(self):
        for clock in ('drift-sample', 'twin-sweep'):
            for key in ('collision', 'race'):
                with self.subTest(clock=clock, case=key): self.run_producer(clock, **{key: True})

    def test_refused_pr_preserves_the_original_pending_object(self):
        for clock in ('drift-sample', 'twin-sweep'):
            with self.subTest(clock=clock): self.run_producer(clock, refuse_pr=True)

    def test_nondefault_and_declarations_never_publish(self):
        for clock in ('drift-sample', 'twin-sweep'):
            for options in ({'ref': 'feature'}, {'declaration': True}):
                with self.subTest(clock=clock, case=options): self.run_producer(clock, **options)

    def test_renamed_default_is_not_hardcoded_to_main(self):
        for clock in ('drift-sample', 'twin-sweep'):
            with self.subTest(clock=clock): self.run_producer(clock, default='trunk')

    def test_trusted_caller_is_pinned_read_only_then_a_narrow_other_hand(self):
        text = (ROOT / '.github/workflows/observation-delivery.yml').read_text();doc = yaml.load(text, Loader=yaml.BaseLoader);job = doc['jobs']['review']
        self.assertEqual(doc['permissions'], {'contents': 'read', 'actions': 'read', 'pull-requests': 'read'})
        self.assertNotIn('schedule', doc['on']);self.assertEqual(doc['on']['workflow_run']['workflows'], ['drift-sample', 'twin-sweep'])
        self.assertEqual(job['environment'], 'observation-delivery');self.assertIn('github.event.repository.default_branch', job['if'])
        self.assertEqual(job['env']['DELIVERY_SOURCE'], SOURCE);self.assertEqual(job['env']['DELIVERY_SHA256'], BUNDLE)
        checkouts = [s for s in job['steps'] if str(s.get('uses', '')).startswith('actions/checkout@')]
        self.assertEqual(len(checkouts), 1);self.assertEqual(checkouts[0]['with']['ref'], '${{ github.event.repository.default_branch }}');self.assertEqual(checkouts[0]['with']['persist-credentials'], 'false')
        preflight = next(i for i,s in enumerate(job['steps']) if '--check-only' in s.get('run', ''))
        writer = next(i for i,s in enumerate(job['steps']) if '--mint' in s.get('run', ''))
        self.assertLess(preflight, writer)
        self.assertEqual([i for i,s in enumerate(job['steps']) if 'PAVC_OTHER_HAND_PRIVATE_KEY' in s.get('env', {})], [writer])
        self.assertEqual(job['steps'][writer]['env']['TRUTH_READ_TOKEN'], '${{ github.token }}')
        self.assertNotIn('download-artifact', text);self.assertNotIn('pull_request_target', text)
        self.assertIn('--require-hashes', text);self.assertIn('sha256sum --check --strict', text)


if __name__ == '__main__':
    unittest.main()
