"""Eco-system ticket 147: the engine is declared once, in gitops/engine/kyverno.yaml, and read.

Run: python3 -m unittest discover -s .github/tests -p 'test_*.py'

The drift lane installs Kyverno from the declaration, and the offline CLI is the declared
engine's CLI. This module grades the two workflows a pull request would change, so a version or
checksum typed back into either of them fails here before it reaches a scheduled run.

This module sits under .github/ on purpose, like test_cut_release_layout.py: the comparison
identity skips hidden paths, so this test does not start a new comparison.
"""
from importlib import util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / '.github/scripts/engine_declaration.py'
DECLARATION = ROOT / 'gitops/engine/kyverno.yaml'
RELEASE_URL = re.compile(r'github\.com/kyverno/kyverno/releases/download')


def _reader():
    spec = util.spec_from_file_location('engine_declaration', READER)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow(name):
    import yaml
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


def _runs(steps):
    return '\n'.join(s.get('run', '') for s in steps)


class EngineDeclaration(unittest.TestCase):

    def test_the_committed_declaration_reads(self):
        engine = _reader().read(DECLARATION)
        self.assertRegex(engine['version'], r'^\d+\.\d+\.\d+$')
        self.assertTrue(engine['install_url'].endswith(f"/v{engine['version']}/install.yaml"))
        self.assertTrue(engine['cli_url'].endswith(
            f"/v{engine['version']}/kyverno-cli_v{engine['version']}_linux_x86_64.tar.gz"))

    def test_the_reader_refuses_every_planted_declaration(self):
        self.assertEqual(_reader().selfcheck(), 0)

    def _reader_step(self, steps, path):
        found = [s for s in steps if 'engine_declaration.py outputs' in s.get('run', '')]
        self.assertEqual(len(found), 1, 'exactly one step reads the declaration')
        self.assertEqual(found[0].get('id'), 'engine')
        self.assertIn(path, found[0]['run'])
        return found[0]

    def test_the_drift_lane_installs_the_declared_engine_once(self):
        workflow = _workflow('drift-sample.yml')
        self.assertNotIn('KYVERNO_VERSION', workflow['env'])
        self.assertNotIn('KYVERNO_SHA256', workflow['env'])
        steps = workflow['jobs']['sample']['steps']
        reader = self._reader_step(steps, 'gitops/engine/kyverno.yaml')
        installs = [s for s in steps if 'kyverno.yaml' in s.get('run', '') and 'curl' in s.get('run', '')
                    and s is not reader]
        self.assertEqual(len(installs), 1, 'one step downloads the engine')
        env = installs[0].get('env', {})
        self.assertEqual(env.get('KYVERNO_INSTALL_URL'), '${{ steps.engine.outputs.install_url }}')
        self.assertEqual(env.get('KYVERNO_INSTALL_SHA256'), '${{ steps.engine.outputs.install_sha256 }}')
        run = installs[0]['run']
        self.assertIn('curl -sSL -o kyverno.yaml "${KYVERNO_INSTALL_URL}"', run)
        self.assertIn('echo "${KYVERNO_INSTALL_SHA256}  kyverno.yaml" | sha256sum -c -', run)
        text = _runs(steps)
        self.assertIsNone(RELEASE_URL.search(text), 'no Kyverno release URL is typed into the lane')
        applies = [line for line in text.splitlines()
                   if 'apply' in line and 'kyverno.yaml' in line and not line.strip().startswith('#')]
        self.assertEqual(len(applies), 1, applies)
        self.assertIn('--server-side', applies[0])

    def test_shift_left_installs_the_declared_cli(self):
        steps = _workflow('shift-left.yml')['jobs']['shift-left']['steps']
        reader = self._reader_step(steps, 'gitops/engine/kyverno.yaml')
        index = steps.index(reader)
        cli = steps[index + 1]
        env = cli.get('env', {})
        self.assertEqual(env.get('KYVERNO_VERSION'), '${{ steps.engine.outputs.version }}')
        self.assertEqual(env.get('KYVERNO_CLI_URL'), '${{ steps.engine.outputs.cli_url }}')
        self.assertEqual(env.get('KYVERNO_CLI_SHA256'), '${{ steps.engine.outputs.cli_sha256 }}')
        self.assertIn('echo "${KYVERNO_CLI_SHA256}  kyverno.tar.gz" | sha256sum -c -', cli['run'])
        self.assertIn('"${reported}" != "${KYVERNO_VERSION}"', cli['run'])
        self.assertIsNone(RELEASE_URL.search(_runs(steps)), 'no Kyverno release URL is typed here')


if __name__ == '__main__':
    unittest.main()
