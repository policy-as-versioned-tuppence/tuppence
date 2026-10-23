"""The actual declared feeds source must remain discoverable by Renovate."""
import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = 'gitops/flux-system/gotk-sync-feeds.yaml'


def expression(value):
    """Translate only RE2 named-group spelling for Python's regex engine."""
    return re.compile(re.sub(r'\(\?<([A-Za-z_][A-Za-z_0-9]*)>', r'(?P<\1>', value))


class FeedsSourceManagerTest(unittest.TestCase):
    def setUp(self):
        self.pin = (ROOT / PIN_PATH).read_text()
        ref = yaml.safe_load(self.pin)['spec']['ref']
        self.tag, self.commit = ref['tag'], ref['commit']
        self.assertRegex(self.tag, r'^recovery-expense/v[0-9]+\.[0-9]+\.[0-9]+$')
        self.assertRegex(self.commit, r'^[0-9a-f]{40}$')
        config = json.loads((ROOT / 'renovate.json').read_text())
        managers = [manager for manager in config['customManagers']
                    if manager.get('customType') == 'regex' and any(
                        re.search(pattern.strip('/'), PIN_PATH)
                        for pattern in manager.get('managerFilePatterns', []))]
        self.assertEqual(len(managers), 1, 'the declared feeds source needs exactly one manager')
        self.manager = managers[0]

    def test_real_declared_tag_and_commit_are_discovered(self):
        matches = [match for pattern in self.manager['matchStrings']
                   for match in expression(pattern).finditer(self.pin)]
        self.assertEqual(len(matches), 1, 'Renovate silently stopped matching the actual source pin')
        self.assertEqual(matches[0].group('currentValue'), self.tag.split('/', 1)[1])
        self.assertEqual(matches[0].group('currentDigest'), self.commit)
        self.assertEqual(self.manager['datasourceTemplate'], 'git-refs')
        self.assertEqual(self.manager['versioningTemplate'], 'semver')

    def test_actual_extractor_selects_only_the_source_release_family(self):
        extractor = expression(self.manager['extractVersionTemplate'])
        for tag, version in [(self.tag, self.tag.split('/', 1)[1]),
                             ('recovery-expense/v1.0.1', 'v1.0.1')]:
            with self.subTest(tag=tag):
                match = extractor.fullmatch(tag)
                self.assertIsNotNone(match)
                self.assertEqual(match.group('version'), version)
        self.assertIsNone(extractor.fullmatch('threat-register/v4.1.0'))
        self.assertIsNone(extractor.fullmatch('recovery-expense/not-a-version'))
        self.assertIsNone(extractor.fullmatch('recovery-expense/v1.0.1-invalid'))

    def test_malformed_digest_is_not_discovered(self):
        malformed = re.sub(r'(?m)^(\s*commit:\s*)' + re.escape(self.commit) + r'\s*$',
                           r'\g<1>not-a-commit', self.pin, count=1)
        self.assertNotEqual(malformed, self.pin)
        self.assertFalse(any(expression(pattern).search(malformed)
                             for pattern in self.manager['matchStrings']))

    def test_legacy_family_cannot_discover_the_current_declared_source(self):
        legacy = r'tag: threat-register/(?<currentValue>v[0-9.]+)\s*\n\s*commit: (?<currentDigest>[a-f0-9]{40})'
        self.assertIsNone(expression(legacy).search(self.pin))


if __name__ == '__main__':
    unittest.main()
