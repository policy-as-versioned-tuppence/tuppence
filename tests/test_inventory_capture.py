"""Same-read diagnostic retention; subprocess stand-ins never reach a cluster."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import io
import contextlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("five_facts_capture", ROOT / "drift/five-facts.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)


class InventoryCapture(unittest.TestCase):
    def test_same_inventory_reads_retain_parser_input_without_reserialization(self):
        raw = ('{\n "items": [{"kind":"Kustomization","metadata":{"name":"café"},'
               '"status":{"inventory":{"entries":[{"id":"_role_rbac.authorization.k8s.io_ClusterRole"}]}}}] }\n')
        replies = [subprocess.CompletedProcess([], 0, raw, ""),
                   subprocess.CompletedProcess([], 0, '{ "items": [] }\n', "")]
        with tempfile.TemporaryDirectory() as tmp, patch.object(ff.subprocess, "run", side_effect=replies) as run:
            evidence = ff.InventoryEvidence(tmp)
            cluster = ff.Cluster("fixture-context")
            found = ff.inventory_ids(cluster, evidence)
            self.assertEqual(found, {"_role_rbac.authorization.k8s.io_ClusterRole": "Kustomization/café"})
            self.assertEqual((Path(tmp) / "01-kustomizations.parser-input.txt").read_bytes(), raw.encode("utf-8"))
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual([r["ordinal"] for r in manifest["reads"]], [1, 2])
            self.assertEqual(manifest["reads"][0]["representation"], "subprocess-text-stdout-utf8")
            self.assertEqual(manifest["reads"][0]["argv"], ["kubectl", "--context", "fixture-context", "--request-timeout=20s", "-n", "flux-system", "get", "kustomizations.kustomize.toolkit.fluxcd.io", "-o", "json"])
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.kwargs, {"capture_output": True, "text": True, "timeout": 60})

    def test_diagnostic_file_failure_cannot_replace_an_inventory_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "not-a-directory"
            blocked.write_text("occupied")
            evidence = ff.InventoryEvidence(str(blocked))
            reply = subprocess.CompletedProcess([], 0, '{"items": []}\n', "")
            with patch.object(ff.subprocess, "run", return_value=reply), contextlib.redirect_stderr(io.StringIO()) as err:
                result = ff.Cluster("fixture").get("-n", "flux-system", "get", "kustomizations.kustomize.toolkit.fluxcd.io", inventory_evidence=evidence)
            self.assertEqual(result, {"items": []})
            self.assertIn("[inventory-evidence]", err.getvalue())
            self.assertTrue(evidence.failed)

    def test_finish_binds_exact_emitted_rows_without_adding_record_fields(self):
        records = [{"source": "test-source", "party": "test-party", "pin": {"commit": "abc"}}]
        original = json.dumps(records)
        with tempfile.TemporaryDirectory() as tmp:
            evidence = ff.InventoryEvidence(tmp)
            evidence.finish(records, '{ "noncanonical": "café" }\n')
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(json.dumps(records), original)
            self.assertEqual(manifest["sample"]["normalized_rows"], 1)
            self.assertEqual(manifest["sample"]["normalized_jsonl_sha256"], "1fb7dc1b8e80c125f83831a4adf8ae147e1316516057a74820e1704d228750a3")

    def test_answer_error_and_timeout_semantics_match_without_capture(self):
        cases = [
            subprocess.CompletedProcess([], 0, '{\r\n "items": [], "note": "café"\r\n}\r\n', ""),
            subprocess.CompletedProcess([], 0, "not json\n", ""),
            subprocess.CompletedProcess([], 1, "", "Error: NotFound\n"),
            subprocess.CompletedProcess([], 1, "", "context error\nprivate diagnostic stderr"),
            OSError("not executable"),
            subprocess.TimeoutExpired(["kubectl"], 60, output=b'{"items": [', stderr=b"private timeout stderr"),
        ]
        args = ("-n", "flux-system", "get", "kustomizations.kustomize.toolkit.fluxcd.io")
        for reply in cases:
            with self.subTest(reply=type(reply).__name__), tempfile.TemporaryDirectory() as tmp:
                def answer(*_args, **_kwargs):
                    if isinstance(reply, Exception):
                        raise reply
                    return reply
                plain, retained = ff.Cluster("fixture"), ff.Cluster("fixture")
                with patch.object(ff.subprocess, "run", side_effect=answer) as run:
                    expected = plain.get(*args)
                    actual = retained.get(*args, inventory_evidence=ff.InventoryEvidence(tmp))
                self.assertEqual((actual, retained.reachable, retained.reason),
                                 (expected, plain.reachable, plain.reason))
                self.assertEqual(run.call_count, 2)
                manifest = json.loads((Path(tmp) / "manifest.json").read_text())
                self.assertNotIn("private", json.dumps(manifest))
                if isinstance(reply, subprocess.CompletedProcess):
                    self.assertEqual((Path(tmp) / "01-kustomizations.parser-input.txt").read_bytes(),
                                     reply.stdout.encode("utf-8"))
                elif isinstance(reply, subprocess.TimeoutExpired):
                    row = manifest["reads"][0]
                    self.assertEqual(row["representation"], "timeout-partial-bytes")
                    self.assertEqual((Path(tmp) / row["file"]).read_bytes(), b'{"items": [')
                    self.assertFalse(row["parse_available"])
                else:
                    self.assertFalse(manifest["reads"][0]["stdout_present"])

    def test_capture_is_narrow_and_disabled_reads_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            reply = subprocess.CompletedProcess([], 0, '{"items": []}', "")
            with patch.object(ff.subprocess, "run", return_value=reply):
                ff.inventory_ids(ff.Cluster("fixture"))
            self.assertEqual(list(Path(tmp).iterdir()), [])
            evidence = ff.InventoryEvidence(tmp)
            with contextlib.redirect_stderr(io.StringIO()):
                evidence.retain(["kubectl", "get", "secrets"], "now", "secret-body", 0)
            self.assertTrue(evidence.failed)
            self.assertNotIn("secret-body", "".join(p.read_text() for p in Path(tmp).iterdir()))


if __name__ == "__main__":
    unittest.main()
