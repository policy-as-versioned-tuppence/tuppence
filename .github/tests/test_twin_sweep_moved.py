"""Command-seam fixtures for the observation-only moved-path instrument.

The emitters here are labelled synthetic classification fixtures. The production
check separately runs the real emitter, and fixtures never count as live evidence.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'twin/verify-twin-sweep-moved.sh'
PARTY = yaml.safe_load((ROOT / 'party.yaml').read_text())['party']
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/twin-sweep.yml').read_text())
OBSERVE = next(s for s in WORKFLOW['jobs']['twin']['steps'] if s.get('id') == 'observe')


class MovedInstrument(unittest.TestCase):
    def run_check(self, mutate=lambda root, doc: None):
        # The initial RED reaches the same missing command as the Hub's step5.
        if not CHECK.is_file():
            return subprocess.run(['bash', str(CHECK)], capture_output=True, text=True)
        with tempfile.TemporaryDirectory(prefix='synthetic-moved-instrument-') as tmp:
            workspace = Path(tmp)
            hub = workspace / 'hub'
            root = hub / '.estate-clone' / PARTY
            root.mkdir(parents=True)
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                       GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='commit.gpgsign',
                       GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='tag.gpgsign',
                       GIT_CONFIG_VALUE_1='false', GIT_CONFIG_KEY_2='core.hooksPath',
                       GIT_CONFIG_VALUE_2='/dev/null')

            def git(where, *args):
                return subprocess.check_output(['git', '-C', str(where), *args],
                                               env=env, text=True).strip()

            (hub / 'twin').mkdir()
            (hub / 'twin/repo.py').write_text('# synthetic hub discovery marker\n')
            (hub / 'clone-estate.sh').write_text('# synthetic hub discovery marker\n')
            (hub / '.gitignore').write_text('.estate-clone/\n.sweep-moved-*/\n')
            for where in (hub, root):
                git(where, 'init', '-q', '-b', 'main')
                git(where, 'config', 'user.name', 'Synthetic instrument fixture')
                git(where, 'config', 'user.email', 'fixture@example.invalid')
            git(hub, 'add', '.')
            git(hub, 'commit', '-qm', 'synthetic discovery fixture')
            for directory in ('twin/orgs/' + PARTY, '.github/scripts', '.github/workflows'):
                (root / directory).mkdir(parents=True, exist_ok=True)
            (root / 'party.yaml').write_text('party: ' + PARTY + '\n')
            (root / 'twin/PIN.yaml').write_text('hub_commit: ' + git(hub, 'rev-parse', 'HEAD') +
                                               '\ntwin_version: 0.1.0\ntag_cut: false\n')
            (root / 'twin/ladder.yaml').write_text('rungs: [isolated]\n')
            (root / 'twin/orgs' / PARTY / 'meta.yaml').write_text('world_ref: valid-fixture\n')
            for major in ('v1', 'v2'):
                feed = root / 'twin/forward-intel' / major / 'feed.json'
                feed.parent.mkdir(parents=True)
                feed.write_text('expected synthetic render\n')
            (root / 'twin/emit-forward-intel.py').write_text(
                'from pathlib import Path\nimport sys\n'
                'VERSION = "2.0.0"\nroot = Path(__file__).resolve().parent.parent\n'
                'if not (root / "twin/ladder.yaml").is_file():\n'
                ' print("CANNOT LOOK: synthetic missing ladder"); raise SystemExit(3)\n'
                'if "refused" in (root / "twin/orgs/' + PARTY + '/meta.yaml").read_text():\n'
                ' print("REFUSED: synthetic world pin"); raise SystemExit(1)\n'
                'feed = root / "twin/forward-intel" / ("v" + VERSION.split(".")[0]) / "feed.json"\n'
                'if feed.read_text() != "expected synthetic render\\n":\n'
                ' print("FAIL: synthetic feed is not what the overlay renders"); raise SystemExit(1)\n'
                'print("ok synthetic render matches")\n')
            shutil.copyfile(ROOT / '.github/scripts/twin-sweep.py', root / '.github/scripts/twin-sweep.py')
            shutil.copyfile(CHECK, root / 'twin/verify-twin-sweep-moved.sh')
            doc = {'jobs': {'twin': {'permissions': {'contents': 'read'}, 'steps': [dict(OBSERVE)]},
                            'write': {'steps': [{'id': 'observe', 'run': 'echo WRITER_EXECUTED; exit 99'}]}}}
            (root / '.github/workflows/twin-sweep.yml').write_text(yaml.safe_dump(doc))
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'synthetic prior source for observation provenance')
            mutate(root, doc)
            (root / '.github/workflows/twin-sweep.yml').write_text(yaml.safe_dump(doc))
            git(root, 'add', '.')
            git(root, 'commit', '--allow-empty', '-qm', 'synthetic command-seam fixture')
            before = git(root, 'status', '--porcelain', '--untracked-files=all')
            done = subprocess.run(['bash', str(root / 'twin/verify-twin-sweep-moved.sh')],
                                  cwd=root, env=env, capture_output=True, text=True, timeout=40)
            self.assertEqual(git(root, 'status', '--porcelain', '--untracked-files=all'), before)
            self.assertNotIn('WRITER_EXECUTED', done.stdout + done.stderr)
            return done

    def test_actual_command_proves_offline_cases_but_keeps_missing_live_witness_skip(self):
        done = self.run_check()
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        for case in ('fresh selected feed', 'stale selected feed', 'missing ladder', 'refused world pin',
                     'stale retained v1 feed'):
            self.assertIn('PASS: ' + case, done.stdout)
        self.assertIn('no committed moved:true witness', done.stdout)

    def test_missing_readjob_observe_fails_instead_of_running_writer(self):
        done = self.run_check(lambda root, doc: doc['jobs']['twin'].update(steps=[]))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('exactly one read-job observe', done.stdout)

    def test_duplicate_readjob_observe_is_refused(self):
        done = self.run_check(lambda root, doc: doc['jobs']['twin']['steps'].append(dict(OBSERVE)))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('exactly one read-job observe', done.stdout)

    def test_write_capability_on_readjob_is_refused(self):
        done = self.run_check(lambda root, doc: doc['jobs']['twin']['permissions'].update(contents='write'))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('contents: read', done.stdout)

    def test_actual_recorder_must_observe_stale_feed_not_claim_unchanged(self):
        def mutate(root, doc):
            helper = root / '.github/scripts/twin-sweep.py'
            helper.write_text(helper.read_text().replace('code = result.returncode', 'code = 0'))
        done = self.run_check(mutate)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('FAIL: stale selected feed', done.stdout)

    def test_record_step_cannot_write_the_source_ledger(self):
        def mutate(root, doc):
            doc['jobs']['twin']['steps'][0]['run'] = OBSERVE['run'].replace('--handoff "${HANDOFF}"', '')
        done = self.run_check(mutate)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('--handoff', done.stdout)

    def observation(self, root, **changes):
        source = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        pin = yaml.safe_load((root / 'twin/PIN.yaml').read_text())
        record = {'org': PARTY, 'feed': 'forward-intel', 'run': '1234',
                  'swept_at': '2026-10-01T00:00:00Z', 'adopter_ref': source,
                  'hub_ref': pin.get('hub_commit') or subprocess.check_output(
                      ['git', '-C', str(root.parents[1]), 'rev-parse', 'HEAD'], text=True).strip(),
                  'twin_pin': pin, 'emitter_exit': 0,
                  'status': 'unchanged', 'moved': False, 'detail': 'ok synthetic render matches'}
        record.update(changes)
        (root / 'observations').mkdir()
        (root / 'observations/twin-sweep.jsonl').write_text(json.dumps(record) + '\n')

    def test_valid_unchanged_history_does_not_count_as_live_movement(self):
        done = self.run_check(lambda root, doc: self.observation(root))
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertIn('no committed moved:true witness', done.stdout)

    def test_real_legacy_pin_shape_is_validated_at_its_own_historical_source(self):
        def mutate(root, doc):
            path = root / 'twin/PIN.yaml'
            current = path.read_bytes()
            old = yaml.safe_load(current)
            del old['hub_commit']
            path.write_text(yaml.safe_dump(old))
            subprocess.run(['git', '-C', str(root), 'add', 'twin/PIN.yaml'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'commit.gpgsign=false',
                            '-c', 'core.hooksPath=/dev/null', 'commit', '-qm',
                            'synthetic prior legacy pin'], check=True, capture_output=True)
            self.observation(root)
            path.write_bytes(current)
        done = self.run_check(mutate)
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertIn('no committed moved:true witness', done.stdout)

    def test_unavailable_historical_source_remains_could_not_look(self):
        done = self.run_check(lambda root, doc: self.observation(root, adopter_ref='f' * 40))
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertIn('historical source PIN unavailable', done.stdout)

    def test_known_historical_source_pin_contradiction_fails(self):
        def mutate(root, doc):
            self.observation(root)
            path = root / 'observations/twin-sweep.jsonl'
            record = json.loads(path.read_text())
            record['twin_pin']['twin_version'] = '99.0.0'
            path.write_text(json.dumps(record) + '\n')
        done = self.run_check(mutate)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('recorded pin differs', done.stdout)

    def test_refusal_record_cannot_be_labelled_a_live_move(self):
        done = self.run_check(lambda root, doc: self.observation(
            root, status='review_required', emitter_exit=1, moved=True, detail='REFUSED: synthetic pin'))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('contradictory status/emitter_exit/moved', done.stdout)

    def test_malformed_committed_ledger_is_failure(self):
        def mutate(root, doc):
            (root / 'observations').mkdir()
            (root / 'observations/twin-sweep.jsonl').write_text('not JSON\n')
        done = self.run_check(mutate)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn('observation line 1', done.stdout)


if __name__ == '__main__':
    unittest.main()
