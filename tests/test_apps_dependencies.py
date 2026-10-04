"""Native app admission follows the actual signed composed delivery graph."""
import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_composed


def assert_ordered(test, apps, generated):
    """Require every generated policy route before apps, with no unknown edge or cycle."""
    policies = [obj for obj in generated if obj.get('kind') == 'Kustomization']
    key = lambda obj: (obj['metadata'].get('namespace', ''), obj['metadata']['name'])
    nodes = {key(obj): obj for obj in [apps, *policies]}
    test.assertEqual(len(nodes), len(policies) + 1, 'duplicate Kustomization name')
    graph = {}
    for node, obj in nodes.items():
        dependencies = [(dep.get('namespace', node[0]), dep['name'])
                        for dep in obj['spec'].get('dependsOn', [])]
        test.assertEqual(len(dependencies), len(set(dependencies)), 'duplicate dependency')
        test.assertTrue(set(dependencies) <= nodes.keys(), 'dependency names no generated route')
        graph[node] = dependencies
    test.assertEqual(set(graph[key(apps)]), {key(obj) for obj in policies},
                     'apps must wait for every composed policy route and machinery')
    visited, active = set(), set()

    def visit(node):
        test.assertNotIn(node, active, 'Flux dependency cycle')
        if node in visited:
            return
        active.add(node)
        for dependency in graph[node]:
            visit(dependency)
        active.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


class AppAdmissionOrder(unittest.TestCase):
    def setUp(self):
        self.apps = next(obj for obj in yaml.safe_load_all(
            (ROOT / 'gitops/flux-system/gotk-sync.yaml').read_text())
            if obj and obj.get('kind') == 'Kustomization')
        # Expand the repository's actual ResourceSet template and declared array.
        self.generated = render_composed.expand(repo=str(ROOT))

    def test_current_native_apps_wait_for_the_actual_composed_graph(self):
        assert_ordered(self, self.apps, self.generated)

    def test_missing_or_invented_route_is_rejected(self):
        for change in ('missing', 'invented'):
            with self.subTest(change=change):
                apps = copy.deepcopy(self.apps)
                if change == 'missing':
                    apps['spec']['dependsOn'] = apps['spec'].get('dependsOn', [])[:-1]
                else:
                    apps['spec']['dependsOn'] = [{'name': 'no-such-composed-route'}]
                with self.assertRaises(AssertionError):
                    assert_ordered(self, apps, self.generated)

    def test_composed_route_waiting_on_apps_is_a_cycle(self):
        apps = copy.deepcopy(self.apps)
        apps['spec']['dependsOn'] = [
            {'name': obj['metadata']['name']}
            for obj in self.generated if obj.get('kind') == 'Kustomization']
        generated = copy.deepcopy(self.generated)
        route = next(obj for obj in generated if obj.get('kind') == 'Kustomization')
        route['spec']['dependsOn'] = [{'name': apps['metadata']['name']}]
        with self.assertRaisesRegex(AssertionError, 'cycle'):
            assert_ordered(self, apps, generated)

    def test_duplicate_route_is_rejected(self):
        apps = copy.deepcopy(self.apps)
        apps["spec"]["dependsOn"] = [{"name": obj["metadata"]["name"]} for obj in self.generated if obj.get("kind") == "Kustomization"]
        apps["spec"]["dependsOn"].append(copy.deepcopy(apps["spec"]["dependsOn"][0]))
        with self.assertRaisesRegex(AssertionError, "duplicate dependency"):
            assert_ordered(self, apps, self.generated)
