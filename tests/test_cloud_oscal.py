"""Actual pinned converter observations must include the separately signed cloud mapping."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cloud_oscal_lane', ROOT / 'drift/oscal_lane.py')
assert spec is not None and spec.loader is not None
lane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lane)


class CloudOscal(unittest.TestCase):
    def collect(self, result='fail', fault=None):
        platform = Path(os.environ.get('PAVC_TEST_PLATFORM', str(ROOT.parent / 'platform')))
        self.assertTrue((platform / 'oscal/result2oscal.py').is_file(), 'the real pinned converter is required')
        report = {'scope': {'apiVersion': 'rds.aws.m.upbound.io/v1beta1', 'kind': 'Instance',
                  'namespace': 'tuppence', 'name': 'datastore-rds-noncompliant', 'uid': 'synthetic-subject'},
                  'results': [{'policy': 'require-rds-multi-az-5-0-0', 'result': result}]}
        files = {str(path.relative_to(ROOT)): path.read_text() for path in (ROOT / 'composed').rglob('*') if path.is_file()}
        if fault == 'missing-component':
            files.pop('composed/cloud/v1.0.0/component-definition.json')
        elif fault == 'conflicting-map':
            comp = json.loads(files['composed/cloud/v1.0.0/component-definition.json'])
            requirement = comp['component-definition']['components'][0]['control-implementations'][0]['implemented-requirements'][0]
            requirement['props'][0]['value'] = 'require-nonroot'
            files['composed/cloud/v1.0.0/component-definition.json'] = json.dumps(comp)
        elif fault == 'old-composed-tag':
            files.pop('composed/CLOUD-PARENT.json')
            header = yaml.safe_load(files['composed/HEADER.yaml'])
            header.pop('cloud-package')
            files['composed/HEADER.yaml'] = yaml.safe_dump(header)
        class API:
            reason = ''
            def get(self, *args):
                return {'items': [copy.deepcopy(report)] if args[1].startswith('policyreports.') else []}
        def read(*args):
            path = args[-1].partition(':')[2]
            return files.get(path)
        sampler = SimpleNamespace(Cluster=lambda _: API(), now=lambda: '2026-10-17T00:00:00Z',
            rc=SimpleNamespace(pinned_tag=lambda: 'v9.9.9', render=lambda _: {}), _git_output=read)
        original_load = lane.load
        with patch.object(lane, 'load', side_effect=lambda path, name: sampler if name == 'five_facts_instrument' else original_load(path, name)):
            return lane.collect('synthetic-no-cluster', platform)

    def test_failed_cloud_check_uses_native_converter_and_retains_missing_price_join(self):
        row = self.collect()
        self.assertEqual(row['status'], 'observed', row)
        findings = row['assessment_results']['assessment-results']['results'][0]['findings']
        self.assertTrue(any(f['target']['target-id'] == 'cp-10' and f['target']['status']['state'] == 'not-satisfied' for f in findings))
        self.assertEqual(len(row['missing_risk_observations']), 1, 'an unpriced cloud failure must remain missing a risk')
        self.assertEqual(row['unmapped_failed_results'], [])
        self.assertEqual(row['risks'], [], 'the collector must not invent a cloud price')

    def test_successful_cloud_result_creates_an_observation_without_inventing_risk(self):
        row = self.collect('pass')
        findings = row['assessment_results']['assessment-results']['results'][0]['findings']
        self.assertTrue(any(f['target']['target-id'] == 'cp-10' and f['target']['status']['state'] == 'satisfied' for f in findings))
        self.assertEqual(row['missing_risk_observations'], [])
        self.assertEqual(row['risks'], [])

    def test_missing_or_conflicting_signed_mapping_cannot_silently_disappear(self):
        for fault in ('missing-component', 'conflicting-map'):
            with self.subTest(fault=fault):
                row = self.collect(fault=fault)
                self.assertEqual(row['status'], 'could-not-look', row)
                self.assertIn('cloud', row['why'])

    def test_old_composed_tag_does_not_consume_a_future_worktree_cloud_mapping(self):
        row = self.collect(fault='old-composed-tag')
        self.assertEqual(row['unmapped_failed_results'], ['require-rds-multi-az-5-0-0'])
        self.assertEqual(row['assessment_results']['assessment-results']['results'][0]['findings'], [])


if __name__ == '__main__':
    unittest.main()
