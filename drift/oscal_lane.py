#!/usr/bin/env python3
"""Ticket 155: collect PolicyReports as an observation and grade their real cage-risk joins."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "drift"
LOG = HERE / "oscal-samples.jsonl"
KIND = "flux.oscal-lane/v1"


def selfcheck() -> int:
    fail = {"uuid": "failed-observation", "props": [{"name": "result", "value": "fail"}]}
    passed = {"uuid": "passed-observation", "props": [{"name": "result", "value": "pass"}]}
    result = {"observations": [fail, passed], "findings": [{"target": {"status": {"state": "not-satisfied"}},
              "related-observations": [{"observation-uuid": fail["uuid"]}, {"observation-uuid": passed["uuid"]}]}]}
    assessment = {"assessment-results": {"results": [result]}}
    assert missing_risks(assessment, []) == ["failed-observation"], "a failed observation needs a cage risk"
    risk = {"related-observations": [{"observation-uuid": "failed-observation"}]}
    assert missing_risks(assessment, [risk]) == [], "the actual risk resolves the failed observation"
    assert missing_risks(assessment, [{"related-observations": [{"observation-uuid": "somebody-else"}]}]) == ["failed-observation"]
    # One UUID can be reported by several served versions. A later non-failure
    # must never hide the failed observation to which this finding points.
    for non_failure in ("skip", "pass"):
        collision = {"uuid": fail["uuid"], "props": [{"name": "result", "value": non_failure}]}
        for observations in ([fail, passed, collision], [collision, passed, fail]):
            view: dict = copy.deepcopy(assessment)
            view["assessment-results"]["results"][0]["observations"] = observations
            assert missing_risks(view, []) == ["failed-observation"], \
                f"same-ID {non_failure} must not hide failure in either observation order"
            assert missing_risks(view, [risk]) == [], "a real risk still resolves a duplicate-ID failure"
            view["assessment-results"]["results"][0]["findings"][0]["target"]["status"]["state"] = "satisfied"
            assert missing_risks(view, []) == [], "a satisfied finding creates no missing risk"
        without_failure: dict = copy.deepcopy(assessment)
        without_failure["assessment-results"]["results"][0]["observations"] = [collision, passed]
        assert missing_risks(without_failure, []) == [], "non-failure-only observations need no risk"
    unlinked: dict = copy.deepcopy(assessment)
    unlinked["assessment-results"]["results"][0]["observations"].append({"uuid": "unlinked", "props": None})
    assert missing_risks(unlinked, []) == ["failed-observation"], "unlinked properties are not interpreted"
    unlinked["assessment-results"]["results"][0]["observations"][-1]["props"] = 42
    assert missing_risks(unlinked, []) == ["failed-observation"], "unlinked malformed properties are not interpreted"
    malformed: dict = copy.deepcopy(assessment)
    malformed["assessment-results"]["results"][0]["observations"].append({"props": [{"name": "result", "value": "skip"}]})
    try:
        missing_risks(malformed, [])
    except KeyError:
        pass
    else:
        raise AssertionError("every observation must still carry its UUID")
    # A bare link is not a priced Cage decision. This fixture exercises the collector's
    # validation only; the composer tests bind the real select()/oscal_risk() pair.
    decision = {"action": "Cage", "org": "fixture", "tier": "isolated", "reason": "fixture decision",
                "tcor": {"residual": 12, "cost_of_controls": 3, "tcor": 15}}
    binding = {"subject": "fixture/workload", "policy": "check", "control": "ac-6"}
    risk = {"related-observations": [{"observation-uuid": "failed-observation"}],
            "fixture-priced-residual": 12}
    from types import SimpleNamespace
    engine = SimpleNamespace(oscal_risk=lambda value, **named: risk)
    entry = {"party": "fixture", "rule": "fixture/check@1.0.0", "tier": "isolated", "residual": 12,
             "decision": decision, "binding": binding, "oscal_risk": risk}
    pod = {"metadata": {"namespace": "fixture", "name": "workload", "labels": {
        "policy-as-versioned.dev/policy-version": "1.0.0", "posture.acme.io/tier": "isolated",
        "posture.acme.io/caged": "true"}}}
    valid, errors = validated_risks({"cages": [entry]}, {"check": "ac-6"}, engine, lambda *_: pod)
    assert valid == [risk] and not errors
    for field, value in (("decision", None), ("binding", None), ("oscal_risk", {"related-observations": risk["related-observations"]})):
        valid, errors = validated_risks({"cages": [{**entry, field: value}]}, {"check": "ac-6"}, engine, lambda *_: pod)
        assert not valid and errors, field
    wrong_pod = json.loads(json.dumps(pod))
    wrong_pod["metadata"]["labels"]["posture.acme.io/tier"] = "baseline"
    assert validated_risks({"cages": [entry]}, {"check": "ac-6"}, engine, lambda *_: wrong_pod)[1]
    assert validated_risks({"cages": [entry]}, {"check": "ac-6"}, engine, lambda *_: None)[1]
    assert validated_risks({"cages": [entry]}, {"check": "cm-6"}, engine, lambda *_: pod)[1]
    assert validated_risks({"risks": [risk]}, {"check": "ac-6"}, engine, lambda *_: pod)[1]
    # The public collector must distinguish an answered empty list from an API it could not read.
    import tempfile
    from types import SimpleNamespace
    from unittest.mock import patch

    class ReportAPI:
        reason = "forbidden: cannot list PolicyReports"

        def __init__(self, answered: bool):
            self.answered = answered

        def get(self, *args: str) -> dict | None:
            return {"items": []} if self.answered else None

    with tempfile.TemporaryDirectory() as directory:
        platform = Path(directory)
        (platform / "oscal").mkdir()
        (platform / "oscal/component-definition.json").write_text("{}")
        converter = SimpleNamespace(check_to_control=lambda _: {})
        for answered in (False, True):
            sampler = SimpleNamespace(Cluster=lambda _: ReportAPI(answered), now=lambda: "2026-10-03T00:00:00Z",
                                      rc=SimpleNamespace(render=lambda _: {}, pinned_tag=lambda: "v1.0.0"))
            with patch(__name__ + ".load", side_effect=lambda path, name: sampler if name == "five_facts_instrument" else converter):
                row = collect("fixture", platform)
            assert row["status"] == "could-not-look"
            if answered:
                assert row["why"] == "no PolicyReport existed on the lane cluster before teardown"
            else:
                assert "PolicyReport API could not be read" in row["why"], row
                assert "forbidden" in row["why"], row
    print("ok  OSCAL lane: failed observations require a real risk link, satisfied observations do not")
    return 0


def missing_risks(assessment: dict, risks: list[dict]) -> list[str]:
    failed = set()
    for result in (assessment.get("assessment-results") or {}).get("results") or []:
        observations: dict[str, list[dict]] = {}
        for observation in result.get("observations") or []:
            observations.setdefault(observation["uuid"], []).append(observation)
        for finding in result.get("findings") or []:
            if ((finding.get("target") or {}).get("status") or {}).get("state") != "not-satisfied":
                continue
            for link in finding.get("related-observations") or []:
                ident = link["observation-uuid"]
                if any(prop.get("name") == "result" and prop.get("value") == "fail"
                       for observation in observations.get(ident, [])
                       for prop in observation.get("props") or []):
                    failed.add(ident)
    linked = {link["observation-uuid"] for risk in risks for link in risk.get("related-observations") or []}
    return sorted(failed - linked)


def validated_risks(evidence: dict, mapping: dict, engine, read_pod) -> tuple[list[dict], list[str]]:
    """Re-derive each risk from its carried Cage decision and verify its live Pod binding.

    No institutional price, agent price or free-standing observation link supplies a
    workload decision. Unbound failures therefore remain missing joins.
    """
    risks, errors = [], []
    if evidence.get("risks"):
        errors.append("free-standing risks have no carried workload Cage decision")
    seen = set()
    for entry in evidence.get("cages") or []:
        if not isinstance(entry, dict):
            errors.append("a carried cage is not a decision record")
            continue
        if not entry.get("binding") and not entry.get("oscal_risk"):
            continue
        binding, decision, risk = entry.get("binding"), entry.get("decision"), entry.get("oscal_risk")
        try:
            if (not isinstance(binding, dict) or set(binding) != {"subject", "policy", "control"}
                    or not all(isinstance(value, str) and value for value in binding.values())):
                raise ValueError("risk has no explicit subject/policy/control binding")
            subject = binding["subject"]
            if subject.count("/") != 1:
                raise ValueError("risk subject must name one namespace/Pod")
            namespace, name = subject.split("/")
            if not namespace or not name or mapping.get(binding["policy"]) != binding["control"]:
                raise ValueError("risk binding differs from the pinned publisher's control mapping")
            policy, separator, version = str(entry.get("rule", "")).rsplit("/", 1)[-1].partition("@")
            if not separator or not version or policy != binding["policy"]:
                raise ValueError("risk binding names a different check from the priced restatement")
            key = (subject, binding["policy"])
            if key in seen:
                raise ValueError("duplicate bound risks would duplicate one workload decision")
            seen.add(key)
            if (not isinstance(decision, dict) or decision.get("action") != "Cage"
                    or decision.get("org") != entry.get("party") or not decision.get("reason")
                    or decision.get("tier") != entry.get("tier")):
                raise ValueError("risk has no matching carried Cage decision")
            tcor = decision.get("tcor") or {}
            amounts = [tcor.get(key) for key in ("residual", "cost_of_controls", "tcor")]
            if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in amounts)
                    or not math.isclose(amounts[0] + amounts[1], amounts[2])
                    or entry.get("residual") != amounts[0]):
                raise ValueError("carried Cage decision has no consistent finite priced residual and cost")
            if risk != engine.oscal_risk(decision, **binding):
                raise ValueError("carried OSCAL risk does not re-derive from that Cage decision and binding")
            live = read_pod(namespace, name)
            if not isinstance(live, dict):
                raise ValueError("the bound live Pod could not be read")
            metadata = live.get("metadata") or {}
            labels = metadata.get("labels") or {}
            if (metadata.get("namespace") != namespace or metadata.get("name") != name
                    or labels.get("posture.acme.io/caged") != "true"
                    or labels.get("posture.acme.io/tier") != decision["tier"]
                    or labels.get("policy-as-versioned.dev/policy-version") != version):
                raise ValueError("the bound live Pod's identity, version or cage tier differs from its priced decision")
            risks.append(risk)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            errors.append(f"{(binding or {}).get('subject', entry.get('rule', 'unknown')) if isinstance(binding, dict) else entry.get('rule', 'unknown')}: {exc}")
    return risks, errors


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("the pinned instrument has no readable module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def component_inputs(sampler, base: dict) -> tuple[dict, dict, list[dict]]:
    """Read cloud mapping and members only from the actually selected composed tag.

    The signed composed artefact carries the identity-verified cloud parent and
    its control claims. Current worktree files cannot activate a future mapping.
    """
    tag = sampler.rc.pinned_tag()
    def read(path: str) -> str | None:
        return sampler._git_output('show', tag + ':' + path)
    header = yaml.safe_load(read('composed/HEADER.yaml') or '{}')
    if not header.get('cloud-package'):
        return base, {}, []
    raw = read('composed/CLOUD-PARENT.json')
    if not raw:
        raise ValueError('cloud component parent is missing from the selected signed composition')
    parent = json.loads(raw)
    if (parent.get('party'), parent.get('kind'), parent.get('name')) != ('platform', 'implementations', 'cloud'):
        raise ValueError('cloud component parent names a different package')
    version = parent.get('version', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or parent.get('tag') != 'cloud/v' + version or not re.fullmatch(r'[0-9a-f]{40}', parent.get('sha', '')):
        raise ValueError('cloud component parent has no immutable package pin')
    if header.get('cloud-package') != parent:
        raise ValueError('cloud component parent differs from the signed composition header')
    directory = 'composed/cloud/v' + version
    text = read(directory + '/component-definition.json')
    if not text:
        raise ValueError('cloud component-definition is missing from the selected signed composition')
    cloud = json.loads(text)
    if cloud['component-definition']['metadata']['version'] != version:
        raise ValueError('cloud component-definition version differs from its parent')
    combined = copy.deepcopy(base)
    combined['component-definition']['components'].extend(cloud['component-definition']['components'])
    mappings: dict[str, str] = {}
    for component in combined['component-definition']['components']:
        for implementation in component.get('control-implementations', []):
            for requirement in implementation.get('implemented-requirements', []):
                for prop in requirement.get('props', []):
                    if prop.get('name') == 'Check_Id':
                        name, control = prop['value'], requirement['control-id']
                        if name in mappings and mappings[name] != control:
                            raise ValueError('cloud control mapping conflicts with the pinned Pod mapping: ' + name)
                        mappings[name] = control
    membership = yaml.safe_load(read(directory + '/kustomization.yaml') or '{}')
    policies = {}
    for filename in membership.get('resources', []):
        if Path(filename).name != filename or not filename.endswith('.yaml'):
            raise ValueError('cloud policy membership escapes its signed directory')
        doc = yaml.safe_load(read(directory + '/' + filename) or '{}')
        metadata = doc.get('metadata') or {}
        if (doc.get('kind') not in ('ValidatingPolicy', 'MutatingPolicy')
                or metadata.get('annotations', {}).get('policy-as-versioned.dev/inherited-from') != 'platform@' + parent['sha']
                or metadata.get('labels', {}).get('policy-as-versioned.dev/cloud-package-version') != version):
            raise ValueError('cloud policy differs from its declared signed parent')
        policies[f"{doc['apiVersion']}/{doc['kind']}/{metadata['name']}"] = doc
    if not policies:
        raise ValueError('cloud policy membership is empty in the signed composition')
    return combined, policies, [{'party': 'platform', 'name': 'cloud', 'tag': parent['tag'],
                               'sha': parent['sha'], 'composed_tag': tag,
                               'component_definition': directory + '/component-definition.json'}]


def collect(context: str, platform: Path) -> dict:
    sampler = load(HERE / "five-facts.py", "five_facts_instrument")
    cluster = sampler.Cluster(context)
    stamp = sampler.now()
    row = {"kind": KIND, "ts": stamp, "run": os.environ.get("GITHUB_RUN_ID", ""), "event": os.environ.get("GITHUB_EVENT_NAME", ""), "context": context,
           "status": "could-not-look", "report_count": 0, "mapped_served_policy_count": 0}
    reports: list[dict] = []
    read_errors: list[str] = []
    for resource, arguments in (("policyreports.wgpolicyk8s.io", ("-A",)),
                                ("clusterpolicyreports.wgpolicyk8s.io", ())):
        response = cluster.get("get", resource, *arguments)
        if not isinstance(response, dict) or not isinstance(response.get("items"), list):
            read_errors.append(f"{resource}: {cluster.reason or 'no readable API list response'}")
        else:
            reports.extend(response["items"])
    row["report_read_errors"] = read_errors
    row["report_count"] = len(reports)
    try:
        converter = load(platform / "oscal/result2oscal.py", "pinned_result2oscal")
        # import cage in the converter may resolve a cached module from another
        # tree. Both UUID joins and risk derivation must use this verified pin.
        converter.cage = load(platform / "graded/cage.py", "pinned_cage")
        comp = json.loads((platform / "oscal/component-definition.json").read_text())
        served = sampler.rc.render(sampler.rc.pinned_tag())
        if read_errors:
            row["why"] = "PolicyReport API could not be read: " + "; ".join(read_errors)
            return row
        if not reports:
            row["why"] = "no PolicyReport existed on the lane cluster before teardown"
            return row
        comp, cloud_policies, sources = component_inputs(sampler, comp)
        mapping = converter.check_to_control(comp)
        served.update(cloud_policies)
        row['cloud_component_sources'] = sources
        policy_names = {re.sub(r"-\d+-\d+-\d+$", "", d["metadata"]["name"])
                        for d in served.values() if d.get("kind", "").endswith("Policy")}
        row["mapped_served_policy_count"] = len(policy_names.intersection(mapping))
        row["served_policy_count"] = len(policy_names)
        row["unmapped_served_policies"] = sorted(policy_names - set(mapping))
        assessment = converter.convert(reports, comp)
        assessment["assessment-results"]["metadata"]["last-modified"] = stamp
        for result in assessment["assessment-results"]["results"]:
            result["start"] = stamp
        # Only carried, priced risk objects count. A report cannot invent a Cage decision or
        # its money. Empty risk input therefore leaves a failing join visible to the gate.
        evidence = json.loads(sampler._git_output("show", sampler.rc.pinned_tag() + ":composed/evidence.json") or "{}")
        risks, validation_errors = validated_risks(evidence, mapping, converter.cage,
            lambda namespace, name: cluster.get("-n", namespace, "get", "pod", name))
        row["assessment_results"] = assessment
        row["risks"] = risks
        row["risk_validation_errors"] = validation_errors
        row["missing_risk_observations"] = missing_risks(assessment, risks)
        row["unmapped_failed_results"] = sorted({r["policy"] for rep in reports for r in rep.get("results") or []
                                                if r.get("result") == "fail" and re.sub(r"-\d+-\d+-\d+$", "", r["policy"]) not in mapping})
        row["status"] = "observed"
        row["why"] = f"converted {len(reports)} PolicyReports at the lane's pinned platform tree"
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError) as exc:
        row["why"] = f"the pinned converter or its inputs could not be read: {exc}"
    return row


def grade() -> tuple[int, str]:
    try:
        rows = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
        row = max((r for r in rows if r.get("kind") == KIND), key=lambda r: r["ts"])
    except (OSError, ValueError, KeyError):
        return 3, "SKIP: no scheduled OSCAL observation has landed on the lane"
    stamp = dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
    if dt.datetime.now(dt.timezone.utc) - stamp > dt.timedelta(hours=48):
        return 3, "SKIP: the newest OSCAL observation is older than the 48h freshness bound"
    sampler = load(HERE / "five-facts.py", "five_facts_instrument")
    rehearsal = sampler.sample_provenance(str(LOG), [row])
    if rehearsal:
        return 3, "SKIP: " + rehearsal.replace("drift/samples.jsonl", "drift/oscal-samples.jsonl").replace("five-fact sample", "OSCAL sample")
    if row.get("status") != "observed":
        return 3, "SKIP: " + row.get("why", "the lane could not collect its PolicyReports")
    missing = missing_risks(row.get("assessment_results") or {}, row.get("risks") or [])
    unmapped = row.get("unmapped_failed_results") or []
    invalid = row.get("risk_validation_errors") or []
    if missing or unmapped or invalid:
        return 1, f"FAIL: {len(missing)} not-satisfied observations have no cage risk; {len(unmapped)} failed policy results have no control mapping; {len(invalid)} carried risks failed decision/live-Pod validation: " + ", ".join(missing + unmapped + invalid)
    if row.get("event") != "schedule":
        return 3, "SKIP: an OSCAL lane run started by hand cannot establish a cited pass"
    return 0, f"PASS: {row['report_count']} PolicyReports; {row['mapped_served_policy_count']} served policies mapped; every not-satisfied observation joins an actual cage risk"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    take = sub.add_parser("collect")
    take.add_argument("--context", required=True)
    take.add_argument("--platform", type=Path, default=ROOT / ".platform-src")
    sub.add_parser("selfcheck")
    sub.add_parser("grade")
    args = parser.parse_args()
    if args.command == "selfcheck":
        return selfcheck()
    if args.command == "collect":
        row = collect(args.context, args.platform)
        with LOG.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"OSCAL observation: {row['mapped_served_policy_count']} served policies mapped; {row['report_count']} PolicyReports; {row['status']}: {row['why']}")
        return 0
    rc, line = grade()
    print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
