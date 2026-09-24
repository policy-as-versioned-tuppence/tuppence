"""Ticket 131: cut-release.yml lays the adopter and its parents out as compose-check does.

Run: python3 -m unittest discover -s .github/tests -p 'test_*.py'
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CutReleaseLayout(unittest.TestCase):
    """Ticket 131: the pre-tag verify reads the inputs the composition read.

    The comparison identity hashes every non-hidden file under the adopter.
    A parent checked out inside the adopter becomes part of that identity, so
    verify refused with 'comparison history does not match current source
    inputs'. cut-release.yml must lay parents out as compose-check does:
    the adopter in its own directory, every parent beside it.

    This module sits under .github/ on purpose. identity() skips hidden
    paths, so this test can change without changing the adopter's source
    identity. A test under tests/ would start a new comparison and make the
    committed composed/ refuse at the very verify this test guards.
    """
    NAME = 'tuppence'

    def setUp(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/cut-release.yml').read_text())
        self.steps = workflow['jobs']['cut']['steps']

    def _step(self, needle):
        found = [s for s in self.steps if needle in s.get('run', '')]
        self.assertEqual(len(found), 1, needle)
        return found[0]

    def test_adopter_and_parents_are_siblings(self):
        checkouts = [s for s in self.steps if s.get('uses', '').startswith('actions/checkout@')]
        own = [s for s in checkouts if 'repository' not in s.get('with', {})]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]['with'].get('path'), self.NAME)
        self.assertEqual(own[0]['with'].get('fetch-depth'), 0)
        for step in checkouts:
            path = step['with'].get('path', '.')
            self.assertNotIn('/', path)
            self.assertNotIn(path, ('.', ''), step)
        for step in self.steps:
            action = step.get('uses', '')
            if action.startswith('./'):
                self.assertTrue(action.startswith(f'./{self.NAME}/.github/actions/'), action)
            if action.endswith('/.github/actions/platform-tools'):
                self.assertEqual(step['with']['adopter-dir'], self.NAME)

    def test_verify_runs_from_the_workspace_with_parents_beside_the_adopter(self):
        step = self._step(' verify ')
        self.assertNotIn('working-directory', step)
        self.assertIn(f'{self.NAME}/.github/scripts/platform-tools.py --adopter-dir {self.NAME} '
                      f'--tools-dir platform-tools verify {self.NAME} --estate-clone .', step['run'])
        pinned = self._step('verify-pinned-checkouts.py')
        self.assertIn(f'{self.NAME}/gitops/platform/platform-pin.yaml platform', pinned['run'])

    def test_the_tag_is_refused_signed_and_pushed_in_the_adopter(self):
        order = [self.steps.index(self._step(n)) for n in (
            'verify-pinned-checkouts.py', ' verify ', 'git rev-parse "refs/tags/',
            'tag -s', 'git push origin')]
        self.assertEqual(order, sorted(order))
        for needle in ('git rev-parse "refs/tags/', 'tag -s', 'git push origin'):
            self.assertEqual(self._step(needle).get('working-directory'), self.NAME, needle)
        self.assertIn('gpg.x509.program=gitsign', self._step('tag -s')['run'])

    def test_this_module_is_outside_the_comparison_identity(self):
        relative = Path(__file__).resolve().relative_to(ROOT)
        self.assertTrue(any(part.startswith('.') for part in relative.parts), relative)


if __name__ == '__main__':
    unittest.main()
