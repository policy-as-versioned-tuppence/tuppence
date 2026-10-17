"""The cloud workload is the incumbent lift, not replacement demo resources."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

import pytest
import yaml


SOURCE = Path(__file__).resolve().parents[1] / 'gitops/cloud/prepare.py'
SPEC = importlib.util.spec_from_file_location('cloud_prepare', SOURCE)
assert SPEC is not None and SPEC.loader is not None
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


def test_the_three_incumbent_resources_and_specs_are_preserved():
    docs = prepare.incumbent_claims()
    assert [doc['metadata']['name'] for doc in docs] == [
        'datastore-s3-compliant', 'datastore-rds-compliant',
        'datastore-rds-noncompliant',
    ]
    assert [doc['spec']['forProvider']['multiAz'] for doc in docs if doc['kind'] == 'Instance'] == [True, False]
    assert docs[0]['spec']['forProvider']['bucketSelector']['matchLabels'] == {
        'testing.upbound.io/example-name': 'mybucket',
    }
    assert all(doc['metadata']['namespace'] == 'tuppence' for doc in docs)
    assert all(doc['metadata']['labels']['department'] == 'data' for doc in docs)


@pytest.mark.parametrize('changed', ['drop-resource', 'rename', 'weaken', 'selector', 'snapshot'])
def test_resource_drift_is_refused_before_preparing_composed_paths(tmp_path, monkeypatch, changed):
    directory = tmp_path / 'cloud'
    shutil.copytree(prepare.HERE, directory)
    monkeypatch.setattr(prepare, 'HERE', directory)
    path = directory / 'claims.yaml'
    docs = list(yaml.safe_load_all(path.read_text()))
    if changed == 'drop-resource':
        docs.pop()
    elif changed == 'rename':
        docs[1]['metadata']['name'] = 'new-ledger-demo'
    elif changed == 'weaken':
        docs[1]['spec']['forProvider']['multiAz'] = False
    elif changed == 'selector':
        docs[0]['spec']['forProvider']['bucketSelector'] = {'matchLabels': {'name': 'different-bucket'}}
    else:
        snapshot = directory / 'sources/datastore-claims.yaml'
        snapshot.write_bytes(snapshot.read_bytes() + b'\n')
    path.write_text(yaml.safe_dump_all(docs, sort_keys=False))
    with pytest.raises(ValueError, match='incumbent'):
        prepare.incumbent_claims()
