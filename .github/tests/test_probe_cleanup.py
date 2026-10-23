"""Pure transport simulation over the actual sampler; never invokes kubectl or native code."""
import unittest
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def exercise(mode='async', case='healthy'):
    path = ROOT.parents[1] / 'drift/five-facts.py'
    spec = importlib.util.spec_from_file_location('actual_sampler_probe_cleanup', path)
    sampler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sampler)
    owned = {sampler.CAGE_FALLCLOSED_NS, sampler.CAGE_REFERENCE_NS}
    namespaces = {'business-namespace': 'Active'}
    pods = {}
    calls = []

    def transport(argv, *, input=None, capture_output=False, text=False, timeout=None):
        assert argv[0] == 'kubectl', 'unexpected subprocess blocked: ' + repr(argv)
        args = argv[4:]
        calls.append({'args': list(args), 'argv': list(argv), 'subprocess_timeout': timeout})
        code, output = 0, ''
        if args[:2] == ['apply', '-f']:
            for obj in json.loads(input)['items']:
                if obj['kind'] == 'Namespace':
                    namespaces[obj['metadata']['name']] = 'Active'
                elif obj['kind'] == 'Pod':
                    ns = obj['metadata']['namespace']
                    if case == 'admission-refused' and ns == sampler.CAGE_FALLCLOSED_NS:
                        code, output = 1, 'synthetic API refusal of fall-closed pod'
                        continue
                    labels = dict(obj['metadata'].get('labels', {}))
                    if ns == sampler.CAGE_FALLCLOSED_NS:
                        labels.update({'posture.acme.io/tier': 'isolated', 'posture.acme.io/caged': 'true'})
                    pods[ns] = {'metadata': {'name': sampler.CAGE_POD, 'namespace': ns, 'labels': labels},
                        'spec': {'priorityClassName': 'cage-isolated-5-0-0' if ns == sampler.CAGE_FALLCLOSED_NS else '',
                                 'priority': -10000 if ns == sampler.CAGE_FALLCLOSED_NS else None,
                                 'containers': [{'name': 'app', 'image': 'SYNTHETIC-STAND-IN'}]},
                        'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'},
                                                                      {'type': 'PodScheduled', 'status': 'True'}]}}
        elif args[:2] == ['delete', 'ns']:
            # A successful asynchronous Kubernetes delete acknowledges the request;
            # finalization may leave the Namespace and its Pod present afterwards.
            assert set(args[2:4]) == owned
            for ns in owned:
                if mode == 'synchronous' or (mode == 'async' and '--wait=true' in args):
                    namespaces.pop(ns, None)
                    pods.pop(ns, None)
                else:
                    namespaces[ns] = 'Terminating'
            output = 'ordinary namespace deletion acknowledged'
            if mode in ('delete-error', 'timeout'):
                code = 1
                output = 'SYNTHETIC delete permission denied' if mode == 'delete-error' else 'SYNTHETIC timed out waiting for deletion'
        elif args[:2] == ['wait', '--for=delete']:
            # Completion semantics, available for the later one-variable fix loop.
            assert set(args[2:4]) == {'namespace/' + n for n in owned}
            for ns in owned:
                namespaces.pop(ns, None)
                pods.pop(ns, None)
            output = 'ordinary namespace deletion completed'
        elif args and args[0] == '-n' and 'exec' in args:
            reached = args[1] == sampler.CAGE_REFERENCE_NS and case != 'reference-broken'
            output = sampler.CAGE_RC_MARKER + ('0' if reached else '1')
            code = 0 if reached else 1
        elif args and 'get' in args:
            if args[:2] == ['get', 'namespace']:
                if mode == 'read-error':
                    return subprocess.CompletedProcess(argv, 1, stdout='', stderr='SYNTHETIC namespace read forbidden')
                output = '\n'.join('namespace/' + n for n in sorted(owned.intersection(namespaces)))
                return subprocess.CompletedProcess(argv, 0, stdout=output, stderr='')
            if args[:2] == ['get', 'mutatingpolicies.policies.kyverno.io']:
                obj = {'items': [{'metadata': {'name': 'cage-tier-5-0-0'},
                                  'status': {'conditionStatus': {'ready': True}}}]}
            elif 'priorityclasses.scheduling.k8s.io' in args:
                obj = {'items': [{'metadata': {'name': 'cage-baseline-5-0-0'}, 'value': -10},
                                 {'metadata': {'name': 'cage-isolated-5-0-0'}, 'value': -10000}]}
            elif 'networkpolicies.networking.k8s.io' in args:
                obj = {'items': [{'metadata': {'name': 'cage-reach-isolated'},
                    'spec': {'podSelector': {'matchLabels': {'posture.acme.io/tier': 'isolated'}},
                             'policyTypes': ['Ingress', 'Egress']}}]} if args[1] == sampler.CAGE_FALLCLOSED_NS else {'items': []}
            elif 'pod' in args:
                obj = pods.get(args[1])
                if obj is None:
                    code, output = 1, 'Error from server (NotFound): pod not found'
            elif 'kubernetes' in args:
                obj = {'spec': {'clusterIP': '10.96.0.1'}}
            else:
                raise AssertionError('unmodeled API read: ' + repr(args))
            if code == 0:
                output = json.dumps(obj)
        else:
            raise AssertionError('unmodeled kubectl operation: ' + repr(args))
        return subprocess.CompletedProcess(argv, code, stdout=output, stderr='')

    # Only the process boundary and wall-clock sleep are replaced. The real
    # Cluster.get/run, cage_facts, admission, bottom and reach logic all execute.
    cluster = sampler.Cluster('PURE-NO-SUCH-CONTEXT')
    cluster.reachable = case != 'unreachable'
    with patch.object(sampler.subprocess, 'run', side_effect=transport), patch.object(sampler.time, 'sleep', lambda _: None):
        six, seven = sampler.cage_facts(cluster, '' if case == 'no-image' else 'SYNTHETIC-STAND-IN')
    expected = {'healthy': (True, True), 'admission-refused': (False, None), 'reference-broken': (True, None), 'no-image': (None, None), 'unreachable': (None, None)}[case]
    assert (six['observed'], seven['observed']) == expected, (six, seven)
    assert namespaces['business-namespace'] == 'Active'
    live_owned = sorted(owned.intersection(namespaces))
    return {'fact6': six, 'fact7': seven, 'remaining': live_owned, 'calls': calls, 'owned': owned}


class ProbeCleanup(unittest.TestCase):
    def test_waits_for_actual_owned_namespace_completion(self):
        result = exercise()
        self.assertEqual(result['remaining'], [], 'sampler returned while owned probe Namespaces still exist')
        for fact in (result['fact6'], result['fact7']):
            self.assertTrue(fact['cleanup']['completed'])
            self.assertTrue(fact['cleanup']['absence_confirmed'])
        calls = result['calls']
        deletion = next(c for c in calls if c['args'][:2] == ['delete', 'ns'])
        self.assertEqual(set(deletion['args'][2:4]), result['owned'])
        self.assertIn('--wait=true', deletion['args'])
        self.assertIn('--timeout=120s', deletion['args'])
        self.assertIn('--request-timeout=130s', deletion['args'])
        self.assertIn('--request-timeout=30s', deletion['argv'])
        self.assertEqual(deletion['subprocess_timeout'], 180)
        reads = [c for c in calls if c['args'][:2] == ['get', 'namespace']]
        self.assertEqual(len(reads), 1)
        self.assertEqual(set(reads[0]['args'][2:4]), result['owned'])
        self.assertIn('--request-timeout=20s', reads[0]['args'])

    def test_successful_delete_still_requires_confirmed_absence(self):
        result = exercise('unconfirmed')
        self.assertTrue(result['remaining'])
        self.assertFalse(result['fact6']['cleanup']['completed'])
        self.assertFalse(result['fact6']['cleanup']['absence_confirmed'])
        self.assertIn('namespace/', result['fact6']['cleanup']['absence_output'])

    def test_delete_failure_is_explicit_without_changing_facts(self):
        result = exercise('delete-error')
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (True, True))
        for fact in (result['fact6'], result['fact7']):
            self.assertFalse(fact['cleanup']['completed'])
            self.assertEqual(fact['cleanup']['delete_exit_code'], 1)
            self.assertIn('permission denied', fact['cleanup']['delete_output'])

    def test_timeout_is_explicit_without_changing_facts(self):
        result = exercise('timeout')
        self.assertFalse(result['fact6']['cleanup']['completed'])
        self.assertIn('timed out', result['fact6']['cleanup']['delete_output'])
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (True, True))

    def test_absence_read_failure_is_not_confirmed(self):
        result = exercise('read-error')
        self.assertFalse(result['fact6']['cleanup']['completed'])
        self.assertFalse(result['fact6']['cleanup']['absence_confirmed'])
        self.assertEqual(result['fact6']['cleanup']['absence_exit_code'], 1)
        self.assertIn('forbidden', result['fact6']['cleanup']['absence_output'])

    def test_admission_refusal_remains_false_on_successful_cleanup(self):
        result = exercise(case='admission-refused')
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (False, None))
        self.assertTrue(result['fact6']['cleanup']['completed'])

    def test_admission_refusal_survives_cleanup_failure(self):
        result = exercise('delete-error', 'admission-refused')
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (False, None))
        self.assertFalse(result['fact6']['cleanup']['completed'])

    def test_broken_reference_remains_unmeasured_on_successful_cleanup(self):
        result = exercise(case='reference-broken')
        self.assertIsNone(result['fact7']['observed'])
        self.assertTrue(result['fact7']['cleanup']['completed'])

    def test_broken_reference_survives_cleanup_failure(self):
        result = exercise('timeout', 'reference-broken')
        self.assertIsNone(result['fact7']['observed'])
        self.assertFalse(result['fact7']['cleanup']['completed'])

    def test_missing_image_creates_and_deletes_nothing(self):
        result = exercise(case='no-image')
        self.assertEqual(result['calls'], [])
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (None, None))

    def test_unreachable_cluster_creates_and_deletes_nothing(self):
        result = exercise(case='unreachable')
        self.assertEqual(result['calls'], [])
        self.assertEqual((result['fact6']['observed'], result['fact7']['observed']), (None, None))


if __name__ == '__main__':
    unittest.main(verbosity=2)
