"""Flux RBAC IDs from original sample39879033938/1, artifact12470285514.

The literal entry is copied from crossplane-crds, not produced by inventory_id.
Flux cli-utils v1.2.2 pkg/object/objmetadata.go String() encodes RBAC colons.
"""
import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("five_facts_inventory", ROOT / "drift/five-facts.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)

ROLE = {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRole",
        "metadata": {"name": "kyverno:cloud-cr-view"}}
ACTUAL_ID = "_kyverno__cloud-cr-view_rbac.authorization.k8s.io_ClusterRole"


class CapturedRoleCluster:
    def __init__(self, entries, live=True):
        self.entries = entries
        self.live = live
        self.reachable = True

    def get(self, *args):
        if args == ("-n", "flux-system", "get", "kustomizations.kustomize.toolkit.fluxcd.io"):
            return {"items": [{"kind": "Kustomization", "metadata": {"name": "crossplane-crds"},
                               "status": {"inventory": {"entries": self.entries}}}]}
        if args == ("-n", "flux-system", "get", "resourcesets.fluxcd.controlplane.io"):
            return {"items": []}
        if args == ("get", "clusterrole.v1.rbac.authorization.k8s.io", "kyverno:cloud-cr-view"):
            return copy.deepcopy(ROLE) if self.live else None
        raise AssertionError(f"unexpected read: {args}")


class FluxInventoryEncoding(unittest.TestCase):
    def grade(self, entries, live=True):
        with patch.object(ff.rc, "render", return_value={ff.rc.key(ROLE): ROLE}):
            return ff.composed_set_facts(CapturedRoleCluster(entries, live), "v4.1.2")

    def test_literal_captured_role_entry_grades_fact5_true(self):
        f4, f5, bad = self.grade([{"id": ACTUAL_ID, "v": "v1"}])
        self.assertIs(f4["observed"], True)
        self.assertIs(f5["observed"], True, f5["why"])
        self.assertEqual(f5["objects_not_in_inventory"], [])
        self.assertEqual(f5["inventory_entries"], 1)
        self.assertEqual(bad, [])

    def test_genuinely_missing_inventory_role_remains_false(self):
        _f4, f5, _bad = self.grade([])
        self.assertIs(f5["observed"], False)
        self.assertEqual(f5["objects_not_in_inventory"], [ff.rc.key(ROLE)])

    def test_an_absent_live_role_with_inventory_still_remains_false(self):
        f4, f5, bad = self.grade([{"id": ACTUAL_ID, "v": "v1"}], live=False)
        self.assertIs(f4["observed"], False)
        self.assertIs(f5["observed"], False)
        self.assertEqual(bad, [ff.rc.key(ROLE)])

    def test_each_rbac_kind_encodes_every_name_colon(self):
        for kind in ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"):
            with self.subTest(kind=kind):
                obj = {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": kind,
                       "metadata": {"namespace": "bank", "name": "system:cloud:view"}}
                self.assertEqual(ff.inventory_id(obj),
                                 f"bank_system__cloud__view_rbac.authorization.k8s.io_{kind}")
        self.assertEqual(ff.inventory_id(ROLE), ACTUAL_ID)

    def test_colon_transcoding_is_limited_to_the_rbac_group_and_four_kinds(self):
        for api, kind, expected in (
            ("example.io/v1", "ClusterRole", "_system:cloud_example.io_ClusterRole"),
            ("rbac.authorization.k8s.io/v1", "Other", "_system:cloud_rbac.authorization.k8s.io_Other"),
            ("v1", "ConfigMap", "_system:cloud__ConfigMap"),
        ):
            with self.subTest(api=api, kind=kind):
                self.assertEqual(ff.inventory_id({"apiVersion": api, "kind": kind,
                                                  "metadata": {"name": "system:cloud"}}), expected)

    def test_ordinary_names_namespaces_groups_and_core_ids_are_unchanged(self):
        self.assertEqual(ff.inventory_id({"apiVersion": "rbac.authorization.k8s.io/v1",
                                         "kind": "Role", "metadata": {"namespace": "bank", "name": "reader"}}),
                         "bank_reader_rbac.authorization.k8s.io_Role")
        self.assertEqual(ff.inventory_id({"apiVersion": "v1", "kind": "Namespace",
                                         "metadata": {"name": "bank"}}), "_bank__Namespace")


if __name__ == "__main__":
    unittest.main()
